# dc_rep_coaching

Weekly per-rep AI coaching synthesis over the dc_ads-rubric call reviews
(migration 0152). One row per `(week_start, close_user_id)` — `week_start`
is the ET Monday of the covered week. Dashboard-only (no Slack); sales-side
isolation per 0054.

## Purpose

Nabeel's "Sales Rep Intelligence" ask: aggregate each rep's week of
reviewed calls (rep-execution scores, outcomes, the why-not-closed reasons
they hit, and the reviews' quote-evidenced strengths/weaknesses) into 2-3
concrete coaching recommendations. One Sonnet call per rep per week.

## Columns

`week_start` + `close_user_id` (PK) · `rep_name` (display fallback frozen
at generation; `team_members.full_name` when linked) · `calls_reviewed` ·
`avg_rep_score` (numeric 1dp) · `closes` · `strengths` / `weaknesses`
(jsonb — the week's `{point, evidence}` items carried from the reviews,
≤12 each) · `recommendations` (jsonb — `{focus, why, drill}` items, ≤3) ·
model/prompt/token/cost provenance · timestamps.

## Populated by / read by

- **Writes:** `agents/dc_intel/rep_coaching.py` `generate_rep_coaching()`,
  driven by `api/dc_rep_coaching_cron.py` (Mondays 08:45 UTC, covering the
  prior Mon–Sun ET week; idempotent per (week, rep), `?week=` / `?force=1`
  for manual runs).
- **Reads:** `getDcRepCoaching()` (`lib/db/dc-ads.ts`, newest week's rows)
  → the `DcRepCoachingSection` on `/sales-dashboard/dc-ads/calls`.

## Example query

```sql
select rep_name, calls_reviewed, avg_rep_score,
       jsonb_array_length(recommendations) as recs
from dc_rep_coaching where week_start = date_trunc('week', now())::date - 7;
```
