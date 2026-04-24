# Followups

Ops reminders and known gaps that aren't "ideas to build" (those live in `docs/future-ideas.md`) and aren't "decisions to revisit" (those are ADRs under `docs/decisions/`). These are things to verify, be aware of, or handle when the moment surfaces.

**Entry format.** Short. Four lines:

- **What:** one-sentence description.
- **Why it matters:** consequence if ignored.
- **Next action:** concrete step that resolves it (or a check that answers whether it needs resolving).
- **Logged:** date.

---

## Verify `javier@buildficial.com` lives on Javi Pena's canonical `metadata.alternate_emails`

- **What:** during the 2026-04-23 session I inserted the `#ella-test-drakeonly` channel row and surfaced that a `Javier Pena` row (`javier@buildficial.com`) was merged into the canonical `Javi Pena` (`javpen93@gmail.com`) row earlier the same day. The merge script is supposed to copy the duplicate's email + full_name into the canonical row's `metadata.alternate_emails` / `metadata.alternate_names` arrays so future Fathom ingestion sees `javier@buildficial.com` on a call participant and resolves to the existing canonical row instead of auto-creating a fresh duplicate.
- **Why it matters:** if the merge didn't complete the metadata write, the next Fathom ingestion run that sees a call from `javier@buildficial.com` will auto-create a new `Javier Pena` row — we'd be right back to the duplicate state, and the merge would need to run again. The Fathom backlog ingestion is next-session priority #1, so this needs to be checked before that runs (or during the post-run verification pass).
- **Next action:** run a quick query against cloud clients: `SELECT email, full_name, metadata->'alternate_emails', metadata->'alternate_names' FROM clients WHERE email = 'javpen93@gmail.com';`. Confirm `alternate_emails` contains `"javier@buildficial.com"` (case-insensitive) and `alternate_names` contains `"Javier Pena"`. If missing, copy them manually before the Fathom run.
- **Logged:** 2026-04-24.

## PostgREST 1000-row page cap — use `count='exact', head=True`

- **What:** `db.table("x").select("id").execute()` against cloud silently caps at 1000 rows — PostgREST's default page size. `len(resp.data)` in that case is the page size, not the row count. For accurate counts, always use `db.table("x").select("id", count="exact", head=True).execute().count`.
- **Why it matters:** caught once on 2026-04-23 while building the `CLAUDE.md` snapshot — I reported `document_chunks: 1000` and `slack_messages: 1000` when the actual counts were 4,179 and 2,914. A silent undercount that gets into a doc or a Slack status message is worse than an obvious error, because the number looks plausible at a glance.
- **Next action:** no one-time fix; this is a behavioral reminder for anyone writing ops scripts or quick counts. If we end up writing enough count-queries to want a shared helper, add one to `shared/db.py` (something like `row_count(table_name)`) that always uses the `count='exact', head=True` shape. Until then, be explicit at every call site.
- **Logged:** 2026-04-24.

## `agent_runs.duration_ms` never written — latency observability gap

- **What:** every Ella `agent_runs` row has `duration_ms = NULL`. The column exists, `shared.logging.end_agent_run` accepts the kwarg, but no agent currently times the turn or passes the value through. Cross-logged as a deferred idea in `docs/future-ideas.md` § "`duration_ms` instrumentation on agent_runs" with the full fix plan.
- **Why it matters:** we can't answer "is Ella getting slower over time?" or "which pilot channel is hitting the worst cold-start latency?" from the rows we have. Tokens and cost land correctly (`shared.claude_client.complete()` writes those via its own UPDATE), so the "is she expensive?" question is covered; latency is the observability hole.
- **Next action:** resolution lives in `docs/future-ideas.md`. This followup is the awareness reminder — until that lands, any latency concern needs to be diagnosed from Vercel request timings, not from the DB.
- **Logged:** 2026-04-24.

## Fluid Compute on Vercel — sub-3s user-visible latency path

- **What:** Ella's webhook is synchronous because Vercel's Python runtime kills background threads at response time. Fluid Compute is Vercel's opt-in runtime setting that would let the handler return 200 fast and keep the Python process alive to finish `chat.postMessage` after the response is sent. With Fluid Compute on, we could revert to an ack-then-work pattern and cut user-visible latency back under 3 seconds on cold starts.
- **Why it matters:** current cold-start experience is a 5–10s gap between @mention and reply — acceptable for V1 pilot volume, will get noticeable if pilot usage climbs. The retry-skip branch in `api/slack_events.py` keeps the architecture correct either way; Fluid Compute would just make it feel faster.
- **Next action:** revisit when (a) pilot users flag the lag explicitly, (b) pilot volume makes cold starts visible several times per day per channel, or (c) we're adding a second agent on the same Vercel project and want the runtime choice unified. Toggling Fluid Compute is a project-level setting; enabling it means reverting the sync path in `api/slack_events.py` to the ack-then-thread pattern that was originally designed.
- **Logged:** 2026-04-24.
