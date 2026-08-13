# Runbook: Meta Lead-Form (Instant Form) Ingestion

Mirrors Meta lead-gen data — the **Digital College ads funnel** — into
Supabase. Since the full-program suspension (July 2026) the DC funnel has run
**two** acquisition paths:

| `source_kind` | Path | Status |
|---|---|---|
| `instant_form` | Meta ad → **Meta instant form** → Meta→Close bridge → reps dial | the original; its campaign has been **paused** since ~2026-07-25 |
| `landing_page` | Meta ad → **landing page** (`digitalcollege.ai`) → **Typeform** → Close → reps dial | live since 2026-07-22, the **active** motion |

Both are scoped by **`dc_ads_campaigns`** (migration 0130), which is what the DC
Ads page reads. Before 0130 only the instant-form path was scoped, so the
landing-page campaigns — including the only active one — were invisible on the
page along with ~$12.2k of spend. See `docs/schema/dc_ads_campaigns.md`.

## What this ingestion does

One pass (`ingestion/meta_ads/leads_pipeline.py :: sync_meta_leads`):

1. **Adset scan** — `GET /act_<id>/adsets`, filter to the instant-form
   discriminator (`optimization_goal=LEAD_GENERATION` +
   `destination_type=ON_AD`; website/landing-page campaigns are
   `OFFSITE_CONVERSIONS`) → upsert **`meta_leadgen_campaigns`**, mirrored into
   **`dc_ads_campaigns`** as `source_kind='instant_form'`.
1b. **Creative scan** (0130) — `GET /act_<id>/ads` with the creative's
   destination fields → upsert **`dc_ads_campaigns`** as
   `source_kind='landing_page'` for any campaign whose creatives point at a
   **`digitalcollege.ai`** host. Landing-page campaigns are otherwise
   indistinguishable from the unrelated ANDROMEDA / Closer Funnel campaigns on
   the same account, which point at `theaipartner.io` — so the match is on
   **host, never path** (`/training` exists on both). Runs in its own try block:
   a failure here can't cost the instant-form scope or the lead sync.

   `dc_ads_campaigns` is THE ad-spend scoping set for the DC ads funnel page:
   spend rows in `cortana_campaign_daily` whose `platform_entity_id` is in it
   count as DC ads spend.
1c. **Landing-page resolver** (0132) — `resolve_dc_landing_pages()`: normalizes
   each landing-page campaign's `destination_url` (`shared/lp_urls.py`) and
   (a) creates a `dc_landing_pages` row for any unseen URL (auto_created,
   label = short URL like `join/training`), (b) stamps
   `dc_ads_campaigns.lp_slug`, (c) resolves a missing LP `typeform_id` by
   majority vote over `typeform_responses.hidden->>'campaign_id'`. This is what
   makes a NEW funnel self-register on the DC Ads page — dropdown, spend scope,
   and (after the next facts refresh) funnel filtering, zero manual steps.
   Videos attach separately (Wistia embed scan, `docs/runbooks/wistia_ingestion.md`).
   Fail-soft in its own try block; outcome fields `lp_pages_created` /
   `lp_campaigns_linked` / `lp_typeforms_resolved` in the cron audit row.
   Curated registry fields are never overwritten — the resolver only fills
   nulls (lp_slug excepted: it follows the destination URL).
2. **Page token** — `GET /{page_id}?fields=access_token` with the user token.
   Lead reads are page-scoped; the page token is derived per run, never stored.
3. **Forms** — `GET /{page_id}/leadgen_forms` → upsert **`meta_lead_forms`**.
4. **Leads** — `GET /{form_id}/leads` per form (incremental via a
   `time_created GREATER_THAN` filter on the cron; full on backfill) → upsert
   **`meta_form_leads`**. Each lead carries `ad_id`/`adset_id`/`campaign_id`
   natively.
5. **Facts refresh** — `refresh_dc_ads_facts()` (migration 0123–0125) rebuilds
   `dc_ads_lead_facts` for the dashboard page.

## Schedule

- `api/meta_leads_sync_cron.py` — Vercel cron **every 15 min**
  (`vercel.json`), trailing 72h lead window. Audit rows:
  `webhook_deliveries` `source='meta_leads_sync'`.
