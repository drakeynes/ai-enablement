# client_health_scores

Computed client health scores, one row per client per computation run.

## Purpose

Historical record of how healthy each client looked at each computation. CSM Co-Pilot writes new rows on its schedule; dashboards render the latest row per client. Keeping the full history lets us audit decisions, review drift, and train better scoring rubrics over time.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `client_id` | `uuid` | FK → `clients.id`, not null |
| `score` | `integer` | 0-100, enforced by check constraint |
| `tier` | `text` | Not null. `green`, `yellow`, `red`. Derived from score + rules at compute time |
| `factors` | `jsonb` | Not null. Breakdown of signals, weights, contributions |
| `computed_at` | `timestamptz` | Default `now()` |
| `computed_by_run_id` | `uuid` | FK → `agent_runs.id`. Traceability back to the specific run |

## Relationships

- FK to `clients`
- FK to `agent_runs` (which run produced this score)

## Populated By

- CSM Co-Pilot on its schedule (nightly or as configured). Each scheduled invocation produces one row per active client.

## Read By

- CSM dashboards (latest per client, trend)
- Alerts pipeline (a drop in tier triggers an alert)

## Example Queries

Latest score per client (dashboard-style):

```sql
select distinct on (client_id) client_id, score, tier, computed_at
from client_health_scores
order by client_id, computed_at desc;
```

Tier changes in the last 7 days (possible alert source):

```sql
with latest as (
  select distinct on (client_id) client_id, tier, computed_at
  from client_health_scores
  order by client_id, computed_at desc
),
previous as (
  select distinct on (client_id) client_id, tier
  from client_health_scores
  where computed_at < now() - interval '7 days'
  order by client_id, computed_at desc
)
select l.client_id, p.tier as old_tier, l.tier as new_tier
from latest l
join previous p on p.client_id = l.client_id
where l.tier <> p.tier;
```
