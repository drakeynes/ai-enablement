-- 0009_add_assignments_metadata.sql
-- Add metadata jsonb to client_team_assignments so the clients importer
-- (and future admin actions) can preserve provenance — specifically the
-- raw Owner string from the Financial Master Sheet when it didn't match
-- a single team member cleanly (e.g. "Lou (Scott Chasing)", "Lou > Nico?").

alter table client_team_assignments
  add column metadata jsonb not null default '{}'::jsonb;

comment on column client_team_assignments.metadata is
  'Extensible blob for assignment provenance. Used by the clients importer '
  'to record raw_owner strings that required heuristic parsing.';
