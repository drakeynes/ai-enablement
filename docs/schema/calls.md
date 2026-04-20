# calls

One row per recorded call. Source-agnostic, but Fathom is the only producer today.

## Purpose

Canonical record of every call we've ingested, with safety classification baked into the schema. `call_category` and `is_retrievable_by_client_agents` together enforce that client-facing agents never surface content from internal or unclassified calls.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `external_id` | `text` | Unique, not null. Source-system call id |
| `source` | `text` | Default `fathom`. Supports adding `gong`, `zoom`, etc. later |
| `title` | `text` | Optional |
| `call_category` | `text` | Not null. `client`, `internal`, `external`, `unclassified`, `excluded` |
| `call_type` | `text` | Sub-type: `sales`, `onboarding`, `csm_check_in`, `coaching`, `team_sync`, `leadership`, `strategy`, `unknown` |
| `classification_confidence` | `float` | 0-1 confidence in `call_category` |
| `classification_method` | `text` | `participant_match`, `title_pattern`, `llm_classified`, `manual` |
| `primary_client_id` | `uuid` | FK → `clients.id`. Set for client calls |
| `started_at` | `timestamptz` | Not null |
| `duration_seconds` | `integer` | |
| `recording_url` | `text` | |
| `transcript` | `text` | Full transcript. Not indexed into `document_chunks` |
| `summary` | `text` | Cleaner, high-signal version — this is what gets chunked into `documents` |
| `is_retrievable_by_client_agents` | `boolean` | Default `false`. **Hard safety gate** |
| `raw_payload` | `jsonb` | Not null. Full source API response |
| `ingested_at` | `timestamptz` | Default `now()` |

## Category Semantics

- `client` — call with one or more known clients. Retrievable by Ella, scoped to those clients.
- `internal` — team-only. Never retrievable by Ella or other client-facing agents.
- `external` — non-client outsiders (vendors, unconverted prospects). Not indexed by default.
- `unclassified` — couldn't determine. Held for human review; no retrieval.
- `excluded` — personal or irrelevant; skipped from retrieval and future re-ingestion attempts.

## Safety Gate

`is_retrievable_by_client_agents` defaults to `false`. Client-facing agents **must** filter on this being `true`. It is flipped on only after confident classification as a `client` call for the matched client.

## Relationships

- FK to `clients` via `primary_client_id`
- Referenced by `call_participants.call_id` (cascade delete)
- Referenced by `call_action_items.call_id` (cascade delete)
- `documents` of type `call_summary` link back via `metadata.call_id`

## Populated By

- Fathom ingestion (webhook + periodic pull)
- Classification pass runs at ingestion: participant match → title pattern → LLM fallback

## Read By

- Ella (only `client` category, only for the matched client, only where `is_retrievable_by_client_agents = true`)
- CSM Co-Pilot (`client` + `internal` summaries for context)
- Future Sales Call Analysis, Executive Briefing agents

## Example Queries

Client calls retrievable by Ella for a given client:

```sql
select id, started_at, summary
from calls
where primary_client_id = $1
  and call_category = 'client'
  and is_retrievable_by_client_agents = true
order by started_at desc
limit 20;
```

Unclassified calls needing human review:

```sql
select id, title, started_at, classification_confidence
from calls
where call_category = 'unclassified'
order by started_at desc;
```
