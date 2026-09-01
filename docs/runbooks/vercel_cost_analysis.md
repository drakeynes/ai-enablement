# Vercel cost analysis — what the bill is, how to re-run it, how to lower it

Written 2026-08-31 after investigating "why did Vercel cost ~$80 this pay period?". The numbers
below are a snapshot; the **commands** are the durable part — re-run them whenever the bill needs
explaining again.

## What the bill is made of (snapshot: July + August 2026)

Two components, team `success-projects-9dcde12c`, project `ai-enablement`:

1. **Seats — fixed, not usage.** Pro is $20/seat/month; the team has two members (the company
   owner account + Drake) → ~$40/month regardless of activity.
2. **Function Duration — the usage overage, and it's growing.** July: $41.89 effective /
   $20.82 billed after included-quota credits. Aug 1–29: $57.38 effective / $37.10 billed.
   Every other meter (invocations, bandwidth, observability, Fluid, builds) is under $2 combined.

("Effective" = list-price value of consumption; "billed" = what's charged after the plan's
included allotments. The invoice ≈ seats + the billed usage of the closed period.)

**Attribution: ~99.8% of function compute is the ingestion machine, ~0.2% is humans using the
dashboard.** 7-day GB-hour split at the time of writing (~403 GB-hr/month pace):
`meta_leads_sync_cron` 24% · `wistia_sync_cron` 19% · `ghl_sync_cron` 18% · `close_events`
(webhook) 10% · `outbound_facts_refresh_cron` 7% · `airtable_sync_cron` 5.5% ·
`typeform_sync_cron` 5% · everything else in the tail. All `/sales-dashboard` + Gregory page
traffic combined rounds to zero. "Only a couple of people use Gregory" is true and irrelevant —
the crons run 24/7 either way (eight of them every 15 minutes; see `cron_schedule.md`).

**Why the machine costs this much:** the Python functions run on the pinned legacy runtime
(`@vercel/python@4.3.1` in `vercel.json`), which bills **wall-clock GB-hours** — and sync crons
spend most of their wall-clock idle, waiting on Meta/GHL/Wistia/Close APIs. The compute is billed
while the function waits.

## How to re-run the analysis

Vercel CLI, logged in as a team member (`vercel whoami`). Dollar totals by billing period:

```bash
# Current billing period (periods start on the 1st):
vercel usage --scope success-projects-9dcde12c --json

# A specific closed period, split by project (seats show under "(unattributed)"):
vercel usage --scope success-projects-9dcde12c --from 2026-07-01 --to 2026-07-31 \
  --group-by project --json
```

Per-endpoint attribution of the Function Duration line (**gotcha: the default aggregation is
`avg` — pass `-a sum`** or the numbers are meaningless):

```bash
vercel metrics vercel.function_invocation.function_duration_gbhr \
  --project ai-enablement --scope success-projects-9dcde12c \
  --since 7d -a sum --group-by request_path --limit 30 --json
```

`vercel metrics schema` lists the other queryable metrics (invocation counts, active CPU, peak
memory, …). Seat count: the team members list in the Vercel dashboard, or
`GET https://api.vercel.com/v2/teams/{teamId}/members` with the CLI token.

## Levers to lower it (analyzed 2026-08; lever 1 APPLIED 2026-09-01)

**Plan of record + applied-status detail: `docs/future-plans.md` § "Vercel bill reduction".**
Applied 2026-09-01 (user-directed): cadence stretch on the heavy syncs, full GHL-sync removal,
and Drake's team seat removed (future re-runs of the analysis happen from the owner account).
Lever 2 (Fluid) remains open.

1. **Stretch cron schedules** — cheap, immediate, costs freshness. The big three
   (`meta_leads_sync` `*/15`, `ghl_sync` `*/15`, `wistia_sync` hourly) are ~61% of the line;
   halving their frequency roughly halves it. Business call — the DC dashboard's 15-minute
   freshness is a feature.
2. **Move the Python functions to Fluid Compute** — the structural fix. Fluid bills active CPU
   instead of wall-clock, so IO-bound syncs that idle on external APIs could get ~an order of
   magnitude cheaper on this line. Requires migrating off the pinned `@vercel/python@4.3.1`
   runtime config; treat it as a real migration (verify current Vercel guidance for Python on
   Fluid, then smoke one cron end-to-end in preview before touching the fleet). Note
   `vercel_python_bundle_size.md` for why the runtime config looks the way it does before
   changing it.

Lever 1 was applied 2026-09-01; lever 2 has not been.
