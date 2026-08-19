# dc_intel — DC Ads intelligence synthesis

LLM-over-aggregates generators for the DC Ads dashboard (migration 0152,
Nabeel's build list 2026-08-18). Two outputs, both **dashboard-only** (no
Slack delivery by decision):

- **Exec summary** (`exec_summary.py` → `dc_ads_exec_summaries`) — daily.
  Context: the last 8 daily-table rows, the day's + trailing-7d
  `dc_ads_call_reviews()` aggregates, spend by day. Output: going_well /
  going_wrong / traffic_or_sales / changed — every item number-anchored
  and deliberately short (~15 words) by prompt contract; recent-cohort
  immaturity and small review-n are called out as grounding rules.
  (exec-v1 also emitted test_next — retired 2026-08-19, boss wanted the
  card shorter; the validator drops the key if a model still emits it.)
  Rendered as the card under the stage row on `/sales-dashboard/dc-ads`.
- **Rep coaching** (`rep_coaching.py` → `dc_rep_coaching`) — weekly, one
  Sonnet call per rep with reviewed dc_ads calls that week. Context: the
  rep's per-call scores/outcomes, why-not-closed tally, main objections,
  and the reviews' quote-evidenced strengths/weaknesses. Output: 2-3
  `{focus, why, drill}` recommendations, evidence-anchored, thin-sample
  hedged. Rendered on `/sales-dashboard/dc-ads/calls`.

## Inputs / outputs

Reads ONLY aggregates from Supabase (daily RPC, call-reviews RPC, review
rows, `cortana_campaign_daily`) — never raw transcripts, never external
APIs. Writes its own table + a `webhook_deliveries` audit row per cron
tick. Cost columns inline on each row (sales isolation, no `agent_runs`).

## Ops

- Crons (`vercel.json`): `api/dc_exec_summary_cron.py` daily 08:15 UTC
  (yesterday ET); `api/dc_rep_coaching_cron.py` Mondays 08:45 UTC (prior
  ET week). Both idempotent; `?force=1` + `?date=`/`?week=` for manual
  runs (`CRON_SECRET` Bearer).
- Failures: generation errors are caught, audited
  (`processing_status='error'`), and surfaced in the cron response — the
  dashboard simply keeps showing the previous row. No HITL escalation
  needed (display-only synthesis; wrong output is regenerated with
  `?force=1` after a prompt fix).
- Cost: ~$0.02/day (exec) + ~$0.02/rep/week (coaching) at Sonnet.

## Evals

`tests/agents/dc_intel/test_parsing.py` — parser/validation contracts
(shape, caps, fence-stripping, malformed-item handling). Prompt iteration
is direct; `prompt_version` on every row keeps output attributable.
