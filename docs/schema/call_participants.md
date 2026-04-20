# call_participants

Attendees of each call. Supports both internal team and clients.

## Purpose

Resolve every attendee email to either a client or a team member when possible. This is the signal that drives `calls.call_category` classification (participant matching is the strongest heuristic) and lets CSM Co-Pilot attribute calls correctly.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `call_id` | `uuid` | FK → `calls.id`, not null, cascade delete |
| `email` | `text` | Not null. Attendee email from the source system |
| `display_name` | `text` | |
| `client_id` | `uuid` | FK → `clients.id`. Null if not matched |
| `team_member_id` | `uuid` | FK → `team_members.id`. Null if not matched |
| `participant_role` | `text` | `host`, `attendee`, or source-provided role |

`UNIQUE (call_id, email)` — re-ingesting a call doesn't duplicate attendees.

If both `client_id` and `team_member_id` are null the email is unresolved (prospect, vendor, or simply not in our books yet).

## Relationships

- FK to `calls` (cascade delete)
- FK to `clients`
- FK to `team_members`

## Populated By

- Fathom ingestion: matches attendee emails to known clients/team at insert time

## Read By

- Call classifier (participant match → `call_category`)
- CSM Co-Pilot (attribute calls to clients for scoring)
- Ella (confirm a call belongs to the asking client)

## Example Queries

All calls a client attended in the last 90 days:

```sql
select c.id, c.started_at, c.title, c.summary
from calls c
join call_participants p on p.call_id = c.id
where p.client_id = $1
  and c.started_at > now() - interval '90 days'
order by c.started_at desc;
```

Unresolved attendees (rows we couldn't match — candidates for new client/team records):

```sql
select email, display_name, count(*) as call_count
from call_participants
where client_id is null
  and team_member_id is null
group by email, display_name
order by call_count desc;
```
