# Future plans

> The parking lot for **planned-but-not-started** work, one section per item. Each section carries
> enough scoping that whoever picks it up later (human or AI) can start without re-research —
> but always re-verify claims against the live code/DB first; these are point-in-time snapshots.
> Nothing here has a timeline or a commitment. When an item ships, delete its section and let the
> permanent docs (runbooks / schema / sales) take over.

Items:

1. [ClickFunnels forms — replace the DC Typeform](#1-clickfunnels-forms--replace-the-dc-typeform)
2. [Vercel bill reduction](#2-vercel-bill-reduction)
3. [Restore the #cs-call-summaries Slack channel](#3-restore-the-cs-call-summaries-slack-channel)

---

## 1. ClickFunnels forms — replace the DC Typeform

> **Status: PLANNED — not started, no timeline** (scoped 2026-08-31 from API-doc research plus a
> full code map of the Typeform integration; **transport settled 2026-09-01, see the update box
> below**). Nothing in the repo ingests ClickFunnels yet. If/when this gets picked up: read this
> section, run the [discovery checklist](#discovery-checklist-do-this-first) before writing any
> adapter code, then follow `docs/runbooks/adding_new_ingestion_source.md`.

### 2026-09-01 update — transport settled: webhook + Google Sheet (no API)

The account's ClickFunnels plan has **no API access**, so every API-based mechanism below
(list-endpoint backfill, reconcile poll, field-set fetch) is **reference-only unless the plan is
upgraded**. Workflow **webhooks ARE available** on their plan (verified in practice — Zain already
runs one), and Nabeel also has the submissions landing in a **Google Sheet**. The plan of record,
pending Nabeel's go-ahead (Zain would then create the webhook):

- **Live path**: a ClickFunnels workflow Webhook step POSTing each submission to our receiver
  (`api/clickfunnels_events.py`). Workflow-step POSTs may be unsigned — put a secret in the URL
  and validate payload shape.
- **Durable backlog**: the Google Sheet. It covers the two things the missing API cost us:
  the **historical backfill** (switch date → go-live) and **gap-patching** when the webhook
  misses deliveries. Read it via a poll cron (15–30 min) using a **dedicated Google service
  account** the sheet is shared with (NOT a publish-to-web CSV link — it's lead PII; and NOT the
  existing Google OAuth, which is the dead ~Jul-20 credential). Upsert key: submission timestamp
  + phone/email hash. Parser must be defensive: Sheets mangle phones/dates (populate as plain
  text), humans rename columns (validate headers), treat the sheet as append-only.
- **Monitoring** (replaces the API reconcile): staleness tile in DC Setup health (no new
  submission in N hours while ads run) + a daily divergence check against Close DC opt-ins,
  which we already mirror.
- **Field definitions**: no field-set API — derive the field inventory from observed payloads /
  sheet headers, or configure `qualify_field_ref` + `qualify_answers` manually once in DC Setup.
- **First discovery step becomes**: get one test submission flowing (webhook to a capture
  endpoint + a look at the Sheet's columns) and confirm phone, email, both scoring answers, and
  the hidden campaign/adset/ad ids all arrive.

**2026-09-01 later same day — the mechanism is known and the capture stub is live.** The flow is
**ClickFunnels workflow → Make.com inbound hook (Zain's, `hook.us2.make.com/…`) → Google Sheet.**
Hard requirement from the user: **the Sheet flow must keep working unchanged — we want BOTH
outputs.** So the wiring is additive: one HTTP "Make a request" module appended to the same Make
scenario **after** the existing Google Sheets module (sheet row is already written before our
module runs), with an **Ignore error handler** attached to our module so that even if our endpoint
is down/misconfigured, the scenario run still completes and never pauses — strictly zero risk to
the Sheet. The capture receiver is `api/clickfunnels_events.py` (`X-Relay-Secret` header vs
`CLICKFUNNELS_WEBHOOK_SECRET`; 503 until the env var is set in Vercel; captured payloads land in
`webhook_deliveries` `source='clickfunnels_webhook'`, status `received` — they double as the
replay queue for the future pipeline). Preferred wiring (user's call, later same day): Zain adds a **second Webhook step directly in the
ClickFunnels workflow** pointing at us — no Make change at all, the Make→Sheet leg untouched. The
secret then travels as `?secret=<value>` appended to the URL (the endpoint accepts header OR query
param). The Make-module route stays documented above as the fallback.

**End-of-day state 2026-09-01 — capture endpoint LIVE and verified** (deploy `success`; GET → 200
health, POST without secret → 503), handoff issued, waiting on people:

1. **Zain**: invents the secret, adds the second CF webhook step with URL
   `https://ai-enablement-sigma.vercel.app/api/clickfunnels_events?secret=<his value>` (POST,
   JSON, same trigger/payload as his existing Make webhook step), sends Drake the secret value.
2. **Drake (owner Vercel login)**: puts that same value in `CLICKFUNNELS_WEBHOOK_SECRET`
   (Production) + Redeploy, then gives Zain the go-ahead.
3. **Zain**: one test submission — success = `{"captured": true}`; `unauthorized` = secret
   mismatch; `receiver not configured` = env var not live yet.
4. Then: inspect the captured row (`webhook_deliveries` `source='clickfunnels_webhook'`) against
   the § contract (phone, email, both scoring answers, hidden ad ids) and build the real parser.
5. Still wanted independently: the **Google Sheet view link** (historical backfill + gap checks)
   and the **switch date**.

Everything else in this section (the contract in § "The contract the adapter must satisfy", the
storage decision, the registry wiring, the Blocked-on asks about question copy / hidden-field
passthrough / switch date) is transport-independent and stands unchanged.

### Why

The DC ads funnel is switching (per Nabeel, relayed 2026-08-29) from Typeform to **ClickFunnels
forms** for the post-opt-in survey. Until a ClickFunnels source ships, every lead who submits the
ClickFunnels form has **no matched survey response** on our side: they render as qualState
`partial`, get no Tier, and fall out of every qualified split (Q-speed boxes, HVC, the by-rep
Q/NonQ close rates from 0157). The longer the gap between the switch and the build, the larger the
backfill and the more degraded the DC dashboard's qualification columns. **The switch date is
therefore the first thing to pin down** — it is both the backfill window and the size of the
current blind spot.

Scope: **DC ads only.** The high-ticket side (`lead_cycles` via `shared/lead_tagging.py`,
`landing_page_forms`) stays on Typeform and is not part of this plan.

### What Typeform feeds today (the thing that must keep working)

Full detail: `docs/runbooks/typeform_ingestion.md`, `docs/schema/typeform_responses.md`,
`docs/schema/dc_ads_lead_facts.md`, and the current facts refresh in
`supabase/migrations/0154_dc_ads_lead_tier.sql`. The short version:

- `ingestion/typeform/` mirrors forms + responses into `typeform_forms` / `typeform_responses`
  (webhook `api/typeform_events.py` + `*/15` reconcile cron + backfill script — three converging
  idempotent paths, all upserting on the response id).
- `refresh_dc_ads_facts()` (0154) matches responses to `close_leads` by **phone (last 10 digits)
  and email (lower/trim)** — answer values first, `hidden->>'phone'` / `hidden->>'email'` as
  fallback — newest matching response wins. Campaign membership rides Close, never the form.
- From the matched response it derives `tf_qualified` (registry-driven:
  `dc_landing_pages.qualify_field_ref` + `qualify_answers`, exact choice-label equality),
  `tf_answered`, and `tf_experience` (hardcoded ILIKE on answer copy — see below).
- Downstream: qualState 3-state, Tier A–D, HVC, the Q-prefixed speed blocks, the 0157 by-rep
  close-rate trio, and the LP-summary submission counts (filtered by `hidden->>'ad_id'` etc.).

### ClickFunnels 2.0 API (verified from docs 2026-08-29 — NOT yet against the live workspace)

Docs index: <https://developers.myclickfunnels.com/llms.txt> (append `.md` to any doc URL).

- **Base URL** `https://{subdomain}.myclickfunnels.com/api/v2`. **Auth**: per-team Bearer token
  (created in the CF account settings). A **`User-Agent` header is required** — requests without
  one are rejected.
- **Two distinct form systems** with different resources. Which one the DC page uses decides the
  adapter shape:
  1. **Page forms** (forms embedded in funnel pages):
     `GET /workspaces/{workspace_id}/form_submissions` — every submission in the workspace, with
     `data` = flat map of HTML input name → submitted value (**hidden inputs included**), plus
     `page_id`, `contact_id`, `created_at`. Filterable by `id` / `page_id` / `contact_id` only.
  2. **Forms product** (standalone survey-style forms):
     `GET /forms/{form_id}/submissions` (id, form_id, contact_id, created_at) →
     `GET /forms/submissions/{submission_id}/answers` (field_id, fields_option_id(s), free-text
     `entry`) → `GET /forms/{form_id}/field_sets` for field/option labels. Contact PII comes from
     `GET` on the contact.
- **Pagination**: cursor by id (`after` param + `Pagination-Next` header), `sort_property` only
  `id` | `updated_at`. **No date filter** — a backfill walks the cursor and filters `created_at`
  client-side.
- **Webhooks**: registered via the API per workspace
  (`/workspaces/{id}/webhooks/outgoing/endpoints`, same manage-by-script pattern as
  `scripts/register_typeform_webhooks.py`). Event **`form_submission.created`** delivers the
  page-form `FormSubmission` payload; `contact.created/updated/identified` also exist. Signature
  verification is documented (`docs/signature-verification`). **No Forms-product submission event
  was found in the event list** — if the DC form is the Forms product, going-forward ingestion may
  be poll-only (a `*/15` cron, i.e. the same freshness we already accept from
  `typeform_sync_cron`).
- **Rate limiting**: "dynamic with a generous quota", no published numbers.

### The contract the adapter must satisfy

Condensed from the code map (verified 2026-08-29). The cheapest integration keeps
`refresh_dc_ads_facts()` and every dashboard surface untouched by normalizing ClickFunnels
submissions **into the exact response shape the tf CTEs read**:

1. **Row shape** (`typeform_responses`-equivalent): stable `response_id` PK, `form_id` (the
   attribution key joined against `dc_landing_pages`), **`submitted_at` (load-bearing — the
   newest-response-wins tie-break and every window filter)**, `answers` jsonb, `hidden` jsonb.
2. **`answers[]` element paths the SQL depends on** (0154:130–187):
   `a->>'type' = 'phone_number'` → `a->>'phone_number'`; `a->>'type' = 'email'` → `a->>'email'`;
   `a->'field'->>'ref'` matched against the registry's `qualify_field_ref`;
   `a->>'type' = 'choice'` with `a->'choice'->>'label'` for both scoring questions. ClickFunnels
   field identity (input names / field_ids) must be mapped into a stable `field.ref`.
3. **`hidden` keys**: `campaign_id` / `adset_id` / `ad_id` (LP-summary submission filtering +
   `typeform_id` majority-vote auto-resolution in `ingestion/meta_ads/leads_pipeline.py`), plus
   `phone` / `email` as identity fallbacks. These only exist if the CF page passes the Meta URL
   macros into the form — a **page-side prerequisite** (ask #3 below).
4. **Scoring questions**: qualify is registry-driven and survives label changes via DC Setup
   (`qualify_field_ref` + `qualify_answers`, exact equality — DC discriminator today:
   "Yes I can pay for the AI tools"). **`tf_experience` is NOT registry-driven**: 0154 hardcodes
   `ILIKE '%dabbled%' / '%used it a good amount%' / '%experienced ai pro%'`. Either the CF form
   reproduces that copy verbatim, or 0154's CASE gets a registry-backed rewrite in the same
   migration that admits the CF form.
5. **Form-definition rows** (`typeform_forms`-equivalent: fields with ref/title/type/choice
   labels) power the DC Setup qualify-question dropdowns
   (`lib/db/landing-page-assets.ts` → `getTypeformFields()`).
6. **Write-path guarantees**: idempotent PK upsert on all paths; webhook envelope id →
   `webhook_deliveries`; a reconcile cron whose `source` string is added to the DC Setup health
   tiles (`lib/db/dc-setup.ts`); post-upsert `refresh_dc_ads_facts()` (or let
   `outbound_facts_refresh_cron` `*/15` pick it up).

### Proposed design

- **`ingestion/clickfunnels/`** — `client.py` / `parser.py` / `pipeline.py`, mirroring
  `ingestion/typeform/` (stdlib urllib client, retry/429 handling, cursor walk with a safety max).
  The parser is where CF payloads become tf-shaped rows.
- **Storage — open decision, two options**:
  - (a) Normalize into the existing `typeform_forms` / `typeform_responses` tables with
    `cf:`-prefixed ids and a source marker in `metadata`. Zero SQL/TS changes downstream
    (~10 files read those tables); the table name becomes a lie — document it in the schema docs.
  - (b) Twin tables (`cf_form_submissions`, …) + rewriting the tf CTEs in a new facts-refresh
    migration to UNION both sources. Honest naming; touches 0154's successor plus every
    consumer enumerated in `docs/schema/dc_ads_lead_facts.md`.
  - Mild recommendation: **(a)** for speed and blast-radius, revisit if Typeform is ever fully
    retired.
- **Registry**: `dc_landing_pages.typeform_id` holds the CF form/page id for the LP (semantic:
  "the form this LP embeds"); rename to a neutral `form_id` only if doing option (b)'s honest
  pass. `qualify_field_ref` / `qualify_answers` get set through DC Setup as today.
- **Endpoints/crons**: `api/clickfunnels_events.py` (if the page-form webhook applies; HMAC verify,
  always-200 posture, audit row, `retag_by_contact` hook — clone the typeform receiver) +
  `api/clickfunnels_sync_cron.py` `*/15` + `scripts/backfill_clickfunnels.py` with
  `--smoke` / `--apply`. New rows in `vercel.json`, `docs/runbooks/cron_schedule.md`,
  `docs/runbooks/credentials-and-accounts.md` (token owner + rotation), a
  `docs/runbooks/clickfunnels_ingestion.md` runbook, and schema-doc updates — same commits as the
  code, per house rules.
- **Env vars**: `CLICKFUNNELS_API_TOKEN`, `CLICKFUNNELS_SUBDOMAIN` (or full base URL),
  `CLICKFUNNELS_WEBHOOK_SECRET`.

### Backfill

Window = switch date → now. Walk the submissions cursor ascending, filter `created_at >= switch
date` client-side, upsert, then run `refresh_dc_ads_facts()` once and verify the lead-roster
tier/qualState counts move. House rule applies: **real-API `--smoke` on one record end-to-end
against the real DB before `--apply`**.

### Discovery checklist (do this FIRST)

Per the discovery-before-build rule — no adapter code until one real authenticated call has been
inspected:

1. `GET /api/v2/teams` with the token (remember the `User-Agent` header) → team + workspace ids.
2. List forms / form_submissions in the workspace; fetch **one real submission from the live DC
   form** and answer: where do phone + email live? What are the `data` keys or field ids? Do the
   hidden `campaign_id`/`adset_id`/`ad_id` appear? What is the exact question + answer copy?
3. Confirm which form system the DC page uses (page form vs Forms product) — this decides
   webhook-vs-poll and which parser to write.
4. Register a webhook endpoint against a test URL and verify the signature scheme end-to-end.

### Blocked on (inputs from Nabeel)

Asked 2026-08-29:

1. A ClickFunnels **API token** + which team/workspace.
2. **Which funnel/page** hosts the new form, and the exact scoring-question copy (can-pay +
   AI-experience answers).
3. **Hidden-field passthrough**: the CF page must carry the Meta URL macros
   (campaign/adset/ad ids) into the submission, as the old LPs did for Typeform — a change for
   Nabeel's web person, without which new submissions lose LP-summary ad attribution (the old
   ~1-in-6 untagged caveat becomes ~all).
4. **The switch date** — backfill window, and the size of the dashboard gap accruing now.

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

> **Status: IN PROGRESS 2026-09-01 — the API key is in hand (Drake has it); the
> backfill-suppression flag is BUILT** (`ingest_call(post_cs_summary=False)` from the daily
> sweep — flood risk closed, so the key can go live safely). Remaining: key into `.env.local`
> (verify with one real call) → `FATHOM_API_KEY` + `FATHOM_WEBHOOK_SECRET` into Vercel via the
> owner login (Drake's seat is gone) → re-register the webhook → live verification → the
> beyond-30-days manual backfill (the daily sweep self-heals the newest 30 days at 50/day).
> Working-system reference: `docs/runbooks/cs_call_summary.md` (message format, audit trail,
> debug table) and `docs/runbooks/fathom_webhook.md` (webhook registration history).

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
