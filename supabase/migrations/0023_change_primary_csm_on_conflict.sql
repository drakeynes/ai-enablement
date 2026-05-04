-- 0023_change_primary_csm_on_conflict.sql
-- M5.6 hotfix: replace the 0014 change_primary_csm RPC with an
-- ON CONFLICT variant so re-assignment back to a previously-archived
-- (client_id, team_member_id, primary_csm) row succeeds instead of
-- erroring on the unique key.
--
-- Failure mode this fixes (Bug 3 from the M5.6 visual smoke):
--   1. Client X is assigned to CSM A (active row in client_team_assignments).
--   2. CSM swap A → B via the dashboard. 0014 archives row(X, A) and
--      inserts row(X, B). Both rows now exist, only B is active.
--   3. CSM swap B → A. 0014 archives row(X, B). Then unconditionally
--      INSERTs row(X, A) — which **fails** on UNIQUE (client_id,
--      team_member_id, role) because the archived row(X, A) from step
--      1 still exists.
--
-- The M5.6 cascade trigger (clients_status_cascade_after, migration
-- 0022) hit the same case for Scott Chasing reassignment and uses
-- ON CONFLICT DO UPDATE to reactivate the archived row. This migration
-- aligns the dashboard-facing RPC to the same pattern.
--
-- Signature unchanged: (p_client_id uuid, p_new_team_member_id uuid)
-- returns void, language plpgsql, security definer. No callers need
-- to change. Behavior change is purely additive — a previously-erroring
-- swap pattern now succeeds; the previously-working "first-time
-- assignment" path is unchanged (no conflict to resolve, INSERT lands
-- a fresh row).

create or replace function change_primary_csm(
  p_client_id uuid,
  p_new_team_member_id uuid
) returns void
language plpgsql
security definer
as $$
begin
  -- Archive the current active primary CSM for this client (if any).
  update client_team_assignments
  set unassigned_at = now()
  where client_id = p_client_id
    and role = 'primary_csm'
    and unassigned_at is null;

  -- Insert the new primary CSM assignment.
  --
  -- ON CONFLICT explanation (the why, not the how):
  -- client_team_assignments has UNIQUE (client_id, team_member_id, role).
  -- The re-assignment-after-archival case is the failure mode: a swap
  -- A → B → A leaves the archived (X, A) row from the first archival
  -- still in the table; a plain INSERT collides on the unique key.
  -- DO UPDATE reactivates the archived row instead: clear unassigned_at,
  -- bump assigned_at to now() to reflect the fresh active assignment.
  -- Result: one row per (client_id, team_member_id, primary_csm) flips
  -- between active and archived as the team member is assigned and
  -- unassigned over time. History is preserved in the assigned_at /
  -- unassigned_at sequence on that single row's lifecycle.
  --
  -- Mirrors the same pattern in clients_status_cascade_after (0022) so
  -- both the cascade-fired path and the dashboard-fired path produce
  -- identical row shapes.
  insert into client_team_assignments (client_id, team_member_id, role, assigned_at)
  values (p_client_id, p_new_team_member_id, 'primary_csm', now())
  on conflict (client_id, team_member_id, role)
  do update set unassigned_at = null, assigned_at = now();
end;
$$;

comment on function change_primary_csm is
  'Atomic primary-CSM swap for the Gregory dashboard. Archives the existing active primary_csm assignment for the client and inserts (or reactivates) one for the new team_member. ON CONFLICT DO UPDATE handles the re-assignment-after-archival case where a previously-archived (client_id, team_member_id, primary_csm) row would otherwise collide on the UNIQUE constraint. Mirrors the M5.6 status cascade trigger''s primary_csm reassignment pattern (migration 0022). Originally introduced as 0014; replaced in 0023 to fix Bug 3 from the M5.6 visual smoke.';

-- Explicit grant for symmetry with the 0018+ RPCs. CREATE OR REPLACE
-- preserves existing permissions, but having the grant in the file makes
-- the permission boundary discoverable via grep without needing to know
-- the preservation rule.
grant execute on function change_primary_csm(uuid, uuid) to service_role;
