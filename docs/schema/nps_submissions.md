# nps_submissions

NPS scores and free-text feedback from clients.

## Purpose

Capture promoter/detractor signal as structured data so CSM Co-Pilot can factor NPS into health scoring and route detractors into alerts immediately.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `client_id` | `uuid` | FK → `clients.id`, not null |
| `score` | `integer` | Not null. 0-10, enforced by check constraint |
| `feedback` | `text` | Optional free-text comment |
| `survey_source` | `text` | `slack_workflow`, `typeform`, ... |
| `submitted_at` | `timestamptz` | Not null. When the client submitted |
| `ingested_at` | `timestamptz` | When we captured it |

## Relationships

- FK to `clients`

## Populated By

- Slack ingestion: when an NPS submission comes through the Slack Workflow form, ingestion lands both a `slack_messages` row (with `message_subtype = 'nps_submission'`) and an `nps_submissions` row
- Future survey-tool ingestions

## Read By

- CSM Co-Pilot (health score factor; detractor → `alerts` row)
- Dashboards (trailing NPS, promoter share)

## Example Queries

Most recent NPS per client:

```sql
select distinct on (client_id) client_id, score, feedback, submitted_at
from nps_submissions
order by client_id, submitted_at desc;
```

Detractors in the last 30 days:

```sql
select c.full_name, n.score, n.feedback, n.submitted_at
from nps_submissions n
join clients c on c.id = n.client_id
where n.score <= 6
  and n.submitted_at > now() - interval '30 days'
order by n.submitted_at desc;
```
