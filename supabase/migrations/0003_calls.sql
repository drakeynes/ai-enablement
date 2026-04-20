-- 0003_calls.sql
-- Call data: calls, call_participants, call_action_items.
-- Primary source today is Fathom; schema is source-agnostic.

-- ---------------------------------------------------------------------------
-- calls
-- ---------------------------------------------------------------------------
create table calls (
  id                              uuid primary key default gen_random_uuid(),
  external_id                     text not null unique,
  source                          text not null default 'fathom',
  title                           text,
  call_category                   text not null,
  call_type                       text,
  classification_confidence       float,
  classification_method           text,
  primary_client_id               uuid references clients(id),
  started_at                      timestamptz not null,
  duration_seconds                integer,
  recording_url                   text,
  transcript                      text,
  summary                         text,
  is_retrievable_by_client_agents boolean not null default false,
  raw_payload                     jsonb not null,
  ingested_at                     timestamptz not null default now()
);

comment on table calls is
  'One row per recorded call. Source is Fathom today; schema allows additional sources later. Classification happens at ingestion time.';
comment on column calls.external_id is
  'Source-system call id (e.g. Fathom call id). Unique across sources when combined with source column values, though a single external_id collision across sources is not currently expected.';
comment on column calls.source is
  'Origin system: fathom today. Leaving this open lets us add gong, zoom, etc. without schema change.';
comment on column calls.call_category is
  'Primary safety-relevant classification: client, internal, external, unclassified, excluded. Controls which agents may read this call.';
comment on column calls.call_type is
  'Finer-grained sub-type within the category (sales, onboarding, csm_check_in, coaching, team_sync, leadership, strategy, unknown).';
comment on column calls.classification_confidence is
  '0-1 score of how confident we are in call_category. Low-confidence calls may flow to human review.';
comment on column calls.classification_method is
  'How the category was chosen: participant_match, title_pattern, llm_classified, manual.';
comment on column calls.primary_client_id is
  'For client calls, the primary client this call is about. Call_participants still captures the full attendee list.';
comment on column calls.transcript is
  'Full transcript text. Stored here but not indexed into document_chunks — summaries go to retrieval, raw transcript is too noisy.';
comment on column calls.is_retrievable_by_client_agents is
  'HARD SAFETY GATE. Client-facing agents (Ella, etc.) MUST filter on this being true. Defaults to false; flipped on only after confident classification as a client call for the correct client.';
comment on column calls.raw_payload is
  'Full source API response. Preserved so new fields can be extracted later.';

create index calls_primary_client_id_idx on calls (primary_client_id);
create index calls_category_idx on calls (call_category);
create index calls_started_at_idx on calls (started_at desc);
create index calls_retrievable_idx on calls (primary_client_id, started_at desc)
  where is_retrievable_by_client_agents = true;

alter table calls enable row level security;

-- ---------------------------------------------------------------------------
-- call_participants
-- ---------------------------------------------------------------------------
create table call_participants (
  id                uuid primary key default gen_random_uuid(),
  call_id           uuid not null references calls(id) on delete cascade,
  email             text not null,
  display_name      text,
  client_id         uuid references clients(id),
  team_member_id    uuid references team_members(id),
  participant_role  text,
  unique (call_id, email)
);

comment on table call_participants is
  'Attendees of each call. Matches emails to known clients and team_members when possible; unresolved attendees leave both FKs null.';
comment on column call_participants.email is
  'Attendee email from the source system. Used as the join key back to clients/team_members.';
comment on column call_participants.client_id is
  'Matched client. Null if the email did not resolve or the attendee is not a client.';
comment on column call_participants.team_member_id is
  'Matched team member. Null if the email did not resolve or the attendee is not team.';
comment on column call_participants.participant_role is
  'host, attendee, or other source-provided role.';

create index call_participants_call_id_idx on call_participants (call_id);
create index call_participants_client_id_idx on call_participants (client_id) where client_id is not null;
create index call_participants_team_member_id_idx on call_participants (team_member_id) where team_member_id is not null;
create index call_participants_email_idx on call_participants (email);

alter table call_participants enable row level security;

-- ---------------------------------------------------------------------------
-- call_action_items
-- ---------------------------------------------------------------------------
create table call_action_items (
  id                    uuid primary key default gen_random_uuid(),
  call_id               uuid not null references calls(id) on delete cascade,
  owner_type            text,
  owner_client_id       uuid references clients(id),
  owner_team_member_id  uuid references team_members(id),
  description           text not null,
  due_date              date,
  status                text not null default 'open',
  extracted_at          timestamptz not null default now(),
  completed_at          timestamptz
);

comment on table call_action_items is
  'Action items extracted from call summaries. Initially populated from Fathom; later enriched by Claude extraction on raw transcripts.';
comment on column call_action_items.owner_type is
  'Who owns the action: client, team_member, unknown. Drives which owner_* FK is set.';
comment on column call_action_items.status is
  'open, done, cancelled.';
comment on column call_action_items.extracted_at is
  'When the action item was first extracted — distinct from the call''s started_at.';

create index call_action_items_call_id_idx on call_action_items (call_id);
create index call_action_items_owner_client_idx on call_action_items (owner_client_id) where owner_client_id is not null;
create index call_action_items_owner_team_member_idx on call_action_items (owner_team_member_id) where owner_team_member_id is not null;
create index call_action_items_status_idx on call_action_items (status);
create index call_action_items_due_date_idx on call_action_items (due_date) where status = 'open';

alter table call_action_items enable row level security;
