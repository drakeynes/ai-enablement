# Runbook: Fathom Webhook

Operational runbook for `api/fathom_events.py` — the Vercel serverless
endpoint that ingests Fathom `new-meeting-content-ready` deliveries. Full
design in `docs/architecture/fathom_webhook.md`.

**Status as of 2026-04-24 (F2.5 paused):** handler deployed, secret set,
webhook registered with Fathom via UI. End-to-end live-delivery
verification is **pending** — no real coaching call has finished Fathom's
post-processing since registration, so no delivery has been observed yet.
Nothing is wrong; just waiting for organic team-call traffic or a
deliberate test recording to exercise the path. See "Resume from F2.5
pause" below.

---

## Resume from F2.5 pause

**What's done (2026-04-24):**
- 7 commits pushed (`bc4cbbb..e9431da`) — the entire Fathom webhook stack,
  from architecture spec through handler + tests.
- Vercel build completed; `GET https://ai-enablement-sigma.vercel.app/api/fathom_events`
  returns `200 {"status":"ok","endpoint":"fathom_events","accepts":"POST"}`.
- Webhook registered with Fathom via the Fathom Settings UI (not via the
  `POST /webhooks` curl). Because Fathom UI registration doesn't surface
  the webhook `id` back to the user, **we don't have the webhook id
  captured**. This matters only for teardown — the id can be fetched via
  Fathom's list-webhooks API later if rotation or deletion is needed:
  `curl -sS -H "Authorization: Bearer $FATHOM_API_KEY" https://api.fathom.ai/external/v1/webhooks`.
- `FATHOM_WEBHOOK_SECRET` set in Vercel env vars (Production scope),
  redeploy done.

**What's NOT yet verified:**
- No `webhook_deliveries` rows have appeared since registration — cloud
  state at pause is exactly F1.4 baseline (516 calls, 685 documents,
  4,980 chunks, 134 clients, 0 webhook_deliveries, 0 call_action_items).
- Therefore: signature verification against Fathom's real signing hasn't
  been exercised live; the adapter hasn't seen a real payload shape;
  the full end-to-end chain hasn't reported a successful `processed` row.
- All four F2.1 open unknowns (webhook-id stability across retries,
  retry schedule, duplicate deliveries on summary regen, plan-tier
  gating) remain formally open, though plan-tier is effectively resolved
  since UI registration succeeded.

**How to resume — two options:**

### Option A — wait for organic team-call traffic

Once any team member records a Fathom call that matches the webhook's
`triggered_for` scope (set during UI registration — likely
`my_recordings` + `shared_team_recordings` per the runbook default), it
should fire to our endpoint ~2–5 minutes after the call ends. Check:

```sql
-- The "did anything land" query — run periodically until a row appears.
select webhook_id, processing_status, received_at, processed_at,
       call_external_id, processing_error
from webhook_deliveries
order by received_at desc
limit 10;
```

Expect first real delivery to show `processing_status='processed'` with a
`call_external_id` matching a Fathom `recording_id`. Downstream verify:

```sql
-- Immediately after the webhook lands, these should show the new call:
select id, external_id, title, call_category, primary_client_id,
       is_retrievable_by_client_agents
from calls
where external_id = '<recording_id from above>';

select document_type, is_active, jsonb_array_length(metadata->'participant_emails') as n_participants
from documents
where external_id = '<recording_id from above>';

-- Summaries + action items ride on the same delivery now
select count(*) from call_action_items
where call_id = (select id from calls where external_id = '<recording_id>');
```

### Option B — force a test recording

Record a Fathom meeting ≥90 seconds (talk to yourself, leave a
voicemail-style note, chat with a colleague — anything over the short-file
threshold). End the call. Wait ~3–5 min for Fathom's post-processing.
Then run the poll query above.

If nothing lands within ~15 minutes of the meeting ending:

1. **Check Fathom's processing status** — open the meeting in Fathom UI,
   confirm transcript + summary + action items all show as generated. If
   any are still "processing," the webhook fires when the last one is
   ready, not on call-ended.
2. **Check the webhook registration matches the call's scope** — in
   Fathom Settings → API Access → Webhooks, confirm the registered
   `triggered_for` includes the scope of the meeting you recorded. A call
   that's in `shared_external_recordings` won't fire a webhook registered
   only for `my_recordings`.
3. **Check for 401s in Vercel function logs** — bad signature is the
   only failure mode that does NOT leave a `webhook_deliveries` row. If
   you suspect a secret mismatch: Vercel dashboard → Functions →
   `api/fathom_events` → Logs. Look for lines matching
   `"fathom_webhook: signature verification failed webhook-id=..."`.
