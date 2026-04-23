# Runbook: Slack Events Webhook (Ella)

How to operate the Vercel serverless function that receives Slack `app_mention` events and routes them into Ella. Covers redeploy, logs, rollback, and signing-secret rotation.

## Where the code lives

- `api/slack_events.py` — the webhook handler. Vercel auto-routes `api/*.py` as individual serverless functions; the production URL for this one is `https://<vercel-project>.vercel.app/api/slack_events`.
- `vercel.json` — function config. Sets `maxDuration: 60` for `api/slack_events.py` so the background thread has headroom to complete Ella's roundtrip after we've already acked Slack.
- `requirements.txt` — Vercel installs Python deps from here at build time. Kept in sync by hand with `[project.dependencies]` in `pyproject.toml`.
- `agents/ella/slack_handler.py` — the handler the webhook calls into. Routing rules and team-test mode logic live there; do not duplicate them in the webhook layer.

## Architecture (why it's split)

Slack retries any webhook that doesn't return 200 within 3 seconds. Ella's full roundtrip takes 3–10 seconds. So `api/slack_events.py` acks first, then spawns a background thread to run the agent and post the reply via `chat.postMessage`:

```
Slack → POST /api/slack_events
            ├── verify HMAC signature on raw body
            ├── handle url_verification challenge (if present)
            ├── detect X-Slack-Retry-Num (skip; original still running)
            └── for app_mention:
                    threading.Thread(target=_process_mention).start()
                    return 200 "ok"      ← Slack sees this in <100ms

Background thread (same invocation, up to maxDuration=60s):
    handle_slack_event(payload)        ← agents.ella.slack_handler
    chat.postMessage (thread_ts, text) ← urllib.request, no SDK
```

The thread is non-daemon: the Python process stays alive until it finishes or `maxDuration` kills it. If Ella routinely takes longer than 60s (she shouldn't — Claude is 3–5s, retrieval is sub-second), bump `maxDuration` in `vercel.json`.

## Required env vars on the Vercel project

Set all six via Vercel dashboard → Project Settings → Environment Variables. Mirror the values from `.env.local` exactly. **Never commit real values.** See `.env.example` for descriptions.

| Name | Used by |
|---|---|
| `SUPABASE_URL` | `shared/db.py` |
| `SUPABASE_SERVICE_ROLE_KEY` | `shared/db.py` |
| `ANTHROPIC_API_KEY` | `shared/claude_client.py` |
| `OPENAI_API_KEY` | `shared/kb_query.py` (embeddings) |
| `SLACK_BOT_TOKEN` | `api/slack_events.py` outbound `chat.postMessage` |
| `SLACK_SIGNING_SECRET` | `api/slack_events.py` inbound HMAC verification |

After changing any env var, **redeploy** — Vercel does not propagate env-var changes to running deployments.

## Redeploying

The Vercel project is linked to the GitHub repo; any push to `main` triggers a production deploy. So the standard loop is:

1. Edit `api/slack_events.py` (or `agents/ella/*`, `shared/*`, etc.).
2. `pytest tests/` — expect 270+ passing.
3. Commit and push to `main`.
4. Watch the deploy on Vercel dashboard → Deployments. Build takes ~30–60s.

Manual-trigger redeploy without a code change: Vercel dashboard → Deployments → latest → … menu → Redeploy. Useful after changing env vars.

## Checking logs

Vercel dashboard → the project → Logs tab. Filter by function `api/slack_events.py`. Every request logs at least one line; look for:

- `signature verification failed` — mismatched `SLACK_SIGNING_SECRET` or a replayed request.
- `url_verification challenge received` — one-time handshake when the Event Subscription URL is first saved. Good sign.
- `skipping retry #N` — Slack retried (almost always because the first delivery took >3s). The original thread is still handling it.
- `slack.postMessage ok: ...` — Ella posted successfully.
- `slack.postMessage failed: ...` — full JSON body from Slack's Web API; check `error` field (`not_in_channel`, `missing_scope`, `channel_not_found`, etc.).
- `handle_slack_event raised: ...` — agent crash. Full traceback follows.

Cross-reference with `agent_runs` rows in Supabase Studio — every mention should have landed a row, whether the thread succeeded or the Slack post failed.

## Rolling back

Vercel dashboard → Deployments → find the last known-good deployment → … menu → Promote to Production. Takes a few seconds; no git changes needed.

If the bad code is already in `main`, follow the promotion with a `git revert` on the offending commit so the next push doesn't re-deploy it.

## Rotating the Slack signing secret

Slack's signing secret changes if someone regenerates it in the app console or if the app is reinstalled. When that happens:

1. api.slack.com/apps → the app → Basic Information → App Credentials → Signing Secret → copy the new value.
2. Update `.env.local` (for local dev / future harness runs).
3. Vercel dashboard → Project Settings → Environment Variables → edit `SLACK_SIGNING_SECRET` → paste new value → save.
4. Redeploy (env-var changes don't propagate without one — see "Redeploying" above).
5. Smoke test: @mention Ella in `#ella-test-drakeonly`. If the Vercel log shows `signature verification failed`, the old value is still cached — redeploy again or force-redeploy from the dashboard.

The same process applies to rotating `SLACK_BOT_TOKEN` (from OAuth & Permissions → Reinstall to Workspace).

## Rotating other secrets

Same pattern: update `.env.local` for parity, update Vercel env var, redeploy. `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` rotations are invisible to Slack — no smoke test needed beyond a single @mention round-trip.

## Adding a new pilot channel

V1 does not consult `slack_channels.ella_enabled` — the enabled-channel list is the set of channels the Slack app is installed in. To add a channel:

1. Invite the Ella bot to the new channel (`/invite @Ella`).
2. Verify / create the `slack_channels` row with the channel's `C...` id and `client_id` set to the pilot client's UUID. Reference `docs/agents/ella-v1-scope.md` for how `client_id` drives retrieval scoping.
3. No code change; no redeploy needed.

## Known limits and gotchas

- **Cold starts can miss the 3s ack.** First request after idle may take 2–5s for Python + deps to load. Slack will retry; the retry-detection in `api/slack_events.py` prevents duplicate responses, but the user sees a slight lag on their first message after idle.
- **`maxDuration: 60` is a hard ceiling.** If Ella's roundtrip ever exceeds 60s, the background thread is killed mid-flight and no `chat.postMessage` lands. Diagnose via agent_runs row (started but not ended) + Vercel log showing the invocation was terminated.
- **Thread posting errors are logged, not retried.** If `chat.postMessage` fails (e.g., transient Slack outage), the message is lost for that mention. Acceptable for V1; a retry queue belongs with eval / HITL work later.
- **No event-id deduplication.** If Slack delivers the same event twice via a path that doesn't set `X-Slack-Retry-Num` (shouldn't happen, but possible), we'd process it twice. Log it in `docs/future-ideas.md` if it surfaces.
