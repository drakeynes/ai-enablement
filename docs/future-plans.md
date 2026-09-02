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

1. **Historical backfill from the Google Sheet** — **switch date derived from data 2026-09-02:
   the Aman Typeform fell off a cliff Aug 29** (76–97 responses/day through Aug 28 → 1–2/day
   after), so the backfill window is only **~Aug 29 → Sep 2 go-live**. The degradation is
   visible in facts: cohort tf_answered coverage 84% on Aug 28 → ~8–10% Aug 31–Sep 2 (the
   residue = leads matching their own older Typeform responses + stragglers). Needs: the Sheet
   view link, a column↔payload-key mapping, then a one-shot script that replays rows as POSTs
   to the endpoint (or inserts via the parser) — idempotent either way. `--smoke` one row
   first, per house rule.
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

## 3. Restore the #cs-call-summaries Slack channel

> **Status: READY TO EXECUTE — everything verifiable tonight was verified 2026-09-01 evening;
> the remaining steps need only the owner Vercel login (Drake gets it 2026-09-02).**
> Working-system reference: `docs/runbooks/cs_call_summary.md` (message format, audit trail,
> debug table) and `docs/runbooks/fathom_webhook.md` (webhook registration history).

**Verified 2026-09-01 evening:**

- **The new Fathom API key WORKS** — live `GET /external/v1/meetings` returned 200; the account
  is actively recording (newest meeting 22:27 UTC same day, 10+ in the prior 7 days), so the
  outage-window recordings exist on Fathom's side and are backfillable. The key sits in Drake's
  local `.env.local` (`FATHOM_API_KEY`) — **local-only; if that file is lost, get the key again
  from Zain/Nabeel.** It is NOT in Vercel yet.
- **Backfill flood-guard shipped** (`cc8ec50`): `ingest_call(post_cs_summary=False)` from the
  daily sweep — swept/backfilled calls generate all data but never post to the CS channel (see
  the note in `cs_call_summary.md`). Deploy was still `pending` at session close — **confirm it
  reads `success` (GitHub commit ✓ on `cc8ec50`) before putting the key into Vercel.**
- Registration mechanics confirmed against the live API: **no list endpoint** (GET /webhooks
  404s, documented quirk); create = `POST /external/v1/webhooks` (exact body in
  `fathom_webhook.md` ~line 212) whose **response contains the new `whsec_…` signing secret**;
  the dead registration's id from the last rotation was `FTVBjD_JqTfjEzVA` (delete it if Fathom
  ever complains about a duplicate destination).
- **Deliberately NOT registered yet**: registering mints a new secret and starts deliveries
  immediately, which would all 401 against the stale `FATHOM_WEBHOOK_SECRET` in Vercel until the
  owner login can update it — a day of rejected deliveries risks Fathom auto-disable. Register
  and paste as one tight sequence instead.

**The go-live sequence (five minutes, with the owner Vercel login open):**

1. Register the webhook (`POST /external/v1/webhooks`, destination
   `https://ai-enablement-sigma.vercel.app/api/fathom_events`, body per the runbook); capture
   the returned webhook id + `whsec_…` secret.
2. Paste `FATHOM_API_KEY` (from `.env.local`) and `FATHOM_WEBHOOK_SECRET` (the fresh `whsec_…`)
   into Vercel env (Production) → **Redeploy**.
3. Verify: POST with a bad signature → 401; then the next real client call end-to-end:
   `webhook_deliveries` `source='fathom_webhook'` processed row → `cs_call_summary_slack_post`
   processed row → message in the CS channel.
4. Aftermath: the daily 08:00 UTC sweep quietly heals the newest 30 days at ≤50 calls/day (no
   channel posts); the older chunk (Jul 2 → early Aug) needs one supervised manual backfill run
   (lift the 30-day/50-call caps for one run, or a one-shot script) — schedule whenever.

### What broke (verified against the live DB 2026-09-01)

