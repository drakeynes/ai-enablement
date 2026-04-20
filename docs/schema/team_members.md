# team_members

Agency-side humans — anyone who operates on behalf of the company.

## Purpose

Identify agency staff (CSMs, leadership, engineering, ops) so agents can attribute actions, route escalations, and tell a team @mention apart from a client @mention. The table is deliberately small: the job here is identity + role, nothing else.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `email` | `text` | Not null. Partial-unique where `archived_at is null`. Primary join key for inbound sources (Fathom, Slack Connect emails) |
| `full_name` | `text` | Not null |
| `role` | `text` | Free-form: `csm`, `leadership`, `engineering`, `ops` |
| `slack_user_id` | `text` | Partial-unique where `archived_at is null`. Slack `U...` id for mentions and matching |
| `is_active` | `boolean` | Default `true`. Cheap filter; `archived_at` is the durable signal |
| `metadata` | `jsonb` | Extensible blob for attributes we haven't promoted to columns |
| `created_at` | `timestamptz` | Default `now()` |
| `updated_at` | `timestamptz` | Default `now()`, bumped by trigger on update |
| `archived_at` | `timestamptz` | Soft delete; null = current |

## Uniqueness

`email` and `slack_user_id` are unique only among non-archived rows (see migration `0007_partial_unique_archival.sql`). That lets a former team member be re-hired and re-added without hitting a collision on the archived row.

## Relationships

- Referenced by `client_team_assignments.team_member_id`
- Referenced by `call_participants.team_member_id`
- Referenced by `call_action_items.owner_team_member_id`
- Referenced by `escalations.assigned_to` and `escalations.resolved_by`
- Referenced by `agent_feedback.provided_by`
- Referenced by `alerts.team_member_id`

## Populated By

- Manual seed for V1 (Scott, Lou, Nico, Drake, Nabeel, Zain)
- Later: programmatic sync from the CRM or an internal admin UI

## Read By

- Every agent (to identify who's acting and who to escalate to)
- CSM Co-Pilot (scorecards, ownership)
- Slack bot / Ella (distinguish team @mentions from client @mentions)
- HITL approval UI (list of possible assignees)

## Example Queries

Find the primary CSM assigned to a given client:

```sql
select tm.*
from team_members tm
join client_team_assignments a on a.team_member_id = tm.id
where a.client_id = $1
  and a.role = 'primary_csm'
  and a.unassigned_at is null;
```

Resolve a Slack user id to a team member:

```sql
select * from team_members
where slack_user_id = $1
  and archived_at is null;
```
