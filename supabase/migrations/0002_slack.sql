-- 0002_slack.sql
-- Slack ingestion: slack_channels (metadata) and slack_messages (message history).

-- ---------------------------------------------------------------------------
-- slack_channels
-- ---------------------------------------------------------------------------
create table slack_channels (
  id                uuid primary key default gen_random_uuid(),
  slack_channel_id  text not null unique,
  name              text not null,
  client_id         uuid references clients(id),
  is_private        boolean not null,
  is_archived       boolean not null default false,
  ella_enabled      boolean not null default false,
  metadata          jsonb not null default '{}'::jsonb,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

comment on table slack_channels is
  'Slack channel metadata, mapped to clients where applicable. Populated on bot install and refreshed periodically.';
comment on column slack_channels.slack_channel_id is
  'Slack C... identifier. Stable across renames — use this, not name, for joins.';
comment on column slack_channels.client_id is
  'Nullable. Set only for client-facing channels; internal channels leave this null.';
comment on column slack_channels.ella_enabled is
  'Beta gate. Ella only responds in channels where this is true. Keep off by default.';

create index slack_channels_client_id_idx on slack_channels (client_id);
create index slack_channels_ella_enabled_idx on slack_channels (ella_enabled) where ella_enabled = true;

create trigger slack_channels_set_updated_at
  before update on slack_channels
  for each row execute function set_updated_at();

alter table slack_channels enable row level security;

-- ---------------------------------------------------------------------------
-- slack_messages
-- ---------------------------------------------------------------------------
create table slack_messages (
  id                uuid primary key default gen_random_uuid(),
  slack_channel_id  text not null,
  slack_ts          text not null,
  slack_thread_ts   text,
  slack_user_id     text not null,
  author_type       text not null,
  text              text not null,
  message_type      text not null default 'message',
  message_subtype   text,
  raw_payload       jsonb not null,
  sent_at           timestamptz not null,
  ingested_at       timestamptz not null default now(),
  unique (slack_channel_id, slack_ts)
);

comment on table slack_messages is
  'Ingested Slack messages. Stores both the raw payload and a normalized form for retrieval. Historical backfill + real-time events.';
comment on column slack_messages.slack_channel_id is
  'Channel C... id. Matches slack_channels.slack_channel_id but deliberately not a FK — messages ingest before the channel record may exist.';
comment on column slack_messages.slack_ts is
  'Slack message timestamp. Unique per message within a channel; forms the natural key.';
comment on column slack_messages.slack_thread_ts is
  'Parent message ts when this message is in a thread. Null otherwise.';
comment on column slack_messages.author_type is
  'Classification of the author: client, team_member, bot, workflow, unknown. Resolved during ingestion by joining slack_user_id to clients/team_members.';
comment on column slack_messages.message_subtype is
  'Domain subtype tagged during ingestion: accountability_submission, nps_submission, etc. Enables CSM Co-Pilot queries without reparsing.';
comment on column slack_messages.raw_payload is
  'Full original Slack event. Preserved verbatim so new fields can be extracted later without re-ingestion.';

create index slack_messages_channel_sent_at_idx on slack_messages (slack_channel_id, sent_at desc);
create index slack_messages_thread_ts_idx on slack_messages (slack_channel_id, slack_thread_ts) where slack_thread_ts is not null;
create index slack_messages_user_id_idx on slack_messages (slack_user_id);
create index slack_messages_subtype_idx on slack_messages (message_subtype) where message_subtype is not null;

alter table slack_messages enable row level security;
