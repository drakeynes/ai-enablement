-- 0020_trustpilot_rename_vocab.sql
-- Renames the clients.trustpilot_status vocabulary to match the
-- Financial Master Sheet vocab Scott uses daily. V1 scope reset
-- post-Scott 1:1: "match the master sheet so Scott adopts Gregory."
-- The DB now mirrors Scott's column values directly; the importer's
-- former master-sheet → old-DB translation collapses to identity in
-- the same logical chunk (scripts/import_master_sheet.py).
--
-- 1:1 mapping (no rows added or removed):
--   'given'     → 'yes'        (Trustpilot review left)
--   'declined'  → 'no'         (client said no)
--   'not_asked' → 'ask'        (semantic shift: descriptive → imperative;
--                               see comment below — 'ask' is "you should
--                               ask," not "we have not asked")
--   'pending'   → 'asked'      (asked, awaiting client action)
--
-- Pure structural rename — no logic changes, no auto-set rules, no
-- history table. Cleanup based on standing + tenure (clients who
-- shouldn't actually be in 'ask' state yet) happens later as a separate
-- manual pass per Drake's M5.3b scoping.
--
-- Order matters: DROP constraint → UPDATE → ADD constraint. The DROP
-- removes the old enum check so the UPDATE can write the new values
-- without violating the intermediate state. The ELSE clause on the
-- CASE preserves any unexpected value so the new ADD CONSTRAINT fails
-- loudly (constraint violation) rather than silently nulling a row —
-- defensive even though pre-apply distribution shows only the four
-- expected values + NULL.

-- ---------------------------------------------------------------------------
-- 1. Drop the existing CHECK constraint (auto-named in 0017).
-- ---------------------------------------------------------------------------
alter table clients drop constraint clients_trustpilot_status_check;

-- ---------------------------------------------------------------------------
-- 2. Rename the existing values 1:1.
-- ---------------------------------------------------------------------------
update clients
set trustpilot_status = case trustpilot_status
  when 'given'     then 'yes'
  when 'declined'  then 'no'
  when 'not_asked' then 'ask'
  when 'pending'   then 'asked'
  else trustpilot_status  -- defensive: preserve unexpected values so
                          -- the new constraint below fails loudly if
                          -- any pre-existing row is outside the old
                          -- vocab (shouldn't happen — old constraint
                          -- enforced — but the silent-null alternative
                          -- is a worse failure mode).
end
where trustpilot_status is not null;

-- ---------------------------------------------------------------------------
-- 3. Add the new CHECK constraint with the same name.
-- ---------------------------------------------------------------------------
alter table clients
  add constraint clients_trustpilot_status_check
  check (trustpilot_status is null or trustpilot_status in ('yes', 'no', 'ask', 'asked'));

-- ---------------------------------------------------------------------------
-- 4. Replace the column comment to reflect the new vocab + semantic
--    shift on 'ask'.
-- ---------------------------------------------------------------------------
comment on column clients.trustpilot_status is
  'Trustpilot review workflow state: yes (review left), no (client declined), ask (you should ask — call to action), asked (we asked, awaiting client). Imperative semantics on ''ask'' is intentional — distinct from the old descriptive ''not_asked'' which 0020 replaced. Vocabulary mirrors the Financial Master Sheet column Scott uses; matching it directly is part of the V1 adoption path. Constraint name unchanged: clients_trustpilot_status_check (renamed in place via 0020).';
