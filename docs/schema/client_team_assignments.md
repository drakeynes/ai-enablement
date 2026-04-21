# client_team_assignments

Many-to-many mapping of which team members serve which clients, and in what role.

## Purpose

A client may have a primary CSM and a secondary coach at the same time, and assignments change over time as people rotate. This table captures both the current assignment and the history. `unassigned_at` is the durable signal; `assigned_at` is when the assignment started.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `client_id` | `uuid` | FK → `clients.id`, not null |
| `team_member_id` | `uuid` | FK → `team_members.id`, not null |
| `role` | `text` | Not null. `primary_csm`, `secondary_csm`, `coach` |
| `assigned_at` | `timestamptz` | Default `now()` |
| `unassigned_at` | `timestamptz` | Null = currently active |
| `metadata` | `jsonb` | Not null, default `'{}'`. Assignment-level provenance (see below) |

`UNIQUE (client_id, team_member_id, role)` prevents duplicate active + historical rows for the same triple. If a person is reassigned in the same role after being removed, update `unassigned_at` rather than insert a duplicate, or use a new row only if history semantics require it (revisit if this constraint bites).

## Metadata

`metadata` captures assignment-level provenance without growing the column set. Conventions:

- `raw_owner` (string) — set by the clients importer when the source sheet's Owner column required heuristic parsing (e.g. `"Lou (Scott Chasing)"`, `"Lou > Nico?"`). The assignment row ends up linked to the first named team member; the raw string lives here so a human can audit the choice. Clean matches (`"Lou"`) do not set this key.
- Other keys may be added over time (e.g. `assigned_by`, `source`). Extension is cheap; rename/reshape is not, so prefer adding keys to renaming existing ones.

## Relationships

- FK to `clients` and `team_members`

## Populated By

- Manual seed for V1
- CRM ingestion later

## Read By

- Ella (to know which CSM to escalate to for a given client)
- CSM Co-Pilot (scorecards, alert routing)
- Dashboards (who-owns-what views)

## Example Queries

Current primary CSM for a client:

```sql
select tm.*
from client_team_assignments a
join team_members tm on tm.id = a.team_member_id
where a.client_id = $1
  and a.role = 'primary_csm'
  and a.unassigned_at is null;
```

All active clients for a CSM:

```sql
select c.id, c.full_name
from client_team_assignments a
join clients c on c.id = a.client_id
where a.team_member_id = $1
  and a.unassigned_at is null
  and c.archived_at is null
order by c.full_name;
```
