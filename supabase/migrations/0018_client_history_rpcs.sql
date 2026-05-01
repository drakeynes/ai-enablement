-- 0018_client_history_rpcs.sql
-- Atomic update + history-row insert RPCs for the M4 Chunk B2 client
-- detail page edit flows. Three functions mirror the application-layer
-- pattern documented in 0017_client_page_schema_v1.sql (status,
-- journey_stage, csm_standing) — the dashboard's edit endpoint calls
-- one of these and the function writes both the clients column AND
-- the corresponding history row in a single transaction. Plus a fourth
-- function for manual NPS-score entry from the dashboard.
--
-- Pattern follows change_primary_csm (0014), merge_clients (0015), and
-- update_call_classification (0016): plpgsql + security definer, single
-- transaction, idempotent-when-unchanged where applicable.
--
-- p_changed_by is nullable — auth context isn't wired through to the
-- Server Actions yet. Followup logged in docs/followups.md to populate
-- this once auth.users → team_members resolution lands.

-- ---------------------------------------------------------------------------
-- update_client_status_with_history
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
     or p_new_status not in ('active', 'paused', 'ghost', 'churned') then
    raise exception 'update_client_status_with_history: invalid status %', p_new_status
      using hint = 'Allowed values: active, paused, ghost, churned';
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
  'Atomic clients.status update + client_status_history insert. Idempotent when the new value equals the current value — no history row is written for a no-op edit. Called by the Gregory dashboard from Section 1 (Identity & Contact) of the client detail page (M4 Chunk B2).';

grant execute on function update_client_status_with_history(uuid, text, uuid, text) to service_role;

-- ---------------------------------------------------------------------------
-- update_client_journey_stage_with_history
-- ---------------------------------------------------------------------------
create or replace function update_client_journey_stage_with_history(
  p_client_id uuid,
  p_new_journey_stage text,
  p_changed_by uuid default null,
  p_note text default null
) returns clients
language plpgsql
security definer
as $$
declare
  v_current_journey_stage text;
  v_updated clients%rowtype;
  v_found boolean;
begin
  -- No enum validation in V1 — journey_stage is free-text until the
  -- taxonomy is finalized. A check constraint will be added later.
  -- Allow null to support "clear the journey stage" UX.

  select journey_stage, true into v_current_journey_stage, v_found
  from clients where id = p_client_id;
  if not v_found then
    raise exception 'update_client_journey_stage_with_history: client not found (%)', p_client_id;
  end if;

  -- Idempotent no-op: distinguish null-equals-null from string-equality.
  if v_current_journey_stage is not distinct from p_new_journey_stage then
    select * into v_updated from clients where id = p_client_id;
    return v_updated;
  end if;

  insert into client_journey_stage_history (
    client_id, journey_stage, changed_at, changed_by, note
  ) values (
    p_client_id, p_new_journey_stage, now(), p_changed_by, p_note
  );

  update clients set journey_stage = p_new_journey_stage where id = p_client_id
    returning * into v_updated;

  return v_updated;
end;
$$;

comment on function update_client_journey_stage_with_history is
  'Atomic clients.journey_stage update + client_journey_stage_history insert. Allows null to clear the field. Idempotent (uses IS NOT DISTINCT FROM so null-to-null is a no-op). Called by the Gregory dashboard from Section 2 (Lifecycle & Standing).';

grant execute on function update_client_journey_stage_with_history(uuid, text, uuid, text) to service_role;

-- ---------------------------------------------------------------------------
-- update_client_csm_standing_with_history
-- ---------------------------------------------------------------------------
-- Wrinkle: client_standing_history.csm_standing is NOT NULL (the column
-- comment explains this is intentional — history rows record an actual
-- standing). When the CSM clears the standing back to null, we update
-- clients.csm_standing to null but skip the history insert.
create or replace function update_client_csm_standing_with_history(
  p_client_id uuid,
  p_new_csm_standing text,
  p_changed_by uuid default null,
  p_note text default null
) returns clients
language plpgsql
security definer
as $$
declare
  v_current_standing text;
  v_updated clients%rowtype;
  v_found boolean;
begin
  if p_new_csm_standing is not null
     and p_new_csm_standing not in ('happy', 'content', 'at_risk', 'problem') then
    raise exception 'update_client_csm_standing_with_history: invalid csm_standing %', p_new_csm_standing
      using hint = 'Allowed values: happy, content, at_risk, problem (or null to clear)';
  end if;

  select csm_standing, true into v_current_standing, v_found
  from clients where id = p_client_id;
  if not v_found then
    raise exception 'update_client_csm_standing_with_history: client not found (%)', p_client_id;
  end if;

  -- Idempotent no-op (handles null=null and value=value).
  if v_current_standing is not distinct from p_new_csm_standing then
    select * into v_updated from clients where id = p_client_id;
    return v_updated;
  end if;

  -- Only write history when transitioning to a non-null value. Clearing
  -- the standing updates clients.csm_standing → null without producing
  -- a history row (the history table can't represent null).
  if p_new_csm_standing is not null then
    insert into client_standing_history (
      client_id, csm_standing, changed_at, changed_by, note
    ) values (
      p_client_id, p_new_csm_standing, now(), p_changed_by, p_note
    );
  end if;

  update clients set csm_standing = p_new_csm_standing where id = p_client_id
    returning * into v_updated;

  return v_updated;
end;
$$;

comment on function update_client_csm_standing_with_history is
  'Atomic clients.csm_standing update + client_standing_history insert. Allows null to clear the field; clearing skips the history insert because client_standing_history.csm_standing is NOT NULL by design. Idempotent. Called by the Gregory dashboard from Section 2 (Lifecycle & Standing).';

grant execute on function update_client_csm_standing_with_history(uuid, text, uuid, text) to service_role;

-- ---------------------------------------------------------------------------
-- insert_nps_submission
-- ---------------------------------------------------------------------------
create or replace function insert_nps_submission(
  p_client_id uuid,
  p_score integer,
  p_feedback text default null,
  p_recorded_by uuid default null
) returns nps_submissions
language plpgsql
security definer
as $$
declare
  v_inserted nps_submissions%rowtype;
begin
  if p_score is null or p_score < 0 or p_score > 10 then
    raise exception 'insert_nps_submission: score must be 0-10, got %', p_score;
  end if;

  -- Verify the client exists before insert (cleaner error than the FK
  -- violation that would otherwise bubble out).
  perform 1 from clients where id = p_client_id;
  if not found then
    raise exception 'insert_nps_submission: client not found (%)', p_client_id;
  end if;

  insert into nps_submissions (
    client_id, score, feedback, survey_source, submitted_at, recorded_by
  ) values (
    p_client_id, p_score, p_feedback, 'manual_dashboard_entry', now(), p_recorded_by
  ) returning * into v_inserted;

  return v_inserted;
end;
$$;

comment on function insert_nps_submission is
  'Manual NPS-score entry from the Gregory dashboard. Stamps survey_source = ''manual_dashboard_entry'' and submitted_at = now(). Validates 0-10 score range. Called by the Gregory dashboard from Section 2 (Lifecycle & Standing) "Add NPS score" inline form (M4 Chunk B2).';

grant execute on function insert_nps_submission(uuid, integer, text, uuid) to service_role;
