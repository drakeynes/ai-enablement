# Future plans

> The parking lot for **planned-but-not-started** work, one section per item. Each section carries
> enough scoping that whoever picks it up later (human or AI) can start without re-research —
> but always re-verify claims against the live code/DB first; these are point-in-time snapshots.
> Nothing here has a timeline or a commitment. When an item ships, delete its section and let the
> permanent docs (runbooks / schema / sales) take over.

Items:

1. [ClickFunnels forms — replace the DC Typeform](#1-clickfunnels-forms--replace-the-dc-typeform)
2. [Vercel bill reduction](#2-vercel-bill-reduction)

---

## 1. ClickFunnels forms — replace the DC Typeform

> **Status: PLANNED — not started, no timeline** (scoped 2026-08-31 from API-doc research plus a
> full code map of the Typeform integration). Nothing in the repo ingests ClickFunnels yet. Blocked
> on four inputs from Nabeel (see [Blocked on](#blocked-on-inputs-from-nabeel)). If/when this gets
> picked up: read this section, run the [discovery checklist](#discovery-checklist-do-this-first)
> before writing any adapter code, then follow `docs/runbooks/adding_new_ingestion_source.md`.

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

> **Status: ANALYZED 2026-08-29, deliberately not applied** — nobody has asked for the trade-off
> yet. The bill explanation and the commands to re-run the analysis live in
> `docs/runbooks/vercel_cost_analysis.md`; this section is the plan of record for acting on it.

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
