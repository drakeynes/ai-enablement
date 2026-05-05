-- 0024_trustpilot_cascade_on_happy.sql
-- M5.7 — Trustpilot auto-switch on csm_standing → happy.
--
-- One-directional BEFORE UPDATE trigger on clients. Fires only when
-- csm_standing transitions TO 'happy' (OLD.csm_standing IS DISTINCT
-- FROM NEW.csm_standing AND NEW.csm_standing = 'happy'). Sets
-- clients.trustpilot_status = 'ask' so the next CSM glance at the
-- adoption section prompts a review request.
--
-- Implements Scott's Loom 2 ask: "when a client moves to happy, we
-- should ask them for a Trustpilot review." Mirrors the M5.6 cascade
-- pattern (migration 0022) — narrow trigger gated on a transition,
-- mutating the in-flight NEW row, no AFTER half because there's no
-- history table for trustpilot_status and no companion side effects.
--
-- ============================================================================
-- Trigger ordering vs M5.6 status cascade
-- ============================================================================
--
-- Postgres fires BEFORE-row triggers in alphabetical order by trigger
-- name. The M5.6 cascade trigger is named clients_status_cascade_before;
-- this one is clients_trustpilot_cascade_on_happy_before. Alphabetically
-- the status cascade fires first.
--
-- Edge case: a single UPDATE that flips both status to negative AND
-- csm_standing to 'happy' simultaneously. Trigger fire order:
--   1. clients_status_cascade_before fires (status moved negative).
--      Mutates NEW.csm_standing := 'at_risk'.
--   2. clients_trustpilot_cascade_on_happy_before's WHEN clause is
--      re-evaluated against the in-flight NEW row. NEW.csm_standing is
--      now 'at_risk', so NEW.csm_standing = 'happy' is FALSE. Trigger
--      does NOT fire. trustpilot_status stays untouched.
--
-- Net behavior: negative status dominates. A client moving negative
-- never gets a "ask for review" prompt even if the same UPDATE also
-- carried csm_standing='happy'. This matches the spirit of the M5.6
-- cascade ("safer to default off whenever unsure").
--
-- ============================================================================
-- Forward-only — no backfill
-- ============================================================================
--
-- Existing clients in csm_standing='happy' with a non-'ask' trustpilot
-- value stay where they are. The cascade is forward-only by design:
--   - A client already in 'happy' may have legitimately had trustpilot
--     set to 'yes' (review left), 'no' (declined), or 'asked' (ask
--     pending). Resetting them to 'ask' would erase that state.
--   - The trigger fires on TRANSITION to happy, not on PRESENCE in
--     happy. Backfilling would conflate the two.
--
-- The four trustpilot vocab values (migration 0020): yes / no / ask /
-- asked. The trigger writes 'ask' specifically — the "next CSM action:
-- ask this client for a review" state.

create or replace function clients_trustpilot_cascade_on_happy_before()
returns trigger
language plpgsql
as $$
begin
  NEW.trustpilot_status := 'ask';
  return NEW;
end;
$$;

comment on function clients_trustpilot_cascade_on_happy_before is
  'BEFORE UPDATE trigger function for the M5.7 trustpilot cascade. Sets clients.trustpilot_status = ''ask'' when csm_standing transitions to ''happy''. Gating happens in the trigger WHEN clause; this function just mutates the NEW row.';

create trigger clients_trustpilot_cascade_on_happy_before
  before update on clients
  for each row
  when (
    OLD.csm_standing is distinct from NEW.csm_standing
    and NEW.csm_standing = 'happy'
  )
  execute function clients_trustpilot_cascade_on_happy_before();
