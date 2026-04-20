-- 0007_partial_unique_archival.sql
-- Replace full-table unique constraints on team_members and clients with
-- partial unique indexes scoped to archived_at IS NULL.
--
-- Reason: the inline `unique` constraints in 0001 apply to archived rows
-- too, which blocks re-adding a person with the same email / slack_user_id
-- after they've been soft-archived. Active-only uniqueness preserves the
-- real invariant (no two active records share the identifier) without
-- locking out legitimate rehires / re-enrollments.
--
-- slack_channels is intentionally left as-is. Channels use is_archived
-- (boolean), not archived_at, and reusing a Slack channel id is not a
-- real scenario — Slack allocates fresh ids on channel creation.

-- ---------------------------------------------------------------------------
-- team_members
-- ---------------------------------------------------------------------------
alter table team_members drop constraint team_members_email_key;
alter table team_members drop constraint team_members_slack_user_id_key;

create unique index team_members_email_active_idx
  on team_members (email)
  where archived_at is null;

create unique index team_members_slack_user_id_active_idx
  on team_members (slack_user_id)
  where archived_at is null and slack_user_id is not null;

-- ---------------------------------------------------------------------------
-- clients
-- ---------------------------------------------------------------------------
alter table clients drop constraint clients_email_key;
alter table clients drop constraint clients_slack_user_id_key;

create unique index clients_email_active_idx
  on clients (email)
  where archived_at is null;

create unique index clients_slack_user_id_active_idx
  on clients (slack_user_id)
  where archived_at is null and slack_user_id is not null;