4. **Check the Fathom side's delivery history** — some providers log
   retries and response codes. If Fathom surfaces that, a streak of 401s
   or 500s tells us what's breaking from our end.

**No data loss risk while resuming slowly.** F2.6 (daily cron backfill)
will eventually catch any call the webhook missed — but the cron
doesn't exist yet. Until it does, a call that falls through a failed
webhook delivery is recoverable by the backlog re-run pattern in
`docs/runbooks/fathom_backlog_ingest.md` against an export including
that day.

---

## Deploy (executed 2026-04-24 as commit `e9431da`)

### 1. Add the handler to `vercel.json`

Append to the existing `functions` block and bump `maxDuration` if needed.
Example final shape:

```json
{
  "functions": {
    "api/slack_events.py":  { "runtime": "@vercel/python@4.3.1", "maxDuration": 60 },
    "api/fathom_events.py": { "runtime": "@vercel/python@4.3.1", "maxDuration": 60 }
  }
}
```

Commit + push; Vercel builds automatically on push if the project is linked
to the repo.

### 2. Verify the deploy picked up the new function

```bash
curl -i https://ai-enablement-sigma.vercel.app/api/fathom_events
# Expect: HTTP 200 + body {"status":"ok","endpoint":"fathom_events","accepts":"POST"}
```

If this 404s: the deploy didn't pick up the new function. Check the Vercel
dashboard → Functions tab; `fathom_events.py` should be listed. If not,
force a redeploy.

### 3. Generate the Fathom API key

One-time — from Drake's Fathom team account (NOT a personal account, NOT a
service account). Settings → API Access → Generate API Key. Capture
immediately — Fathom only shows it once. Store in Bitwarden as
`FATHOM_API_KEY_PROD`.

### 4. Register the webhook against the Vercel URL

```bash
curl -sS -X POST https://api.fathom.ai/external/v1/webhooks \
  -H "Authorization: Bearer <FATHOM_API_KEY_PROD>" \
  -H "Content-Type: application/json" \
  -d '{
    "destination_url": "https://ai-enablement-sigma.vercel.app/api/fathom_events",
    "triggered_for": ["my_recordings","shared_team_recordings"],
    "include_transcript": true,
    "include_summary": true,
    "include_action_items": true,
    "include_crm_matches": false
  }'
```

Response body contains the new webhook's `id` AND `secret` (format
`whsec_<base64>`). **The secret is returned ONCE and is not recoverable** —
capture immediately. Store in Bitwarden as `FATHOM_WEBHOOK_SECRET_PROD`.

### 5. Set the env var on Vercel + redeploy

In the Vercel dashboard → Project Settings → Environment Variables → add
`FATHOM_WEBHOOK_SECRET` with the `whsec_...` value, scope to Production.
Then redeploy (any small push, or manually redeploy the latest). The
handler reads the env var on every invocation, so a deploy that postdates
the env-var set is sufficient.

### 6. Smoke-test with a short test meeting

