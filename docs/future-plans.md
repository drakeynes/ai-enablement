# Future plans

> The parking lot for **planned-but-not-started** work, one section per item. Each section carries
> enough scoping that whoever picks it up later (human or AI) can start without re-research —
> but always re-verify claims against the live code/DB first; these are point-in-time snapshots.
> Nothing here has a timeline or a commitment. When an item ships, delete its section and let the
> permanent docs (runbooks / schema / sales) take over.

Items:

1. [ClickFunnels forms — remaining work](#1-clickfunnels-forms--remaining-work-core-shipped-2026-09-02)
2. [Vercel bill reduction](#2-vercel-bill-reduction)
3. [Restore the #cs-call-summaries Slack channel](#3-restore-the-cs-call-summaries-slack-channel)

---

## 1. ClickFunnels forms — remaining work (core SHIPPED 2026-09-02)

> The forward path is **LIVE**: CF workflow webhook → `api/clickfunnels_events.py` → normalized
> into the `typeform_responses` mirror → facts refresh qualifies leads → DC Ads surfaces, with
> the first form (`cf:aman-vsl-funnel` on LP `go-lp-v2`) attached and its first live submitter
> verified `tf_qualified=true`. Typeform runs unchanged alongside. The permanent record is
> `docs/runbooks/clickfunnels_ingestion.md` (+ `dc_setup_admin.md` § Scenario 4, schema-doc
> notes). What remains here:

1. ~~Historical backfill from the Google Sheet~~ — **DONE 2026-09-02**: all 434 sheet rows
   (Aug 28 → Sep 2; sheet id `1JrvsOxiL76w_v32qwNHJffR7kSfzW6wBH8d2VIqTvP8`) replayed through
   the live endpoint via `scripts/backfill_clickfunnels_sheet.py` (kept for reuse — the sheet
   keeps logging, so it can patch any future webhook gap). Result: Sep-1 cohort tf_answered
   went 18 → **215/215**, qualified 12 → **160**; Aug-31 and Sep-2 similarly healed. Event-ID
   dedupe against live captures confirmed. Timestamp quirk documented in the script: the
   sheet's "Local Time" column is actually UTC ISO; "Time Lead Came In" is ET.
2. **Daily Close-divergence check** — the promised no-API safety net: compare new DC opt-ins in
   Close vs CF submissions received; alert on drift (piggyback an existing daily cron; the DC
   Setup ClickFunnels health tile added 2026-09-02 covers gross staleness already).
3. **Payload-drift watch** — the parser mirrors the workflow step's hand-mapped keys; if Zain
   edits the mapping, `tests/ingestion/clickfunnels/test_parser.py` + `parser.py` must follow.

---

## 2. Vercel bill reduction

> **Status: PARTIALLY APPLIED 2026-09-01** (user-directed): the schedule lever shipped —
> meta_leads/typeform/airtable/outbound_facts `*/15`→`*/30`, typeform_insights 4×/hr→hourly,
> wistia hourly→6-hourly, and the GHL sync removed entirely (~18% of the line; the planned GHL
> motion was dropped). Drake's team seat was also removed (~$20/mo; he works via Nabeel's seat
> now — **CLI access from Drake's machine is gone**, so future `vercel usage` checks run from
> Nabeel's account). Estimated combined effect: roughly half the Function Duration line + the
> seat. **Still open: the Fluid Compute migration below (lever 2).** The bill explanation and
> re-run commands live in `docs/runbooks/vercel_cost_analysis.md`.

The bill ≈ 2 Pro seats ($40/mo fixed) + the **Function Duration** usage line ($42 effective in
July, $57+ and rising in August). ~99.8% of the function compute is the cron/webhook ingestion
fleet (top burners: `meta_leads_sync` 24%, `wistia_sync` 19%, `ghl_sync` 18%, `close_events` 10%);
dashboard users round to zero. The Python functions bill **wall-clock** GB-hours on the pinned
legacy `@vercel/python@4.3.1` runtime while mostly idle-waiting on external APIs.

Two levers, independent, either can ship alone:

1. **Stretch cron schedules** — cheap, immediate, costs data freshness. The big three
   (`meta_leads_sync_cron` `*/15`, `ghl_sync_cron` `*/15`, `wistia_sync_cron` hourly) are ~61% of
   the line; halving their frequency roughly halves it. Business call — the DC dashboard's
   15-minute freshness is a feature, so get sign-off on the new cadence before editing
   `vercel.json` (and update `docs/runbooks/cron_schedule.md` in the same commit).
2. **Migrate the Python functions to Fluid Compute** — the structural fix. Fluid bills active CPU
   instead of wall-clock, so IO-bound syncs could get ~an order of magnitude cheaper on this line.
   Treat as a real migration: verify current Vercel guidance for Python on Fluid, read
   `docs/runbooks/vercel_python_bundle_size.md` for why the runtime config is pinned the way it
   is, smoke ONE cron end-to-end in a preview deploy, then roll the fleet. Verify the effect with
   `vercel usage` after a full day of production traffic.

---

## 3. Restore the #cs-call-summaries Slack channel — **DONE 2026-09-02**

> Fully restored and verified: Fathom webhook live (id `F8gszQFknRvwMtFN`, env vars under the
> `1`-suffixed names), receiver enforcing signatures, and the first summary **posted to the
> unarchived channel** (the channel had been archived during the outage — Zain unarchived it).
> Forward-only by user decision: no manual backfill of the Jul 2 → Aug outage window; the daily
> sweep silently heals the newest 30 days of dashboard data. Permanent record:
> `docs/runbooks/cs_call_summary.md` + `docs/runbooks/fathom_webhook.md` +
> `docs/runbooks/credentials-and-accounts.md` (env-var naming note). Known cosmetic residue: one
> pre-go-live call (`179301765`) repeatedly 504s at the gateway on re-delivery and never got a
> channel post — irrelevant under forward-only.