The channel is fed by a hook inside **Fathom ingestion** — `agents/gregory/cs_call_summary_post.py`,
fired from `ingestion/fathom/pipeline.py:ingest_call` for every `call_category='client'` call with
a usable review. No Fathom deliveries → no ingest → no posts. Evidence:

- Last `fathom_webhook` delivery: **2026-07-02 15:24 UTC** (14–20/day before that). Last ingested
  Fathom call started 2026-07-02. Last successful channel post: **2026-07-01**.
- The daily `fathom_cron` safety-net sweep has written **zero** audit rows since Jul 2 08:00 — it
  dies on the dead API key.
- The Slack side is healthy: `SLACK_CS_CALL_SUMMARIES_CHANNEL_ID` + `SLACK_BOT_TOKEN` are still
  set in Vercel, and the hook kept writing (correctly-skipped `malformed` / `no_summary_text`)
  audit rows when old TXT transcripts were re-ingested in mid-August — proving the code path still
  executes.
- Pre-outage volume: ~400 Fathom calls/month, **~210–225 client-category/month**. The gap
  (Jul 2 → restore date) is therefore roughly **~800 calls / ~430 client calls** as of Sep 1 and
  growing.
- Related but **separate** break, don't conflate: the `cs_missed_recording` cron's audit trail
  stopped 2026-07-24 — that one is the Google Calendar OAuth death (~Jul 20), a different
  credential (fix via `/api/auth/google/connect`).

### Restore steps

1. **From Nabeel: a working Fathom API key** (and pick a fresh `FATHOM_WEBHOOK_SECRET`). Confirm
   the Fathom workspace that records CS calls, and that the current Fathom plan still includes
   API + webhook access (find out *why* it died Jul 2 — key revoked vs plan/account change —
   because that decides whether it can die again).
2. Set `FATHOM_API_KEY` + `FATHOM_WEBHOOK_SECRET` in Vercel env, redeploy.
3. **Re-register the webhook via Fathom's API** (`POST /external/v1/webhooks`, destination
   `https://ai-enablement-sigma.vercel.app/api/fathom_events`) — it was re-registered via API
   before; `docs/runbooks/fathom_webhook.md` documents the exact call.
4. **Verify live end-to-end on the next real client call**: `fathom_webhook` processed row →
   `cs_call_summary_slack_post` processed row → message visible in the channel. If the Slack leg
   fails, the runbook's error table covers it (`not_in_channel` → `/invite` the bot, etc.).
5. **Backfill the gap** (Jul 2 → restore date) — this fills the DB/dashboards, *not* the channel:
   - The built-in daily sweep cannot do it alone: `api/fathom_backfill.py` caps lookback at
     `_MAX_LOOKBACK_DAYS = 30` and ingests `_MAX_INGESTS_PER_SWEEP = 50` per run. A ~2-month /
     ~800-call gap needs a dedicated run — repeated invocations with the window lifted, or a
     one-shot script. House rule: real-API `--smoke` on one record before the full run.
   - **Suppress the CS Slack hook during the backfill, or the channel gets ~430 stale summaries.**
     Backfill ingests are deliberately bit-for-bit identical to webhook ingests, and no suppress
     flag exists today. Smallest change: a `post_cs_summary: bool = True` param on `ingest_call`
     threaded from the backfill path (or an env kill-switch checked inside
     `maybe_post_cs_call_summary`). **Do not run the backfill before this exists.**
   - Cost: the pipeline auto-generates a Claude review per client call — expect the same order as
     the DC review backfill (471 reviews ≈ $13), so roughly **$10–30** plus embeddings.
6. After the backfill: spot-check the Gregory dashboard (calls list, client health) across the gap
   window, and confirm the daily `fathom_cron` writes audit rows again.

### Effort + what else comes back

Once credentials exist: env + webhook + live verification is **~an hour**; the suppression flag +
supervised backfill is **a few more hours**. Note the channel is just the visible symptom — the
entire Fathom-fed fulfillment side (call ingestion, summaries, reviews, Gregory scoring inputs)
has been blind since Jul 2, and this restore brings all of it back.
