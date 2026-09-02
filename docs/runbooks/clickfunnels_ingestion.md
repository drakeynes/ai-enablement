# Runbook — ClickFunnels form-submission ingestion

Live since **2026-09-02**. The DC funnel's opt-in survey moved from Typeform to a ClickFunnels
form (~Sep 2026); this pipeline ingests those submissions **alongside** Typeform — both sources
land in the same tables and every downstream consumer (facts refresh, DC Setup, DC Ads surfaces)
reads them identically. Typeform ingestion is unchanged (`typeform_ingestion.md`).

## Architecture (event-driven — no cron)

```
CF form submit ──► CF workflow ──► Webhook step ──► POST /api/clickfunnels_events?secret=…
                       └─────────► Make.com hook ──► Google Sheet   (Zain's, independent leg)
```

- **Receiver** `api/clickfunnels_events.py`: auth = shared secret (`?secret=` query param or
  `X-Relay-Secret` header) constant-time-compared against `CLICKFUNNELS_WEBHOOK_SECRET`
  (Vercel env). 503 = env var missing; 401 = wrong secret. After auth: always-200 posture.
- **Phase 1 — capture (audit-first)**: raw payload upserted into `webhook_deliveries`
  (`source='clickfunnels_webhook'`, `webhook_id='clickfunnels_webhook:<sha256(body)[:16]>'`,
  status `received`). Identical retries dedupe on the body hash.
- **Phase 2 — normalize**: `ingestion/clickfunnels/pipeline.process_pending` (called inline,
  drains ≤20 per delivery) projects each capture into a `typeform_responses` row via
  `ingestion/clickfunnels/parser.py` and registers a `typeform_forms` definition row for new
  forms (that's what makes the form appear in the DC Setup pickers). Processing failures leave
  the capture row as the replay queue (`received`/`failed`) and heal on the next submission.

## The payload contract (set in the CF workflow's Webhook step)

One flat JSON object per submission. Load-bearing keys: `submitted_at`, `email`, `phone`
(E.164), `funnel` (label → our form id `cf:<slugified label>`), `has_budget_200` (the can-pay
answer, "Yes"/"No"), and the Meta attribution set `campaign_id`/`adset_id`/`ad_id`/`utm_*`/
`fbp`/`fbc`/`client_ip_address`/`event_id` (also `page_url`, `name`, `client_user_agent`).
**If fields are added/renamed in the workflow step, the parser must follow** — the mapping
lives in `parser.py` (`_HIDDEN_KEYS`, `_QUALIFY_SOURCE_KEY`).

Identity semantics:
- **Form id** = `cf:` + slugified `funnel` label (payload carries no CF form/page id). Renaming
  the funnel in ClickFunnels therefore MINTS A NEW FORM ID — re-attach it in DC Setup if that
  happens.
- **Response id** = `cf:<event_id>` (the LP's per-submission uuid), payload-hash fallback.

## Registration (how a form shows on the dashboards)

Same as Typeform: `dc_landing_pages.typeform_id` holds the `cf:` form id + `qualify_field_ref`
(`cf_has_budget_200`) + `qualify_answers` (`{Yes}`), edited via DC Setup → Landing pages
(admin guidance incl. funnel-ID-vs-form-ID: `dc_setup_admin.md` § Scenario 4). The first live
form was attached 2026-09-02: LP `go-lp-v2` → `cf:aman-vsl-funnel`; `dc_ads_campaigns`
`120251021193170748` aligned to match. `refresh_dc_ads_facts()` then matches responses to
leads by phone/email exactly as for Typeform (0154 CTEs — no SQL changes were needed).

## Monitoring / failure modes

| Symptom | Meaning | Fix |
|---|---|---|
| DC Setup **ClickFunnels health tile** stale (>12h) | The CF workflow webhook step died or the secret changed | Check the CF workflow with Zain; probe the endpoint (below) |
| POST → `503 receiver not configured` | `CLICKFUNNELS_WEBHOOK_SECRET` missing in Vercel | Set it + Redeploy |
| POST → `401 unauthorized` | URL secret ≠ Vercel secret | Align both sides |
| Capture rows stuck `received`/`failed` | Normalization failing (payload drift?) | Read `processing_error`; fix parser; set rows back to `received` — they drain on the next delivery |
| Rows `malformed` | Payload had no `submitted_at` or no email+phone | Check the workflow step's field mapping |
| Lead shows Partial though they submitted | Response landed after the last facts refresh (≤30 min lag), or phone/email mismatch vs Close | Wait a cycle; then compare `typeform_responses.answers` vs the Close lead's contacts |

Health probe: `GET https://ai-enablement-sigma.vercel.app/api/clickfunnels_events` → `200 ok`.
Missed-webhook recovery: the Google Sheet (Make leg) holds every submission independently —
cross-check and, if needed, replay by POSTing the missing rows to the endpoint with the secret.

## Env vars

`CLICKFUNNELS_WEBHOOK_SECRET` (Vercel + `.env.local`; also lives in the CF webhook step's URL —
rotate both together). `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` via `shared.db`.

## Tests

`tests/ingestion/clickfunnels/test_parser.py` — the payload fixture mirrors the first live
capture; update it if the workflow mapping changes.

## Still open (tracked in `docs/future-plans.md` §1)

Historical backfill from the Google Sheet (submissions between the Typeform switch and
2026-09-02 go-live), and the daily Close-divergence cross-check.
