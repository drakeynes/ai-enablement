-- 0019_status_add_leave.sql
-- Expands the clients.status vocabulary to include 'leave' (a CSM decision
-- to let a client go ghost without chasing — distinct from 'churned' which
-- is post-program). New vocabulary: active, paused, ghost, leave, churned.
--
-- Two changes bundled so the dashboard's status-edit path stays coherent
-- across a single apply:
--   (1) Add the first DB-level check constraint on clients.status. Until
--       now the column was unconstrained — vocabulary was enforced only
--       application-side, in the update_client_status_with_history RPC
--       (from 0018) and the dashboard's filter chips.
--   (2) Replace update_client_status_with_history (from 0018) with the
--       new five-value allowlist. Without this, the dashboard would
--       reject 'leave' edits via the RPC's old hint message even though
--       the DB constraint accepts the value.
--
-- 'churned' is unchanged — NOT renamed. History is immutable: existing
-- client_status_history rows (recording any prior status value) remain
-- as-is. No data migration.

-- ---------------------------------------------------------------------------
-- New check constraint
-- ---------------------------------------------------------------------------
alter table clients
  add constraint clients_status_check
  check (status in ('active', 'paused', 'ghost', 'leave', 'churned'));

comment on column clients.status is
  'Operational status: active, paused, ghost, leave, churned. ''leave'' is a CSM decision to let a client go ghost without chasing — distinct from ''churned'' (post-program). Distinct from journey_stage which captures lifecycle bucket. Constraint added in 0019; previously enforced only application-side.';

-- ---------------------------------------------------------------------------
-- Replace update_client_status_with_history (from 0018) with the new
-- allowed-values list. Same signature, same body shape, same grant —
-- only the IN clause and hint string change. Other 0018 RPCs
-- (journey_stage, csm_standing, nps) are intentionally left alone.
-- ---------------------------------------------------------------------------
create or replace function update_client_status_with_history(
  p_client_id uuid,
  p_new_status text,
  p_changed_by uuid default null,
  p_note text default null
) returns clients
language plpgsql
security definer
as $$
declare
  v_current_status text;
  v_updated clients%rowtype;
begin
  if p_new_status is null
     or p_new_status not in ('active', 'paused', 'ghost', 'leave', 'churned') then
    raise exception 'update_client_status_with_history: invalid status %', p_new_status
      using hint = 'Allowed values: active, paused, ghost, leave, churned';
  end if;

  select status into v_current_status from clients where id = p_client_id;
  if not found then
    raise exception 'update_client_status_with_history: client not found (%)', p_client_id;
  end if;

  -- Idempotent no-op: nothing changed, no history row written.
  if v_current_status = p_new_status then
    select * into v_updated from clients where id = p_client_id;
    return v_updated;
  end if;

  insert into client_status_history (client_id, status, changed_at, changed_by, note)
  values (p_client_id, p_new_status, now(), p_changed_by, p_note);

  update clients set status = p_new_status where id = p_client_id
    returning * into v_updated;

  return v_updated;
end;
$$;

comment on function update_client_status_with_history is
  'Atomic clients.status update + client_status_history insert. Idempotent when the new value equals the current value — no history row is written for a no-op edit. Called by the Gregory dashboard from Section 1 (Identity & Contact) of the client detail page (M4 Chunk B2). Allowlist expanded to include ''leave'' in 0019.';

grant execute on function update_client_status_with_history(uuid, text, uuid, text) to service_role;
