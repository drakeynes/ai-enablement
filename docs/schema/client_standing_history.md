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
| `note` | `text` | Optional free-text reason. Carries multiple known formats — see § Note formats below |

## Note formats

`note` is unstructured free text by column type, but several producers write structured forms that downstream queries can parse. Documenting them here so future readers can see what conventions exist:

| Source | Format | Example |
|---|---|---|
| Master sheet importer (M4 Chunk C) | free text | `'master sheet import'` / `'import seed'` |
| Manual `update_client_csm_standing_with_history` RPC call (M4 Chunk B2) | free text or null | (whatever the dashboard passes — typically null in V1) |
| Airtable NPS auto-derive (M5.4) | structured | `'auto-derived from NPS segment promoter'` |
| M5.6 status cascade — transition-fired | structured | `'cascade:status_to_<status>:by:<uuid_or_NULL>'` |
| M5.6 status cascade — migration backfill | structured | `'cascade:backfill:m5.6'` |

The M5.6 cascade format is the most structured — colon-delimited so SQL `split_part(note, ':', N)` extracts each field. Position 4 is the human-attributed UUID OR the literal string `'NULL'`. Recovery query for "which human triggered each cascade":

```sql
select
  c.full_name,
  csh.changed_at,
  split_part(csh.note, ':', 4) as triggered_by_user_uuid,
  tm.full_name                  as triggered_by_name,
  csh.csm_standing              as cascade_set_to,
  csh.note
from client_standing_history csh
join clients c on c.id = csh.client_id
left join team_members tm on tm.id::text = split_part(csh.note, ':', 4)
where csh.note like 'cascade:status_to_%'
order by csh.changed_at desc;
```

Note: `split_part(note, ':', 4)` returns the literal string `'NULL'` (not SQL NULL) for cascade rows where no `app.current_user_id` GUC was set at trigger time (direct UPDATE via Studio, or a calling RPC that didn't propagate `p_changed_by`). The LEFT JOIN handles that gracefully — those rows show `triggered_by_name = NULL` because no UUID matches the literal string `'NULL'`. Future query convenience if the literal-NULL convention gets annoying: wrap with `nullif(split_part(note, ':', 4), 'NULL')` before the join.

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
