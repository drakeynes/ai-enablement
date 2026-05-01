# client_standing_history

Append-only audit trail for `clients.csm_standing` changes.

## Purpose

Preserve when a client moved between CSM-judgment standings (`happy`, `content`, `at_risk`, `problem`) so the dashboard's Lifecycle & Standing section can show a standing timeline and so CSM Co-Pilot can reason about standing trajectory. Same application-layer write pattern as `client_status_history`.

NOT seeded at migration time — `clients.csm_standing` has no values when migration `0017_client_page_schema_v1.sql` applies. The first rows land via the master sheet importer (`scripts/import_master_sheet.py`, Chunk C) which writes one history row per non-null `csm_standing` it sets.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `client_id` | `uuid` | FK → `clients.id`, not null. No cascade |
| `csm_standing` | `text` | Not null. Check constraint: `csm_standing in ('happy', 'content', 'at_risk', 'problem')` — matches the constraint on `clients.csm_standing` |
| `changed_at` | `timestamptz` | Default `now()` |
| `changed_by` | `uuid` | FK → `team_members.id`. Nullable for the same reasons as `client_status_history.changed_by` |
| `note` | `text` | Optional free-text reason. The importer uses this to tag rows seeded from the master sheet (e.g. `'master sheet import'`) |

## Relationships

- FK to `clients` (no cascade)
- FK to `team_members` via `changed_by`

## Populated By

- Master sheet importer (Chunk C) — first batch of rows; one per client whose `csm_standing` the importer sets
- Gregory dashboard's standing-edit endpoint (Chunk B) — every change writes both `clients.csm_standing` and a new row here

## Read By

- Gregory dashboard's Lifecycle & Standing section on `/clients/[id]` (standing timeline)
- Future CSM Co-Pilot for trajectory-aware reasoning (e.g. "this client has been at_risk for 6 weeks")

## Example Queries

Standing timeline for one client, newest first:

```sql
select csm_standing, changed_at, changed_by, note
from client_standing_history
where client_id = $1
order by changed_at desc;
```

Clients currently at_risk and how long they've been there:

```sql
select distinct on (client_id) client_id, csm_standing, changed_at,
       (now() - changed_at) as time_in_current_standing
from client_standing_history
order by client_id, changed_at desc;
```
