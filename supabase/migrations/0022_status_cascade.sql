-- 0022_status_cascade.sql
-- M5.6 — DB-level status cascade.
--
-- When a client's clients.status moves to a negative value (ghost,
-- paused, leave, churned), a coordinated set of derived field changes
-- auto-fire in one transaction:
--
--   1. csm_standing → 'at_risk' (history row written, attributed to
--      Gregory Bot)
--   2. accountability_enabled → false
--   3. nps_enabled → false
--   4. primary_csm reassigned to "Scott Chasing" sentinel (existing
--      assignment archived, new one inserted/reactivated)
--   5. trustpilot_status — explicitly NOT touched
--
-- The cascade is one-directional (off-only) — there is NO symmetric
-- trigger for active. Per Scott's "safer to default off whenever
-- unsure" framing. CSMs can manually flip accountability_enabled or
-- nps_enabled back to true via the dashboard; if a future status move
-- back to negative re-fires the cascade, the manual override is NOT
-- sticky and gets flipped off again. The dashboard surfaces an active+off
-- amber hint so re-activations don't go un-noticed.
--
-- ============================================================================
-- Sentinel UUIDs (pinned literals; grep for the UUID to find call sites)
-- ============================================================================
--
--   Scott Chasing      ccea0921-7fc1-4375-bcc7-1ab91733be73   (this migration)
--   Gregory Bot        cfcea32a-062d-4269-ae0f-959adac8f597   (migration 0021)
--
-- Scott Chasing is a CSM placeholder — assignments to it land in the
-- regular client_team_assignments table with role='primary_csm', and
-- the team_members row carries is_csm=true so it appears in the dashboard
-- Primary CSM dropdowns alongside the four real CSMs. The
-- metadata.sentinel=true flag is the orthogonal "this is not a real
-- person" filter for any future "real team member" listing.
--
-- ============================================================================
-- Attribution pattern: GUC + structured note
-- ============================================================================
--
-- Cascade-induced client_standing_history rows are attributed to the
-- Gregory Bot UUID (the row was written by the trigger, not by a human).
-- The note column carries a structured format so a SQL query can join
-- cascade-induced rows back to the human who triggered them:
--
--   cascade:status_to_<status>:by:<uuid_or_NULL>
--
-- Examples:
--   cascade:status_to_paused:by:76357ccc-8628-4342-aa61-1f70047c1487
--      (Lou Perez moved a client to paused via the dashboard; her UUID
--       was set in app.current_user_id by the calling RPC)
--   cascade:status_to_ghost:by:NULL
--      (direct UPDATE via Studio with no session attribution, OR a
--       calling RPC that didn't set the GUC)
--   cascade:backfill:m5.6
--      (this migration's data backfill — distinct format because there's
--       no "transition status" semantically; we're backfilling current
--       negative-status rows to match the post-cascade shape)
--
-- The GUC is set by update_client_status_with_history (this file
-- replaces the 0019 version with the GUC-aware body). The trigger reads
-- via current_setting('app.current_user_id', true) — the second arg
-- returns NULL on missing-key rather than erroring. SET LOCAL via
-- set_config(...) is transaction-scoped; clears on COMMIT/ROLLBACK.
--
-- Sample audit-trail query (documented in gregory.md):
--
--   select c.full_name,
--          csh.changed_at,
--          split_part(csh.note, ':', 4) as triggered_by_user_uuid,
--          tm.full_name as triggered_by_name,
--          csh.csm_standing as cascade_set_to
--   from client_standing_history csh
--   join clients c on c.id = csh.client_id
--   left join team_members tm on tm.id::text = split_part(csh.note, ':', 4)
--   where csh.note like 'cascade:status_to_%'
--   order by csh.changed_at desc;

-- ===========================================================================
-- 1. Schema additions
-- ===========================================================================

-- 1a. clients.accountability_enabled, clients.nps_enabled
alter table clients
  add column accountability_enabled boolean not null default true,
  add column nps_enabled            boolean not null default true;

comment on column clients.accountability_enabled is
  'Whether accountability (DMs, nudges, automated check-ins) is active for this client. Cascade owns this for negative-status transitions: when status moves to ghost/paused/leave/churned, this auto-flips to false (see migration 0022 trigger). CSMs can manually flip back to true via the dashboard; the override is NOT sticky — a future status move back to negative re-fires the cascade and flips it off again. Distinct from clients.status: status is the operational state (paused = "on hold for legitimate reason"); accountability_enabled is a CSM-controlled gate on the automation layer regardless of status.';

comment on column clients.nps_enabled is
  'Whether NPS surveys go to this client. Same cascade semantics as accountability_enabled: auto-off on negative-going status transitions, manually flippable, override-NOT-sticky. The Airtable NPS Survery side is currently independent — flipping this to false in Gregory does not (V1) prevent Airtable from sending; Path 2 outbound writeback (deferred per future-ideas.md) will close that loop.';

-- 1b. team_members.is_csm
alter table team_members
  add column is_csm boolean not null default false;

comment on column team_members.is_csm is
  'Marks a team_member as eligible for primary_csm assignments. Surfaces in dashboard Primary CSM dropdowns (filter dropdown on /clients, swap dialog on /clients/[id]). Default false so non-CSM team_members (engineering, ops, sales) are excluded; flipping is_csm=true is an explicit choice. Orthogonal to the existing free-text role column — Scott Wilson and Nabeel Junaid carry role=leadership but is_csm=true because they actively own clients. The Scott Chasing sentinel carries is_csm=true so it appears in the dropdowns alongside the four real CSMs.';

-- 1c. Scott Chasing sentinel team_member
-- Same pattern as Gregory Bot (migration 0021): pinned UUID, system
-- email, metadata.sentinel=true. Differs from Gregory Bot in role+is_csm
-- because Scott Chasing functions as a CSM placeholder from the
-- dashboard's perspective — clients get assigned to it like any other
-- CSM.
insert into team_members (id, email, full_name, role, is_active, is_csm, metadata)
values (
  'ccea0921-7fc1-4375-bcc7-1ab91733be73'::uuid,
  'scott-chasing@theaipartner.io',
  'Scott Chasing',
  'csm',
  true,
  true,
  jsonb_build_object(
    'seed_source', 'migration_0022',
    'seeded_at', '2026-05-03',
    'sentinel', true,
    'purpose', 'primary_csm assignment target for clients in negative status (ghost/paused/leave/churned). Cascade trigger reassigns to this UUID. Distinct from a real CSM — clients here are "the system is chasing them," not "this person is actively managing them."'
  )
)
on conflict (id) do nothing;

-- ===========================================================================
-- 2. Update update_client_status_with_history to set the session GUC
-- ===========================================================================
-- Replaces the 0019 version. Same signature, same allowlist, same
-- idempotent no-op semantics. Adds a SET LOCAL of app.current_user_id
-- so the cascade trigger (created below) can attribute the row to the
-- human who triggered the status change. NULL p_changed_by leaves the
-- GUC unset; the trigger reads NULL and emits :by:NULL.
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

  -- Set the session-local GUC so the cascade trigger can read the
  -- changed_by UUID via current_setting('app.current_user_id', true).
  -- SET LOCAL via set_config is transaction-scoped; the trigger fires
  -- on the UPDATE below in this same transaction. NULL p_changed_by
  -- leaves the GUC unset; the trigger handles that via the missing_ok
  -- second argument to current_setting.
  if p_changed_by is not null then
    perform set_config('app.current_user_id', p_changed_by::text, true);
  end if;

  select status into v_current_status from clients where id = p_client_id;
  if not found then
    raise exception 'update_client_status_with_history: client not found (%)', p_client_id;
  end if;

  -- Idempotent no-op: nothing changed, no history row written. The
  -- cascade trigger also does not fire (its WHEN clause requires
  -- OLD.status IS DISTINCT FROM NEW.status, which is false here).
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
  'Atomic clients.status update + client_status_history insert. Idempotent when the new value equals the current value — no history row is written for a no-op edit. Called by the Gregory dashboard from Section 1 (Identity & Contact) of the client detail page (M4 Chunk B2). Allowlist expanded to include ''leave'' in 0019. Sets the app.current_user_id GUC for the M5.6 cascade trigger when p_changed_by is non-null (0022).';

grant execute on function update_client_status_with_history(uuid, text, uuid, text) to service_role;

-- ===========================================================================
-- 3. Cascade trigger functions
-- ===========================================================================

-- 3a. BEFORE UPDATE — mutate the in-flight NEW row.
-- The trigger's WHEN clause already filters to negative-going
-- transitions; this function just sets the cascade fields. No history
-- writes here — those happen in the AFTER variant.
create or replace function clients_status_cascade_before()
returns trigger
language plpgsql
as $$
begin
  NEW.csm_standing           := 'at_risk';
  NEW.accountability_enabled := false;
  NEW.nps_enabled            := false;
  return NEW;
end;
$$;

comment on function clients_status_cascade_before is
  'BEFORE UPDATE half of the M5.6 status cascade. Mutates the in-flight NEW row to set csm_standing=''at_risk'', accountability_enabled=false, nps_enabled=false. Fires only on negative-going transitions (gated by the trigger WHEN clause). The post-write side effects (history row + primary_csm reassignment) live in clients_status_cascade_after.';

-- 3b. AFTER UPDATE — write history row + reassign primary_csm.
create or replace function clients_status_cascade_after()
returns trigger
language plpgsql
as $$
declare
  v_changed_by_text text;
  v_changed_by_uuid uuid;
  v_current_primary uuid;
  v_scott_chasing   uuid := 'ccea0921-7fc1-4375-bcc7-1ab91733be73'::uuid;
  v_gregory_bot     uuid := 'cfcea32a-062d-4269-ae0f-959adac8f597'::uuid;
begin
  -- Read the GUC. The `true` second argument tells current_setting to
  -- return NULL on missing-key rather than erroring. Empty-string
  -- treated as NULL too (covers `set_config(_, '', _)` edge cases).
  v_changed_by_text := current_setting('app.current_user_id', true);
  if v_changed_by_text is null or v_changed_by_text = '' then
    v_changed_by_uuid := null;
  else
    -- Cast to uuid; an invalid UUID raises and the whole cascade aborts
    -- (transaction rolls back). Conservative: better to surface a bad
    -- GUC value loudly than to silently land :by:NULL when something
    -- upstream is buggy.
    v_changed_by_uuid := v_changed_by_text::uuid;
  end if;

  -- Always insert a standing history row attributed to Gregory Bot.
  -- Re-fires (negative→negative) deliberately get a row each time —
  -- the audit trail benefits from "the cascade fired again" being
  -- visible. The structured note carries the new status + the human
  -- attribution for SQL-side joining (see audit query in the migration
  -- header).
  insert into client_standing_history (
    client_id, csm_standing, changed_at, changed_by, note
  ) values (
    NEW.id,
    'at_risk',
    now(),
    v_gregory_bot,
    'cascade:status_to_' || NEW.status || ':by:' || coalesce(v_changed_by_uuid::text, 'NULL')
  );

  -- Look up the client's current active primary_csm.
  select team_member_id into v_current_primary
  from client_team_assignments
  where client_id = NEW.id
    and role = 'primary_csm'
    and unassigned_at is null
  limit 1;

  -- Reassign to Scott Chasing only when not already assigned to it. The
  -- "no-op when already Scott Chasing" path keeps the assignment table
  -- from churning rows on cascade re-fire (negative → another negative).
  if v_current_primary is null or v_current_primary <> v_scott_chasing then
    -- Archive any active primary_csm.
    update client_team_assignments
    set unassigned_at = now()
    where client_id = NEW.id
      and role = 'primary_csm'
      and unassigned_at is null;

    -- Insert a new active assignment to Scott Chasing.
    --
    -- ON CONFLICT explanation (the why, not the how):
    -- client_team_assignments has UNIQUE (client_id, team_member_id, role).
    -- The re-cascade case is the failure mode: a client cascades to
    -- Scott Chasing once, gets manually reassigned back to a real CSM
    -- by a CSM (the Scott Chasing row is now archived with
    -- unassigned_at != NULL), then status moves negative again and the
    -- cascade re-fires. A plain INSERT would error on the unique key
    -- because the (client, scott_chasing, primary_csm) row still exists
    -- (just archived). DO UPDATE reactivates it: clear unassigned_at,
    -- bump assigned_at to now() to reflect the fresh active assignment.
    -- The result is one row per (client, scott_chasing, primary_csm)
    -- that flips between active and archived as the cascade fires and
    -- the CSM re-assigns. History is preserved in the changed_at /
    -- assigned_at sequence on that single row's lifecycle.
    insert into client_team_assignments (client_id, team_member_id, role, assigned_at)
    values (NEW.id, v_scott_chasing, 'primary_csm', now())
    on conflict (client_id, team_member_id, role)
    do update set unassigned_at = null, assigned_at = now();
  end if;

  return NEW;
end;
$$;

comment on function clients_status_cascade_after is
  'AFTER UPDATE half of the M5.6 status cascade. Writes one client_standing_history row (attributed to Gregory Bot, with structured note carrying the new status + the human-attributed UUID from the app.current_user_id GUC). Reassigns primary_csm to Scott Chasing if not already assigned to it (idempotent no-op when already Scott Chasing; ON CONFLICT reactivates a previously-archived Scott Chasing assignment for the re-cascade case).';

-- ===========================================================================
-- 4. Create the triggers
-- ===========================================================================
-- Both triggers share the same WHEN clause: only fire on negative-going
-- transitions. NEW.status IN (negative set) AND OLD.status IS DISTINCT
-- FROM NEW.status. The IS DISTINCT FROM handles null safely (a NULL
-- status updated to 'paused' counts as a transition; this matches the
-- intuition that a brand-new client_status_history seed row exists for
-- every non-archived client per migration 0017's seed insert).

create trigger clients_status_cascade_before
  before update on clients
  for each row
  when (
    OLD.status is distinct from NEW.status
    and NEW.status in ('ghost', 'paused', 'leave', 'churned')
  )
  execute function clients_status_cascade_before();

create trigger clients_status_cascade_after
  after update on clients
  for each row
  when (
    OLD.status is distinct from NEW.status
    and NEW.status in ('ghost', 'paused', 'leave', 'churned')
  )
  execute function clients_status_cascade_after();

-- ===========================================================================
-- 5. Data backfill
-- ===========================================================================

-- 5a. Mark the four current CSMs (Scott Wilson, Nabeel, Nico, Lou) as
-- is_csm=true. Names match the live cloud team_members rows (verified
-- 2026-05-03). Scott Chasing is already is_csm=true from its INSERT
-- above. Everyone else stays at the default is_csm=false.
update team_members
set is_csm = true
where archived_at is null
  and full_name in (
    'Scott Wilson',
    'Nabeel Junaid',
    'Nico Sandoval',
    'Lou Perez'
  );

-- 5b. Backfill the cascade for clients currently in negative statuses.
-- The trigger does NOT fire here because the UPDATE doesn't touch
-- status (the trigger's WHEN clause requires OLD.status IS DISTINCT
-- FROM NEW.status). So we must:
--   (1) write history rows BEFORE the UPDATE, scoped to clients whose
--       csm_standing will actually flip (was-distinct-from at_risk)
--   (2) UPDATE the columns after
--
-- Primary_csm reassignment is INTENTIONALLY skipped for the backfill
-- per the M5.6 spec: clients with departed CSMs are currently
-- unassigned and that's fine; reassigning current-CSM-owned negative-
-- status clients to Scott Chasing as part of a one-shot migration is
-- a Big Behavioral Change Drake decides about manually post-apply.

insert into client_standing_history (
  client_id, csm_standing, changed_at, changed_by, note
)
select
  id,
  'at_risk',
  now(),
  'cfcea32a-062d-4269-ae0f-959adac8f597'::uuid,  -- Gregory Bot
  'cascade:backfill:m5.6'
from clients
where archived_at is null
  and status in ('ghost', 'paused', 'leave', 'churned')
  and csm_standing is distinct from 'at_risk';

update clients
set
  csm_standing           = 'at_risk',
  accountability_enabled = false,
  nps_enabled            = false
where archived_at is null
  and status in ('ghost', 'paused', 'leave', 'churned')
  and (
    csm_standing is distinct from 'at_risk'
    or accountability_enabled is distinct from false
    or nps_enabled is distinct from false
  );
