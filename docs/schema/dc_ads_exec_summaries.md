# dc_ads_exec_summaries

Daily AI executive summary for the DC Ads page (migration 0152). One row
per ET day; PK `for_date`. Dashboard-only by decision (Drake 2026-08-18) —
never posted to Slack. Sales-side isolation per 0054: no embeddings, not
retrievable by Ella; LLM cost columns inline, no `agent_runs` writes.

## Purpose

Nabeel's "Executive Intelligence" ask: the page answers what's going well /
what's going wrong / is it traffic or sales / what changed, generated
nightly from **aggregates only** (the daily-table rows, the
`dc_ads_call_reviews()` aggregates, spend) — never raw transcripts.

## Columns

`for_date` (date PK, the ET day summarized) · `summary` (jsonb —
`{going_well[], going_wrong[], traffic_or_sales, changed[]}`, short strings
validated by the generator, ≤4 items per list; **exec-v1 rows additionally
carry `test_next[]`**, retired 2026-08-19 with prompt exec-v2 for brevity —
the card never renders it) · `model` / `prompt_version` / `input_tokens` /
`output_tokens` / `cost_usd` (provenance + spend) · `created_at` /
`updated_at`.

## Populated by / read by

- **Writes:** `agents/dc_intel/exec_summary.py` `generate_exec_summary()`,
  driven by `api/dc_exec_summary_cron.py` (daily 08:15 UTC, summarizes
  yesterday ET; idempotent per date, `?force=1` regenerates, `?date=` for
  manual runs).
- **Reads:** `getDcAdsExecSummary()` (`lib/db/dc-ads.ts`) → the
  `DcAdsExecSummaryCard` on `/sales-dashboard/dc-ads` (newest row).

## Example query

```sql
select for_date, summary->>'traffic_or_sales'
from dc_ads_exec_summaries order by for_date desc limit 7;
```
