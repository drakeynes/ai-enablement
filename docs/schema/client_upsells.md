# client_upsells

One row per upsell sale to a client.

## Purpose

Track upsell revenue per client so the dashboard's Financials section can show all upsells alongside contracted revenue and arrears, and so CSM Co-Pilot has a clean source for "what has this client bought beyond the base program?" Populated initially by the master sheet importer (legacy upsells from the Active++ sheet); going forward, by the Gregory dashboard's add-upsell action.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `client_id` | `uuid` | FK → `clients.id`, not null, cascade delete |
| `amount` | `numeric(10, 2)` | Dollar amount. Nullable — master sheet rows often have free-text descriptions without amounts |
| `product` | `text` | What was sold. Nullable; the master sheet often lacks a clean product field |
| `sold_at` | `date` | Sale-close date. Nullable for the same reason as amount |
| `notes` | `text` | Free-text context. Captures the master sheet's raw text when amount/product cannot be parsed |
| `recorded_by` | `uuid` | FK → `team_members.id`. Null for legacy rows imported from the master sheet |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | Bumped by `client_upsells_set_updated_at` trigger |

## Relationships

- FK to `clients` (cascade delete — upsells are owned by their client; same pattern as `call_participants` / `call_action_items`)
- FK to `team_members` via `recorded_by`

## Populated By

- `scripts/import_master_sheet.py` (Chunk C) — parses the Active++ "Upsells (N2AN)" column, splits dollar-amount strings into `amount`, free-text without amounts goes into `notes`
- Gregory dashboard (Chunk B) — Financials section "add upsell" action, sets `recorded_by` to the acting team member

## Read By

- Gregory dashboard's Financials section on `/clients/[id]`
- Future CSM Co-Pilot for revenue-aware reasoning

## Example Queries

Upsells for one client, newest first:

```sql
select id, amount, product, sold_at, notes, recorded_by
from client_upsells
where client_id = $1
order by sold_at desc nulls last;
```

Total upsell revenue per client (excluding rows without amounts):

```sql
select client_id, sum(amount) as total_upsell_dollars
from client_upsells
where amount is not null
group by client_id
order by total_upsell_dollars desc;
```
