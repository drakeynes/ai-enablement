-- 0014_change_primary_csm_function.sql
-- Atomic swap of a client's primary CSM. Archives the existing
-- primary_csm assignment (sets unassigned_at = now()) and inserts a
-- new active assignment for the new team member. Single transaction
-- so the client always has exactly one active primary CSM.

create or replace function change_primary_csm(
  p_client_id uuid,
  p_new_team_member_id uuid
) returns void
language plpgsql
security definer
as $$
begin
  -- Archive the current active primary CSM for this client (if any)
  update client_team_assignments
  set unassigned_at = now()
  where client_id = p_client_id
    and role = 'primary_csm'
    and unassigned_at is null;

  -- Insert new primary CSM assignment
  insert into client_team_assignments (client_id, team_member_id, role)
  values (p_client_id, p_new_team_member_id, 'primary_csm');
end;
$$;

comment on function change_primary_csm is
  'Atomic primary-CSM swap for the Gregory dashboard. Archives the existing active primary_csm assignment for the client and inserts a new active one. Preserves history per gregory.md detail view Section 3.';
