-- 0017_client_page_schema_v1.sql
-- Schema additions for the V1 client detail page (M4 Chunk A).
-- Adds 14 columns to clients, 1 column to nps_submissions, and 4 new tables:
-- client_upsells, client_status_history, client_journey_stage_history,
-- client_standing_history. History tables follow the application-layer
-- write pattern (mirror client_team_assignments) — not trigger-based.
--
-- Two history tables are seeded at migration time from existing clients:
-- status (one row per non-archived client with non-null status) and
-- journey_stage (one row per client with non-null journey_stage).
-- client_standing_history is seeded by the master sheet import script
-- (Chunk C) since csm_standing has no values at migration time.
--
-- Full design: docs/client-page-schema-spec.md.

-- ---------------------------------------------------------------------------
-- clients — 14 new columns
-- ---------------------------------------------------------------------------
alter table clients
  add column country                  text,
  add column birth_year               integer
    check (birth_year is null or (birth_year >= 1900 and birth_year <= extract(year from current_date)::int)),
  add column location                 text,
  add column occupation               text,
  add column csm_standing             text
    check (csm_standing is null or csm_standing in ('happy', 'content', 'at_risk', 'problem')),
  add column archetype                text,
  add column contracted_revenue       numeric(10, 2),
  add column upfront_cash_collected   numeric(10, 2),
  add column arrears                  numeric(10, 2) not null default 0,
  add column arrears_note             text,
  add column trustpilot_status        text
    check (trustpilot_status is null or trustpilot_status in ('not_asked', 'pending', 'given', 'declined')),
  add column ghl_adoption             text
    check (ghl_adoption is null or ghl_adoption in ('never_adopted', 'affiliate', 'saas', 'inactive')),
  add column sales_group_candidate    boolean,
  add column dfy_setting              boolean;

create index clients_csm_standing_idx       on clients (csm_standing)       where archived_at is null;
create index clients_trustpilot_status_idx  on clients (trustpilot_status)  where archived_at is null;
create index clients_ghl_adoption_idx       on clients (ghl_adoption)       where archived_at is null;

comment on column clients.country is
  'Free-text country. ISO codes deferred until query patterns surface a need.';
comment on column clients.birth_year is
  'Year only; age derived at display. Constrained to 1900..current_year.';
comment on column clients.location is
  'Free-text city or region. Distinct from country; both can be set or just one.';
comment on column clients.occupation is
  'What the client does for work. Free text.';
comment on column clients.csm_standing is
  'CSM-judgment standing: happy, content, at_risk, problem. Distinct from financial standing — split during master sheet import where the source column mixed both.';
comment on column clients.archetype is
  'Personality/behavior archetype label. Free text in V1; will be enum-constrained once Drake/Nabeel finalize the value set.';
comment on column clients.contracted_revenue is
  'Total program contract value in dollars.';
comment on column clients.upfront_cash_collected is
  'Upfront payment captured at signup, in dollars.';
comment on column clients.arrears is
  'Amount owed in dollars. Not null; defaults to 0. Negative master-sheet values normalize to 0 during import.';
comment on column clients.arrears_note is
  'Operational note explaining arrears state (e.g. payment plan in progress, dispute pending).';
comment on column clients.trustpilot_status is
  'Workflow state for the Trustpilot review ask: not_asked, pending, given, declined.';
comment on column clients.ghl_adoption is
  'GHL product adoption state: never_adopted, affiliate, saas, inactive. Enum subject to Nabeel review; widen if needed.';
comment on column clients.sales_group_candidate is
  'Three-state: true / false / null (not assessed). CSMs refresh per-client in the dashboard.';
comment on column clients.dfy_setting is
  'Three-state: true / false / null (not assessed). CSMs refresh per-client in the dashboard.';

-- ---------------------------------------------------------------------------
-- nps_submissions — recorded_by
-- ---------------------------------------------------------------------------
alter table nps_submissions
  add column recorded_by uuid references team_members(id);

comment on column nps_submissions.recorded_by is
  'Which team member entered this score manually. Null for entries from automated sources (Slack workflow, future Airtable webhook).';

