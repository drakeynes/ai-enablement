# call_action_items

Action items extracted from call summaries.

## Purpose

Track follow-up commitments made on calls so CSM Co-Pilot can reason about accountability and so a future Task Management Agent has a clean source. Initially populated from Fathom's built-in action items; later enriched by Claude extraction on raw transcripts for higher quality.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `call_id` | `uuid` | FK → `calls.id`, not null, cascade delete |
| `owner_type` | `text` | `client`, `team_member`, `unknown` |
| `owner_client_id` | `uuid` | FK → `clients.id`. Set when `owner_type = 'client'` |
| `owner_team_member_id` | `uuid` | FK → `team_members.id`. Set when `owner_type = 'team_member'` |
| `description` | `text` | Not null |
| `due_date` | `date` | Optional |
| `status` | `text` | Default `open`. `open`, `done`, `cancelled` |
| `extracted_at` | `timestamptz` | When this action item was first extracted |
| `completed_at` | `timestamptz` | When it was marked done |

## Relationships

- FK to `calls` (cascade delete)
- FK to `clients`, `team_members` (owner resolution)

## Populated By

- Fathom ingestion (Fathom returns its own action items via API)
- Later: Claude-based re-extraction on `calls.transcript` when we want higher-quality items

## Read By

- CSM Co-Pilot (accountability tracking)
- Future Task Management Agent

## Example Queries

Open action items owned by a client, sorted by due date:

```sql
select description, due_date, extracted_at
from call_action_items
where owner_client_id = $1
  and status = 'open'
order by due_date nulls last;
```

Overdue items across all clients:

```sql
select ai.id, c.full_name, ai.description, ai.due_date
from call_action_items ai
join clients c on c.id = ai.owner_client_id
where ai.status = 'open'
  and ai.due_date < current_date
order by ai.due_date;
```
