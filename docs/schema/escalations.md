# escalations

HITL escalations: when an agent defers to a human.

## Purpose

When an agent lacks confidence or an action requires human approval, it calls `shared/hitl.py` which creates a row here. The approval UI reads from this table, the human resolves it, and the resolution flows back. Rejected and edited escalations are gold for eval datasets.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `agent_run_id` | `uuid` | FK → `agent_runs.id`, not null |
| `agent_name` | `text` | Not null. Denormalized for fast filtering |
| `reason` | `text` | Not null. Human-readable reason for escalation |
| `context` | `jsonb` | Not null. Full context the reviewer needs |
| `proposed_action` | `jsonb` | What the agent wanted to do |
| `assigned_to` | `uuid` | FK → `team_members.id` |
| `status` | `text` | Default `open`. `open`, `approved`, `rejected`, `edited`, `expired` |
| `resolution` | `jsonb` | What the human actually decided (diffs cleanly against `proposed_action`) |
| `resolution_note` | `text` | Free-text explanation |
| `resolved_by` | `uuid` | FK → `team_members.id` |
| `resolved_at` | `timestamptz` | |
| `created_at` | `timestamptz` | |

## Relationships

- FK to `agent_runs`
- FK to `team_members` (twice: `assigned_to`, `resolved_by`)

## Populated By

- Any agent via `shared/hitl.py`

## Read By

- HITL approval UI (frontend + Slack)
- Eval dataset builders (rejected/edited escalations are training signal)
- Analytics (escalation rate per agent)

## Example Queries

Open escalations for a specific reviewer:

```sql
select id, agent_name, reason, created_at
from escalations
where assigned_to = $1
  and status = 'open'
order by created_at;
```

Escalation rate per agent in the last week:

```sql
select agent_name,
       count(*) as escalations,
       count(*) filter (where status = 'rejected') as rejected,
       count(*) filter (where status = 'edited') as edited
from escalations
where created_at > now() - interval '7 days'
group by agent_name
order by escalations desc;
```