-- ---------------------------------------------------------------------------
-- client_upsells
-- ---------------------------------------------------------------------------
create table client_upsells (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id) on delete cascade,
  amount        numeric(10, 2),
  product       text,
  sold_at       date,
  notes         text,
  recorded_by   uuid references team_members(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

comment on table client_upsells is
  'Upsell sales per client. Populated by the master sheet importer for legacy upsells and the Gregory dashboard going forward. Cascade-delete on client_id matches owned-by-parent pattern (call_participants, call_action_items).';
comment on column client_upsells.amount is
  'Dollar amount of the upsell. Nullable — the master sheet has free-text upsell descriptions without amounts; in those cases store the full text in notes and leave amount null.';
comment on column client_upsells.product is
  'What was sold (e.g. coaching package, additional content). Nullable; the master sheet often lacks a clean product field.';
comment on column client_upsells.sold_at is
  'Date the upsell sale closed. Nullable for the same reason as amount.';
comment on column client_upsells.notes is
  'Free-text context. Captures the master sheet''s raw text when amount/product cannot be parsed cleanly.';
comment on column client_upsells.recorded_by is
  'Team member who logged the upsell. Null for legacy rows imported from the master sheet.';

create index client_upsells_client_id_sold_at_idx
  on client_upsells (client_id, sold_at desc nulls last);

create trigger client_upsells_set_updated_at
  before update on client_upsells
  for each row execute function set_updated_at();

alter table client_upsells enable row level security;

-- ---------------------------------------------------------------------------
-- client_status_history
-- ---------------------------------------------------------------------------
create table client_status_history (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references clients(id),
  status      text not null,
  changed_at  timestamptz not null default now(),
  changed_by  uuid references team_members(id),
  note        text
);

comment on table client_status_history is
  'Append-only history of clients.status changes. Application-layer writes from the dashboard API route — pattern mirrors client_team_assignments. Not trigger-based, so the audit logic stays visible in dashboard code. Seeded at migration time with one row per non-archived client (changed_at = clients.created_at, note = ''initial migration seed'').';
comment on column client_status_history.status is
  'The status value at the time of this row. Mirrors clients.status enum-by-convention (active, paused, ghost, churned). Not constrained here so adding new status values does not require a migration.';
comment on column client_status_history.changed_by is
  'Team member who made the change. Nullable because team_members.id may not resolve cleanly during early V1 (auth.users → team_members join via email is best-effort), and because the migration seed has no author.';
comment on column client_status_history.note is
  'Optional free-text reason for the change. Used by the migration seed to mark seeded rows.';

create index client_status_history_client_id_changed_at_idx
  on client_status_history (client_id, changed_at desc);

alter table client_status_history enable row level security;

-- ---------------------------------------------------------------------------
-- client_journey_stage_history
-- ---------------------------------------------------------------------------
create table client_journey_stage_history (
  id              uuid primary key default gen_random_uuid(),
  client_id       uuid not null references clients(id),
  journey_stage   text,
  changed_at      timestamptz not null default now(),
  changed_by      uuid references team_members(id),
  note            text
);

comment on table client_journey_stage_history is
  'Append-only history of clients.journey_stage changes. Same application-layer write pattern as client_status_history. Seeded at migration time with one row per client whose clients.journey_stage is non-null (most rows have null journey_stage so the seed is small).';
comment on column client_journey_stage_history.journey_stage is
  'Lifecycle bucket at the time of this row (onboarding, active, churning, churned, alumni). Nullable because the application can record a transition into "no stage" — and because mirroring clients.journey_stage''s nullability avoids needing a sentinel value.';
comment on column client_journey_stage_history.changed_by is
  'Team member who made the change. Nullable for the same reason as client_status_history.changed_by.';
comment on column client_journey_stage_history.note is
  'Optional free-text reason for the change. Used by the migration seed to mark seeded rows.';

create index client_journey_stage_history_client_id_changed_at_idx
  on client_journey_stage_history (client_id, changed_at desc);

alter table client_journey_stage_history enable row level security;

-- ---------------------------------------------------------------------------
-- client_standing_history
-- ---------------------------------------------------------------------------
create table client_standing_history (
  id              uuid primary key default gen_random_uuid(),
  client_id       uuid not null references clients(id),
  csm_standing    text not null check (csm_standing in ('happy', 'content', 'at_risk', 'problem')),
  changed_at      timestamptz not null default now(),
  changed_by      uuid references team_members(id),
  note            text
);

comment on table client_standing_history is
  'Append-only history of clients.csm_standing changes. Same application-layer write pattern as client_status_history. Not seeded at migration time — clients.csm_standing has no values until the master sheet import (Chunk C) runs; the importer writes one history row per non-null standing it sets.';
comment on column client_standing_history.csm_standing is
  'CSM-judgment standing at the time of this row. Check constraint matches clients.csm_standing.';
comment on column client_standing_history.changed_by is
  'Team member who made the change. Nullable for the same reason as client_status_history.changed_by.';
comment on column client_standing_history.note is
  'Optional free-text reason for the change. The importer uses this to tag rows seeded from the master sheet (e.g. ''master sheet import'').';

create index client_standing_history_client_id_changed_at_idx
  on client_standing_history (client_id, changed_at desc);

alter table client_standing_history enable row level security;

-- ---------------------------------------------------------------------------
-- Seed inserts — run at migration time
-- ---------------------------------------------------------------------------
-- One row per non-archived client with non-null status. Filter on archived_at
-- to keep history rows scoped to live clients (per the spec doc).
insert into client_status_history (client_id, status, changed_at, note)
select id, status, created_at, 'initial migration seed'
from clients
where status is not null
  and archived_at is null;

-- One row per non-archived client with non-null journey_stage. Symmetric
-- with the status-history seed above — both filter on archived_at is null.
-- Most existing clients have null journey_stage, so the seed produces a
-- small number of rows.
insert into client_journey_stage_history (client_id, journey_stage, changed_at, note)
select id, journey_stage, created_at, 'initial migration seed'
from clients
where journey_stage is not null
  and archived_at is null;

-- No seed for client_standing_history — clients.csm_standing has no values
-- yet. The master sheet import (Chunk C) writes the first history rows.