Record a quick Fathom meeting (≥90 seconds so the classifier's short-file
heuristic doesn't exclude it). Wait 2–5 minutes for Fathom's post-
processing. Check:

```sql
-- Expect a row with processing_status='processed' within a few minutes
select webhook_id, processing_status, call_external_id, received_at, processed_at
from webhook_deliveries order by received_at desc limit 5;

-- Matching calls row
select id, title, call_category, primary_client_id, started_at
from calls where external_id = '<recording_id from above>';
```

If `processing_status = 'processed'` and a `calls` row exists → pipeline
working end-to-end. F2.5 closed.

If `processing_status = 'failed'`: inspect `processing_error` for the
traceback.

If no row at all: check Vercel function logs — either signature verify is
failing (check env var spelling + trailing whitespace) or the webhook was
registered with a wrong URL.

---

## Monitoring

### Daily health query

```sql
select processing_status, count(*)
from webhook_deliveries
where received_at > now() - interval '24 hours'
group by processing_status;
```

Expected: one row `processed` with ~15–25 count (our daily call volume).
Any rows with `failed` or `malformed` warrant investigation.

### Recent failures

```sql
select webhook_id, received_at, call_external_id, processing_error
from webhook_deliveries
where processing_status in ('failed','malformed')
  and received_at > now() - interval '7 days'
order by received_at desc;
```

### Coverage check — webhook vs cron

After F2.6 lands, both paths will write `webhook_deliveries` rows. Tell
them apart via `source`:

```sql
select source, count(*) from webhook_deliveries
where received_at > now() - interval '7 days' group by source;
```

If `fathom_cron` > 0 but `fathom_webhook` is flat for that same window, the
webhook stopped firing — investigate Fathom-side or Vercel-side.

### Slowest deliveries (latency regression)

```sql
select webhook_id, extract(epoch from processed_at - received_at) as seconds
from webhook_deliveries
where processing_status = 'processed'
  and processed_at > now() - interval '24 hours'
order by seconds desc limit 20;
```

Typical is ~5–10s. Anything >30s is worth inspecting (long call? embedding
API slow?). Anything approaching 60s → Vercel will kill the function next
time; raise `maxDuration` or investigate the latency source.

---

## Failure modes — what to do when

| Symptom | Likely cause | Action |
|---|---|---|
| All deliveries 401 | Secret mismatch between Fathom and Vercel env var | Rotate the secret — see "Rotate Secret" below. |
| All deliveries 500 | OpenAI or Supabase outage | Check status pages. Cron backfill catches up once service restored. |
| Some deliveries `malformed` | Fathom payload shape drift | Inspect `webhook_deliveries.payload` — compare to adapter's expectations in `ingestion/fathom/webhook_adapter.py`. |
| `needs_review` queue growing fast | New client roster — resolver doesn't match | Expected; hand-merge via `scripts/merge_client_duplicates.py` when queue reaches actionable size. See `docs/followups.md` § "Auto-created client review workflow". |
| Duplicate calls in DB | Shouldn't happen — pipeline idempotency covers this | File a bug; worth investigating the classifier / upsert paths. |
| `calls` row but no `call_summary` document | Summary was empty in the webhook payload | Normal — older calls or calls Fathom didn't summarize. Not a bug. |
| `calls` row but no `call_action_items` | Same — not all calls have action items | Normal. |

---

## Rotate Secret (F2.5+ — not yet needed)

Fathom has no `PATCH /webhooks` endpoint, so rotation = delete + recreate.
Because deliveries in-flight between the two steps would fail signature
verify, the correct pattern is:

1. Register a second webhook at the same URL via `POST /webhooks` (same
   body as the original registration). Capture the new `secret`.
2. Set `FATHOM_WEBHOOK_SECRET_PREV` = the CURRENT secret on Vercel.
3. Set `FATHOM_WEBHOOK_SECRET` = the NEW secret on Vercel.
4. Deploy. (During this deploy, the handler needs to accept either secret —
   see the existing handler's signature verify function; today it reads only
   `FATHOM_WEBHOOK_SECRET`. Update the verifier to try both env vars if
   both are present, OR accept the risk of a brief verify-fail window
   during step 5.)
5. Wait 5 minutes for Fathom's retry window to clear, then delete the
   original webhook via `DELETE /webhooks/<original_id>`.
6. Unset `FATHOM_WEBHOOK_SECRET_PREV` on Vercel + redeploy.

See `docs/followups.md` § "Fathom webhook secret rotation runbook" for the
pending work to update the handler's verify function to support the dual-
secret overlap window.

---

## Teardown

To stop Fathom deliveries entirely (e.g., for maintenance window):

```bash
curl -sS -X DELETE https://api.fathom.ai/external/v1/webhooks/<WEBHOOK_ID> \
  -H "Authorization: Bearer <FATHOM_API_KEY_PROD>"
```

Fathom stops delivering immediately. The Vercel endpoint stays live (200s
on GET, 401s on POST since the secret-tied-to-deleted-webhook won't verify
any real signed request). Calls recorded during the teardown period are
recoverable via the F2.6 cron backfill once the webhook is re-registered.

---

## References

- `docs/architecture/fathom_webhook.md` — full design spec.
- `api/fathom_events.py` — handler source, annotated.
- `ingestion/fathom/webhook_adapter.py` — payload → FathomCallRecord.
- `ingestion/fathom/pipeline.py` — `ingest_call`, `_ensure_summary_document`,
  `_upsert_action_items`.
- `supabase/migrations/0011_webhook_deliveries_and_doc_type_unique.sql` —
  table DDL.
- `scripts/test_fathom_webhook_locally.py` — local 5-path test loop.
- `docs/followups.md` — open questions, secret rotation, observability push-
  vs-pull.
- `docs/runbooks/slack_webhook.md` — structurally-similar handler; sync
  pattern precedent.
- `docs/runbooks/fathom_backlog_ingest.md` — TXT backlog path, same
  pipeline core.
