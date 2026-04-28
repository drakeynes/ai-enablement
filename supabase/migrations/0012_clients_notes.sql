-- 0012_clients_notes.sql
-- Adds a free-text notes column to clients for the Gregory dashboard.
-- Edited inline by team members on the client detail page.

alter table clients add column notes text;

comment on column clients.notes is
  'Free-text notes per client. Edited by team members via the Gregory dashboard.';