- `api/outbound_facts_refresh_cron.py` (every 15 min) ALSO calls
  `refresh_dc_ads_facts()` so downstream stages (dials/bookings/closes from
  the Close + Airtable mirrors) stay fresh between lead syncs.

## Credentials (env vars)

`META_ACCESS_TOKEN` (user token — never-expiring since 2026-07-10; scopes
`ads_read`, `leads_retrieval`, `pages_show_list`, `pages_read_engagement`,
`pages_manage_ads`), `META_AD_ACCOUNT_ID`, `META_LEADGEN_PAGE_ID`
(The AI Partner = `627212320483048`), optional `META_API_VERSION`.
Local `.env.local` + Vercel Production. Token caveats (person-tied, rolling
data-access window): `meta_ads_ingestion.md` § warnings.

## ⚠ The 90-day retention clock

Meta only retains lead submissions ~**90 days** via the API. The mirror is
the durable copy. If the cron dies, fix it within that window or the oldest
opt-ins become unrecoverable (the backfill can only fetch what Meta still
has). The current form ("7/8 - Basic Form") collects **full_name +
phone_number only — no email**; phone is the identity key for these leads.

## Backfill

```bash
# one lead end-to-end (real API + real DB) — always run first
.venv/bin/python scripts/backfill_meta_leads.py --smoke
# everything Meta still retains, all forms, + facts refresh
.venv/bin/python scripts/backfill_meta_leads.py --apply
```

Idempotent (Meta-id upserts everywhere); safe alongside the cron.
First run 2026-07-10: 1 campaign, 1 form, 110 leads.

## Failure modes / debugging

- **`meta_leadgen_creds_missing` audit** — one of the three META_* env vars
  unset in Vercel.
- **Meta code 190 (`MetaAdsAuthError`)** — token revoked/expired → lead data
  freezes stale. See `meta_ads_ingestion.md` § token warnings.
- **Page-token step fails, adset scan succeeds** — pages permission problem
  (page removed from the Business, or token missing `pages_*` scopes);
  campaigns keep updating, leads stop.
- **Leads in Meta but missing in Close** — the Meta→Close bridge (not ours)
  broke; `meta_form_leads` keeps ingesting regardless. Compare
  `meta_form_leads` count vs `close_leads where funnel_name='Digital College'`
  — the DC ads page's opt-in count reads the Close-side facts, so a growing
  gap means the bridge needs fixing. **Split the gap by `form_id` first**:
  the bridge is subscribed PER FORM, so a brand-new instant form silently
  drops 100% of its leads until someone wires it. Happened 2026-07-13: the
  "7/13 - Basic Form" launched unwired and 67/78 of its opt-ins never became
  Close leads while the 7/8 form ran 232/232 clean. **Launching a new form ⇒
  wire the bridge to it the same day** (our mirror + form dropdown pick it up
  automatically; the bridge does not).
- **A new lead-form campaign shows no spend on the DC page** — check it
  appears in `meta_leadgen_campaigns` (adset scan runs every tick; the
  campaign must have at least one instant-form adset).
- **A new LANDING-PAGE campaign is missing entirely** (no leads, no spend,
  absent from the cascade dropdown) — check `dc_ads_campaigns` for a
  `source_kind='landing_page'` row. The creative scan only claims a campaign
  whose ad creatives resolve to a `digitalcollege.ai` host, so a campaign
  pointed at a NEW DC domain is invisible until that host is added to
  `DC_LANDING_HOSTS` in `ingestion/meta_ads/leads_parser.py`. This is the exact
  failure 0130 fixed — the whole page ran off a paused campaign for three weeks.
  Quick check: `select source_kind, count(*) from dc_ads_campaigns group by 1;`
- **Landing-page leads counted but the bridge-drift banner keeps firing** — the
  banner compares Meta-side instant-form submissions against
  `dc_ads_lead_facts` rows with `source_kind='instant_form'` ONLY. If it
  compares against the whole funnel it will always show a gap, because
  landing-page opt-ins never submit a Meta form.

## Table docs

`docs/schema/meta_lead_forms.md` · `docs/schema/meta_form_leads.md` ·
`docs/schema/meta_leadgen_campaigns.md` · `docs/schema/dc_ads_lead_facts.md`
