# slack_channels

Slack channel metadata, mapped to clients where applicable.

## Purpose

Mirror every Slack channel we care about so agents can reason about scope (client vs. internal), privacy, and beta gating without calling Slack's API. `ella_enabled` is the pilot gate for Ella's answering behavior.

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `slack_channel_id` | `text` | Unique, not null. Slack `C...` id — stable across renames |
| `name` | `text` | Not null. Current channel name; may change |
| `client_id` | `uuid` | FK → `clients.id`. Null for internal channels |
| `is_private` | `boolean` | Not null |
| `is_archived` | `boolean` | Default `false` |
| `ella_enabled` | `boolean` | Default `false`. Beta gate — Ella only responds when true |
| `metadata` | `jsonb` | Extensible |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | Bumped by trigger |

## Relationships

- Logical join from `slack_messages.slack_channel_id` → `slack_channels.slack_channel_id` (text equality, not a FK — messages can land before the channel record is written)
- FK to `clients`

## Populated By

- Slack ingestion: bulk load on bot install, plus periodic refresh and `channel_created` / `channel_rename` / `channel_archive` event handlers

## Read By

- Ella (gates on `ella_enabled`; resolves `client_id` for scoping retrieval)
- Dashboards (channel → client views)

## Example Queries

Channels where Ella is enabled and a client is attached:

```sql
select sc.*, c.full_name
from slack_channels sc
join clients c on c.id = sc.client_id
where sc.ella_enabled = true
  and sc.is_archived = false
  and c.archived_at is null;
```

Resolve a Slack channel id to its client:

```sql
select client_id
from slack_channels
where slack_channel_id = $1;
```
