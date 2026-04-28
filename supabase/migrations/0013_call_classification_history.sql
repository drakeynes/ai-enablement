-- 0013_call_classification_history.sql
-- Audit trail for manual edits to call classification fields via the Gregory
-- dashboard. Written application-side from the Calls detail page on save —
-- not trigger-based, so the audit logic stays visible in dashboard code.
--
-- Append-only by convention. No deletes, no updates after insert.

create table call_classification_history (
  id           uuid primary key default gen_random_uuid(),
  call_id      uuid not null references calls(id) on delete cascade,
  changed_by   uuid references team_members(id),
  changed_at   timestamptz not null default now(),
  field_name   text not null check (field_name in ('call_category', 'call_type', 'primary_client_id')),
  old_value    text,
  new_value    text
);

comment on table call_classification_history is
  'Audit trail for manual edits to call classification via the Gregory dashboard. Append-only.';
comment on column call_classification_history.changed_by is
  'Nullable because team_members.id may not resolve cleanly during early V1 (auth.users to team_members join via email is best-effort).';
comment on column call_classification_history.field_name is
  'Constrained to the three classification fields the dashboard exposes for edit. Adding new editable fields requires updating both the dashboard and the constraint.';
comment on column call_classification_history.old_value is
  'Pre-edit value as text. UUIDs stored as their string form.';

create index call_classification_history_call_id_idx
  on call_classification_history (call_id);
create index call_classification_history_changed_at_idx
  on call_classification_history (changed_at desc);

alter table call_classification_history enable row level security;
