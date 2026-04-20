-- 0001_core_entities.sql
-- Core entities: team_members, clients, client_team_assignments.
-- Also defines the shared set_updated_at() trigger function used across the schema.

-- Ensure gen_random_uuid() is available. Postgres 13+ has it built in,
-- but explicitly enabling pgcrypto makes the intent clear and is a no-op on Supabase.
create extension if not exists pgcrypto;

-- Shared trigger function for bumping updated_at on row update.
-- Used by every table that carries an updated_at column.
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- team_members
-- ---------------------------------------------------------------------------
create table team_members (
  id              uuid primary key default gen_random_uuid(),
  email           text not null unique,
  full_name       text not null,
  role            text not null,
  slack_user_id   text unique,
  is_active       boolean not null default true,
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  archived_at     timestamptz
);

comment on table team_members is
  'Agency-side humans (CSMs, leadership, engineering, ops). Seeded manually for V1; grows programmatically later.';
comment on column team_members.role is
  'Free-form role label: csm, leadership, engineering, ops.';
comment on column team_members.slack_user_id is
  'Slack U... id. Used to match Slack events to team members and to @-mention them from agents.';
comment on column team_members.metadata is
  'Extensible blob for ad-hoc attributes we have not promoted to columns yet.';
comment on column team_members.archived_at is
  'Soft delete. Set to the time of archival; nulls mean active records.';

create index team_members_is_active_idx on team_members (is_active) where archived_at is null;

create trigger team_members_set_updated_at
  before update on team_members
  for each row execute function set_updated_at();

alter table team_members enable row level security;

-- ---------------------------------------------------------------------------
-- clients
-- ---------------------------------------------------------------------------
create table clients (
  id              uuid primary key default gen_random_uuid(),
  email           text not null unique,
  full_name       text not null,
  slack_user_id   text unique,
  phone           text,
  timezone        text,
  journey_stage   text,
  status          text not null default 'active',
  start_date      date,
  program_type    text,
  tags            text[] not null default '{}'::text[],
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  archived_at     timestamptz
);

comment on table clients is
  'Customers of the agency. One row per person. Company-level grouping, if ever needed, lives in a future companies table.';
comment on column clients.journey_stage is
  'Lifecycle bucket: onboarding, active, churning, churned, alumni. Free text to avoid schema churn during V1 tuning.';
comment on column clients.status is
  'Operational status: active, paused, ghost, churned. Distinct from journey_stage — captures present engagement.';
comment on column clients.tags is
  'Ad-hoc labels (beta_tester, high_value, at_risk, etc.). Promote to columns once queried frequently.';
comment on column clients.metadata is
  'Long tail of attributes (goals, SWOT, profession, age). Promote high-traffic fields to real columns later.';

create index clients_status_idx on clients (status) where archived_at is null;
create index clients_journey_stage_idx on clients (journey_stage) where archived_at is null;
create index clients_tags_idx on clients using gin (tags);

create trigger clients_set_updated_at
  before update on clients
  for each row execute function set_updated_at();

alter table clients enable row level security;

-- ---------------------------------------------------------------------------
-- client_team_assignments
-- ---------------------------------------------------------------------------
create table client_team_assignments (
  id              uuid primary key default gen_random_uuid(),
  client_id       uuid not null references clients(id),
  team_member_id  uuid not null references team_members(id),
  role            text not null,
  assigned_at     timestamptz not null default now(),
  unassigned_at   timestamptz,
  unique (client_id, team_member_id, role)
);

comment on table client_team_assignments is
  'Many-to-many: which team members serve which clients, and in what role. A client may have a primary CSM and a secondary coach simultaneously.';
comment on column client_team_assignments.role is
  'Assignment role: primary_csm, secondary_csm, coach.';
comment on column client_team_assignments.unassigned_at is
  'Preserves history; null means the assignment is current.';

create index client_team_assignments_client_id_idx on client_team_assignments (client_id);
create index client_team_assignments_team_member_id_idx on client_team_assignments (team_member_id);
create index client_team_assignments_active_idx on client_team_assignments (client_id, team_member_id)
  where unassigned_at is null;

alter table client_team_assignments enable row level security;
