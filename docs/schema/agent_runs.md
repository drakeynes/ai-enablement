# agent_runs

Every execution of every agent, logged.

## Purpose

The universal agent telemetry table. Every agent writes one row per run — success, failure, or escalation. Analytics, evals, debugging, cost tracking, and confidence monitoring all read from here.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `agent_name` | `text` | Not null. Canonical name: `ella`, `csm_copilot`, `sales_call_analysis`, ... |
| `trigger_type` | `text` | Not null. `slack_mention`, `schedule`, `webhook`, `manual` |
| `trigger_metadata` | `jsonb` | What triggered it (Slack event payload, cron info, etc.) |
| `input_summary` | `text` | Short human-readable input description |
| `output_summary` | `text` | Short human-readable output description |
| `status` | `text` | Not null. `success`, `escalated`, `error`, `skipped` |
| `confidence_score` | `float` | Optional, agent-reported |
| `llm_model` | `text` | `claude-sonnet-4-6`, `claude-opus-4-7`, ... |
| `llm_input_tokens` | `integer` | |
| `llm_output_tokens` | `integer` | |
| `llm_cost_usd` | `numeric(10, 4)` | |
| `duration_ms` | `integer` | |
| `error_message` | `text` | |
| `metadata` | `jsonb` | Extensible |
| `started_at` | `timestamptz` | Default `now()` |
| `ended_at` | `timestamptz` | Null while the run is in flight |

## Relationships

- Referenced by `escalations.agent_run_id`
- Referenced by `agent_feedback.agent_run_id`
- Referenced by `client_health_scores.computed_by_run_id`
- Referenced by `alerts.created_by_run_id`

## Populated By

- Every agent, via `shared/logging.py`. A run is opened at entry, updated on completion. Failures still get a row.

## Read By

- Analytics dashboards (volume, success rate, cost per agent)
- Eval runner (replay historical inputs)
- Cost attribution
- Debugging

## Example Queries

Per-agent run volume + error rate in the last 24 hours:

```sql
select agent_name,
       count(*) as runs,
       count(*) filter (where status = 'error') as errors,
       count(*) filter (where status = 'escalated') as escalations
from agent_runs
where started_at > now() - interval '24 hours'
group by agent_name
order by runs desc;
```

Cost by agent in the last week:

```sql
select agent_name,
       sum(llm_cost_usd) as total_cost,
       sum(llm_input_tokens) as input_tokens,
       sum(llm_output_tokens) as output_tokens
from agent_runs
where started_at > now() - interval '7 days'
group by agent_name
order by total_cost desc;
```
