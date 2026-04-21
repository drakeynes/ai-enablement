# Runbook: Seed Clients from the Financial Master Sheet

How to populate `clients`, `slack_channels`, and `client_team_assignments` from the Financial Master Sheet. Also covers the re-import loop when the sheet gets a new export.

## What counts as a client (V1 import rule)

The importer follows the sheet's **Active++ working view** as the canonical definition of "who is a client for V1":

- **USA TOTALS tab:** `Status ∈ {Active, Ghost, Paused, Paused (Leave)}`
- **AUS TOTALS tab:** `Status ∈ {Active, Paused}`

Anything else — `Churn`, `Churn (Aus)`, `N/A`, blank — **is not imported**. Excluded rows appear under "EXCLUDED BY ACTIVE++ FILTER" in the dry-run report so nothing silently disappears.

Why this filter: historical churn in the sheet predates the current team's ownership, the data quality is uncertain, and a confidently-wrong agent response about an ex-client is worse than no knowledge. Going forward, churn events will happen under current ownership with proper context and will be handled as a status update on an already-imported row (see "Churn after import" below).

## When to run

- First-time seed of a fresh Supabase project (local or cloud).
- Whenever the team produces a new Financial Master Sheet export (typically once per month).
- After fixing an Owner typo or adding missing data in the sheet, to refresh the DB.

## Prerequisites

- Local Supabase running (or cloud target with `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` set in `.env.local`).
- Migrations `0001`–`0009` applied.
- `team_members` already seeded (`supabase/seed/team_members.sql`) — the importer resolves Owner strings to `team_members.id`, so this must come first.
- Virtualenv active with `pip install -e '.[scripts]'` (brings in `openpyxl`).
- The XLSX file dropped at `data/client_seed/`. Filename doesn't matter — the importer auto-discovers the single `.xlsx` in that directory.

## Running

### Dry run (always first)

```bash
python scripts/seed_clients.py
```

Prints the full report to stdout. Writes nothing to the DB or to disk. The report covers:

