-- Seed: team_members
-- Agency-side humans (V1 manual seed). Safe to re-run — ON CONFLICT keeps
-- existing rows untouched so manual edits (slack_user_id population, metadata
-- tweaks) are preserved.
--
-- First names only where no last name was provided. Aleks is intentionally
-- NOT in this list. slack_user_id is null here; it gets populated later from
-- Fathom participant matching or manual admin edits.
--
-- The ON CONFLICT target includes the `where archived_at is null` predicate
-- because email uniqueness is enforced by a partial unique index (see
-- migration 0007_partial_unique_archival.sql), not a plain constraint.

insert into team_members (email, full_name, role, is_active, metadata)
values
  ('drake@theaipartner.io',   'Drake',         'engineering', true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('scott@theaipartner.io',   'Scott Wilson',  'leadership',  true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('lou@theaipartner.io',     'Lou Perez',     'csm',         true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('nico@theaipartner.io',    'Nico Sandoval', 'csm',         true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('nabeel@theaipartner.io',  'Nabeel Junaid', 'leadership',  true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('zain@theaipartner.io',    'Zain',          'ops',         true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('aman@theaipartner.io',    'Aman',          'sales',       true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('ellis@theaipartner.io',   'Ellis',         'ops',         true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb),
  ('huzaifa@theaipartner.io', 'Huzaifa',       'ops',         true, '{"seed_source": "manual_v1", "seeded_at": "2026-04-21"}'::jsonb)
on conflict (email) where archived_at is null do nothing;
