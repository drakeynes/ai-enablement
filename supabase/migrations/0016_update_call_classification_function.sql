-- 0016_update_call_classification_function.sql
-- Atomic edit of a call's classification fields (call_category,
-- call_type, primary_client_id) with per-field audit rows in
-- call_classification_history. Used by the Gregory dashboard's
-- Calls detail page Save button (M3.3).
--
-- Single transaction; same security definer + atomicity pattern as
-- merge_clients (0015) and change_primary_csm (0014).
--
-- Behaviors enforced server-side (the dashboard mirrors them in UX
-- but the function is the source of truth):
--
--   1. No-op silently when no incoming field differs from current.
--      Returns counts of zero — caller can show "no changes" and
--      exit edit mode.
--
--   2. When call_category changes to anything other than 'client',
--      primary_client_id is auto-cleared. Generates a separate
--      history row for the clear (honest audit trail; the user's
--      single click cascades into two recorded changes).
--
--   3. is_retrievable_by_client_agents is auto-derived: true iff
--      the resulting category='client' AND primary_client_id IS
--      NOT NULL. Not history-tracked; this is downstream of the
--      classification fields, not itself editable.
--
--   4. classification_method is set to 'manual' on any change. Not
--      history-tracked.
--
-- Returns jsonb summarizing what changed, for the dashboard toast.

create or replace function update_call_classification(
  p_call_id uuid,
  p_changes jsonb,
  p_changed_by uuid
) returns jsonb
language plpgsql
security definer
as $$
declare
  v_call calls%rowtype;
  v_new_category text;
  v_new_call_type text;
  v_new_primary_client_id uuid;
  v_should_auto_clear_primary boolean := false;
  v_new_retrievable boolean;
  v_fields_changed int := 0;
  v_history_rows int := 0;
begin
  select * into v_call from calls where id = p_call_id;
  if not found then
    raise exception 'update_call_classification: call not found (%)', p_call_id;
  end if;

  -- Resolve target values: take from p_changes if the key is present,
  -- otherwise hold current. nullif('') translates the dashboard's
  -- "Unknown" / "(unset)" empty-string convention into a real null
  -- for the call_type and primary_client_id paths.
  v_new_category := coalesce(p_changes->>'call_category', v_call.call_category);

  if p_changes ? 'call_type' then
    v_new_call_type := nullif(p_changes->>'call_type', '');
  else
    v_new_call_type := v_call.call_type;
  end if;

  if p_changes ? 'primary_client_id' then
    v_new_primary_client_id := nullif(p_changes->>'primary_client_id', '')::uuid;
  else
    v_new_primary_client_id := v_call.primary_client_id;
  end if;

  -- Server-side enforcement: a non-client category cannot carry a
  -- primary_client_id. If the user changed category to non-client,
  -- clear primary_client_id even if they didn't explicitly send it
  -- in p_changes — the auto-clear is recorded as its own history
  -- row below.
  if v_new_category <> 'client' and v_new_primary_client_id is not null then
    v_new_primary_client_id := null;
    v_should_auto_clear_primary := true;
  end if;

  -- Per-field history rows BEFORE the calls update so they reference
  -- the current (about-to-be-old) values. Insert order: category,
  -- call_type, primary_client_id — stable for any reader pulling the
  -- audit log.
  if v_new_category is distinct from v_call.call_category then
    insert into call_classification_history
      (call_id, changed_by, field_name, old_value, new_value)
    values
      (p_call_id, p_changed_by, 'call_category',
       v_call.call_category, v_new_category);
    v_history_rows := v_history_rows + 1;
    v_fields_changed := v_fields_changed + 1;
  end if;

  if v_new_call_type is distinct from v_call.call_type then
    insert into call_classification_history
      (call_id, changed_by, field_name, old_value, new_value)
    values
      (p_call_id, p_changed_by, 'call_type',
       v_call.call_type, v_new_call_type);
    v_history_rows := v_history_rows + 1;
    v_fields_changed := v_fields_changed + 1;
  end if;

  if v_new_primary_client_id is distinct from v_call.primary_client_id then
    insert into call_classification_history
      (call_id, changed_by, field_name, old_value, new_value)
    values
      (p_call_id, p_changed_by, 'primary_client_id',
       v_call.primary_client_id::text,
       v_new_primary_client_id::text);
    v_history_rows := v_history_rows + 1;
    v_fields_changed := v_fields_changed + 1;
  end if;

  -- No-op: nothing to update, nothing to revalidate.
  if v_fields_changed = 0 then
    return jsonb_build_object(
      'fields_changed', 0,
      'history_rows_written', 0,
      'auto_cleared_primary_client_id', false
    );
  end if;

  -- Auto-derive retrievability from the resulting state.
  v_new_retrievable := (
    v_new_category = 'client' and v_new_primary_client_id is not null
  );

  update calls
  set call_category = v_new_category,
      call_type = v_new_call_type,
      primary_client_id = v_new_primary_client_id,
      classification_method = 'manual',
      is_retrievable_by_client_agents = v_new_retrievable
  where id = p_call_id;

  return jsonb_build_object(
    'fields_changed', v_fields_changed,
    'history_rows_written', v_history_rows,
    'auto_cleared_primary_client_id', v_should_auto_clear_primary
  );
end;
$$;

comment on function update_call_classification is
  'Atomic edit of a call''s classification fields with per-field call_classification_history rows. Server-side enforcement: non-client category clears primary_client_id (separate history row); is_retrievable_by_client_agents auto-derived; classification_method auto-set to manual. See docs/agents/gregory.md M3.3 build log.';
