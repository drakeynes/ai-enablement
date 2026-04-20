# agent_feedback

Explicit and implicit human corrections of agent output.

## Purpose

Source of truth for building eval golden datasets. Every time a human corrects an agent — by clicking "this was wrong", by editing the agent's draft before sending, or by overriding an auto-action — a row lands here.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `agent_run_id` | `uuid` | FK → `agent_runs.id`, not null |
| `feedback_type` | `text` | Not null. `correction`, `thumbs_up`, `thumbs_down`, `edit`, `override` |
| `original_output` | `jsonb` | What the agent produced |
| `corrected_output` | `jsonb` | What the human thinks it should have been. Null for thumbs-style |
| `note` | `text` | Free-text reason |
| `provided_by` | `uuid` | FK → `team_members.id` |
| `created_at` | `timestamptz` | |

## Relationships

- FK to `agent_runs`
- FK to `team_members`

## Populated By

- HITL flows (resolution of escalations)
- Zain's QA work
- Slack thumbs-up/down actions on bot messages
- Dashboard edit/override buttons

## Read By

- Eval harness — turn corrections into regression examples
- Agent improvement workflows (prompt tuning, reward data)

## Example Queries

Recent thumbs-down events for a given agent:

```sql
select af.created_at, af.note, af.original_output, ar.input_summary
from agent_feedback af
join agent_runs ar on ar.id = af.agent_run_id
where ar.agent_name = $1
  and af.feedback_type = 'thumbs_down'
order by af.created_at desc
limit 50;
```

Corrections with both original and corrected (i.e., eval-ready pairs) for the last week:

```sql
select af.id, ar.agent_name, af.original_output, af.corrected_output, af.note
from agent_feedback af
join agent_runs ar on ar.id = af.agent_run_id
where af.feedback_type in ('correction', 'edit')
  and af.corrected_output is not null
  and af.created_at > now() - interval '7 days';
```