- **Summary counts** — proposed clients / channels / assignments / skipped rows.
- **Skipped — missing email** — the list of rows ignored because `Client Emails` was blank (name, tab, row number).
- **Unmapped Owner values** — every distinct Owner string that didn't cleanly match one of our 5 mapped CSMs, with a row count. `Aleks`, `N/A`, and anything unfamiliar shows up here.
- **Messy Owner mappings** — Owner strings like `Lou (Scott Chasing)` or `Lou > Nico?` that mapped heuristically to the first-named team member. The full raw string will land in `client_team_assignments.metadata.raw_owner`.
- **Sheet email duplicates** — same email appearing on 2+ rows in the sheet. Flag to the sheet owner; last occurrence wins on `--apply`.
- **DB email collisions** — emails in the sheet that already exist as non-archived rows in `clients`. Non-zero means this is an update, not a fresh seed.
- **Random sample of 5 proposed clients** (plus a guaranteed AUS row if the random pick doesn't include one) showing the full payload: status, tags, metadata JSON. Use this to eyeball the transforms.

### Metadata keys written to `clients.metadata`

The importer writes exactly these five keys and nothing else:

- `seed_source` — constant `"financial_master_jan26"`
- `seeded_at` — ISO date the import ran
- `country` — `"USA"` or `"AUS"`
- `nps_standing` — raw NPS Standing cell, trimmed
- `owner_raw` — raw Owner cell, for audit

**Excluded by design:** revenue fields (`Contracted Rev`, `Contracted Rev AUD`, `Month N PP`) and the `Standing` column. Revenue data is stale; Standing reliability is unclear. See `docs/data-hygiene.md` for the rule.

### Tag derivation

- `promoter` — `NPS Standing` trimmed-lower equals `promoter`.
- `at_risk` — `NPS Standing` trimmed-lower equals `detractor / at risk`.
- `detractor` — same as `at_risk`.
- `aus` — source tab is AUS TOTALS.
- `churned` — defensive; does not fire under the Active++ filter.

`owing_money` and the Standing-derived half of `at_risk` were removed when Standing was marked unreliable.

### Apply

After reviewing the dry run:

```bash
python scripts/seed_clients.py --apply
```

Writes to the DB and drops an `import_<timestamp>.log` under `data/client_seed/` with the full dry-run report plus the apply summary plus post-apply breakdowns — status counts, journey_stage counts, and tag counts across all active clients. The breakdowns make it easy to spot a mapping drift at a glance (e.g. "status='active' dropped by 20 vs the prior run"). That log file is gitignored along with the rest of `data/`.

### Optional flags

- `--input <path>` — point at a specific XLSX instead of auto-discovering in `data/client_seed/`.

## Idempotency

Re-running `--apply` with the same sheet is safe:

- **`clients`** — matched by email (with `archived_at IS NULL`). Existing rows are updated; `created_at` and `archived_at` are never touched; `metadata` is **merged** so keys not present in the new row are preserved (enables hand-edits to stick through a re-import).
- **`slack_channels`** — `on_conflict=slack_channel_id` upserts; channel name and `client_id` refresh, other columns untouched.
- **`client_team_assignments`** — `on_conflict=(client_id, team_member_id, role)` with `ignore_duplicates=True`. Existing assignments are not overwritten, so manual reassignments stay put. To intentionally reassign, delete the old row first.

## Adding new clients

Two paths, in order of preference:

1. **Through the sheet (canonical).** Add the new client to the Financial Master Sheet, export a fresh XLSX, drop it at `data/client_seed/`, and re-run `python scripts/seed_clients.py` (dry run), then `--apply`. The sheet remains the source of truth.
2. **Direct one-off.** No dedicated tool today — see the deferred `scripts/add_client.py` entry in `docs/future-ideas.md`. For now, if a client needs to be added between sheet exports, the honest answer is either to update the sheet and re-import, or to run a hand-crafted `INSERT INTO clients ...` via Studio SQL Editor using the same transforms this importer uses.

### Sheet re-export workflow

1. Team updates the Master Sheet (new rows, status changes, Owner adjustments, NPS updates).
2. Export the workbook as `.xlsx`. File → Download → Microsoft Excel (.xlsx) from Google Sheets.
3. Move the export into `data/client_seed/`. **Remove any prior `.xlsx`** from that folder — the importer refuses to run if multiple `.xlsx` files are present (ambiguity), and the old file's data would no longer match the new source of truth.
4. Run the dry run. Compare counts to the prior run's log in `data/client_seed/import_<ts>.log` to sanity-check the delta.
5. Apply.

## Churn after import

Once a client has been imported, a subsequent churn event is handled **differently** from the initial filter:

- Update the `Status` in the sheet to `Churn` (or `Churn (Aus)`).
- Re-run `--apply`. The importer will detect that the client is no longer in the Active++ view and soft-archive the row: set `clients.archived_at = now()`, cascade `slack_channels.is_archived = true`, and end active `client_team_assignments` with `unassigned_at = now()`.
- The row stays in the DB; history is preserved. Agents stop retrieving it (partial unique on email is `WHERE archived_at IS NULL`, and channels filter on `is_archived = false`).
- Do not delete. Never delete.

## Common Fixes

**Owner column has an unmapped value.** Dry run shows it under "Unmapped Owner values" with zero assignment produced. Fix in the sheet (normalize to one of `Lou`, `Scott`, `Nico`, `Nabeel`, `Aman`, with optional messy suffix), re-export, re-run. If the raw value is informative (e.g. `Aleks` — no longer on team), leaving it unassigned is fine; the `clients` row still lands, just without a CSM.

**Typo in an email.** If the typo is in the sheet, fix the sheet and re-run — the importer will insert the corrected row as a new client (old row still exists with the typo'd email). You'll need to manually delete or archive the typo row afterward. If the typo is historical and already in the DB, an archival + re-import is the cleanest fix; otherwise update the row via Studio.

**Same email on multiple sheet rows.** The "Sheet email duplicates" section of the dry run lists these. Pick which row should win (usually the most recent or the one with better data), deduplicate in the sheet, re-run.

**DB has rows the sheet doesn't have.** Expected for any client who was archived manually between re-imports. The importer won't touch those rows (email matching is filtered on `archived_at IS NULL`). If a row is in the DB as non-archived but not in the sheet, the importer doesn't delete or archive it — intentional conservatism. Handle manually.

**Apply failed partway through.** The importer isn't wrapped in a transaction end-to-end (it's many small writes via supabase-py). Re-run after fixing the underlying cause; idempotency handles the partial state.

**Partial unique index confusion.** If you see `ON CONFLICT ... ambiguous` or similar from the underlying REST call, the `clients` upsert path is hitting an edge case with the partial unique index on `email WHERE archived_at IS NULL`. The current implementation works around this with a SELECT-then-INSERT-or-UPDATE pattern; if that breaks, we'd need a Postgres function (`upsert_client_from_import`) in a new migration. Flag before implementing.

## Adding the script to cloud

`supabase db push` doesn't run arbitrary scripts, only migrations. To seed cloud:

1. Set `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` in `.env.local` to the cloud values.
2. Run the dry run, same as local — verifies the sheet parses and counts line up.
3. Run `--apply`. All writes go through the REST API, which the service_role key authenticates against.
4. Verify counts in Studio (cloud Studio is reachable via the dashboard).

## Future

- `scripts/add_client.py` for one-off additions between sheet re-exports — see `docs/future-ideas.md`.
- Automated cloud seed application — see `docs/future-ideas.md`.
