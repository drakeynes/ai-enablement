# client_status_history

Append-only audit trail for `clients.status` changes.

## Purpose

Preserve when a client moved between operational statuses (`active`, `paused`, `ghost`, `leave`, `churned` — `leave` added in 0019) and who made the change, so the dashboard's Lifecycle & Standing section can show a status timeline and so churn analysis has a clean source. Same application-layer write pattern as `client_team_assignments` — the dashboard's status-edit endpoint writes both `clients.status` and a new history row in the same transaction. Not trigger-based, so the audit logic stays visible in dashboard code.

Seeded at migration time (`0017_client_page_schema_v1.sql`) with one row per non-archived client whose `status` is non-null, using `clients.created_at` as `changed_at` and `'initial migration seed'` as the `note`.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `client_id` | `uuid` | FK → `clients.id`, not null. No cascade — preserve history if a client is ever hard-deleted (matches `client_team_assignments`) |
| `status` | `text` | Not null. The status value at the time of this row. Mirrors `clients.status` enum-by-convention; not constrained here so adding new status values does not require a migration |
| `changed_at` | `timestamptz` | Default `now()` |
| `changed_by` | `uuid` | FK → `team_members.id`. Nullable — auth.users → team_members join is best-effort in V1, and migration-seeded rows have no author |
| `note` | `text` | Optional free-text reason for the change. Used by the migration seed to mark seeded rows |

## Relationships

- FK to `clients` (no cascade)
- FK to `team_members` via `changed_by`

## Populated By

- Migration `0017_client_page_schema_v1.sql` seed — one row per non-archived client with non-null status
- Gregory dashboard's status-edit endpoint (Chunk B) — every status change writes both `clients.status` and a new row here in the same transaction

## Read By

- Gregory dashboard's Lifecycle & Standing section on `/clients/[id]` (status timeline)
- Future churn analysis / cohort reporting

## Example Queries

Status timeline for one client, newest first:

```sql
select status, changed_at, changed_by, note
from client_status_history
where client_id = $1
order by changed_at desc;
```

Clients who churned in the last 30 days:

```sql
select distinct on (client_id) client_id, changed_at
from client_status_history
where status = 'churned'
  and changed_at > now() - interval '30 days'
order by client_id, changed_at desc;
```
