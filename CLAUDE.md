# CLAUDE.md

Primary context for any Claude Code instance working on this repo. Read this fully before making changes.

## Project Purpose

Internal AI enablement system for a coaching/consulting agency. Replaces and augments human work across customer success, sales, and operations. The consumer business runs on this system first; later, the same system will be deployed to other agencies as a productized consulting offering.

**Immediate focus:** ship Slack Bot V1 (Ella) and CSM Co-Pilot V1 by end of April.

## Core Principles (Non-Negotiable)

These four principles protect the system from lock-in and rebuilds. Apply them to every decision.

1. **Our database is the source of truth.** Every piece of data we touch is mirrored into Supabase. External tools are secondary.
2. **Agents query our database, not external tools.** An agent never calls Fathom, Slack, or the CRM directly for data. Ingestion pipelines populate Supabase; agents read from Supabase.
3. **External tools are replaceable adapters.** Each integration lives in its own module. Swapping any one is a contained rewrite, not a system-wide migration.
4. **Interfaces are thin clients on a shared brain.** Agent logic lives in one place, exposed via API. Slack, future web portals, email — all just front doors. No business logic in interface code.

## Stack

| Layer | Tool | Notes |
|-------|------|-------|
| Database | Supabase (Postgres + pgvector) | Source of truth. All data mirrored here. |
| Backend / Agents | Python 3.11+ | Primary language. FastAPI for services. |
| Frontend | Next.js 14 + TypeScript | Dashboards and approval UI. |
| Orchestration | n8n (self-hosted) | Workflows, scheduling, HITL routing. Zain builds workflows; they get imported into our n8n. |
| LLM | Anthropic Claude API | Sonnet as default, Opus for complex reasoning, Haiku for simple/cheap tasks. |
| Embeddings | OpenAI `text-embedding-3-small` | 1536 dims. Used by `shared/kb_query.py` and all ingestion that writes `document_chunks`. |
| Hosting | Vercel | Frontend + serverless Python functions (Ella's Slack webhook handler will live here). |
| Voice | ElevenLabs | Course audio, future voice agents. |
| Dev environment | WSL2 Ubuntu on Windows | All dev happens inside WSL. VS Code with Remote-WSL extension. |
| Secrets | Bitwarden master list + env vars | `.env.local` locally, Vercel env vars in production. See `.env.example` — required keys today: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`. `SUPABASE_DB_PASSWORD` is also set in `.env.local` for ops scripts that connect directly via psycopg2 (migrations, seeds, diagnostics) — not required by the webhook or the agent runtime. |

## Language Policy

- **Python first** for agents, ingestion pipelines, evals, scripts, data work
- **TypeScript** for Next.js frontend and browser code
- **Other languages only when no reasonable Python or TS option exists.** Ask before introducing a new language.

## Folder Structure

```
ai-enablement/
├── CLAUDE.md                   # This file
├── README.md                   # Human-facing project overview
├── .env.example                # Template for required env vars
├── .gitignore
├── pyproject.toml              # Python project config
├── docs/
│   ├── architecture.md         # System overview, data flow, component map
│   ├── collaboration.md        # How Drake and Zain divide work
│   ├── future-ideas.md         # Deferred work log with revisit triggers
│   ├── schema/                 # One markdown file per database table (schema-v1.md is canonical index)
│   ├── agents/                 # One markdown file per agent (ella.md full spec, ella-v1-scope.md team-facing)
│   ├── decisions/              # Architecture Decision Records (ADRs)
│   └── runbooks/               # How to do recurring tasks
├── supabase/
│   ├── migrations/             # Numbered SQL migration files (0001–0010 applied locally)
│   └── seed/                   # Seed data for local testing
├── ingestion/                  # Data ingestion pipelines (all built and applied locally)
│   ├── fathom/                 # Call transcripts — backlog `.txt` path shipped; webhook deferred
│   ├── slack/                  # Channel history backfill (REST only; Events API deferred)
│   ├── content/                # Filesystem-sourced HTML lessons (Drive API deferred)
│   └── crm/                    # (planned)
├── agents/                     # Agent implementations
│   ├── ella/                   # Slack Bot V1 — agent.py, retrieval.py, prompts.py,
│   │                           # escalation.py, slack_handler.py
│   └── csm_copilot/            # (planned — follows Ella)
├── orchestration/              # n8n workflow exports (JSON)
├── frontend/                   # Next.js app
├── shared/                     # Shared Python utilities
│   ├── claude_client.py        # Anthropic API wrapper (cost tracking via run_id)
│   ├── kb_query.py             # Knowledge base retrieval (wraps match_document_chunks RPC)
│   ├── hitl.py                 # Human-in-the-loop escalation helper
│   ├── logging.py              # Structured logging + agent_runs lifecycle (start_agent_run / end_agent_run)
│   ├── db.py                   # Supabase client setup
│   └── ingestion/
│       └── validate.py         # documents / document_chunks metadata validator — REQUIRED for new pipelines
├── evals/                      # Golden datasets + eval runner (empty for now; Ella V1 ships without)
├── scripts/                    # One-off scripts, data imports, admin tasks
│   ├── seed_clients.py         # Load Active++ view into clients + client_team_assignments
│   ├── backfill_team_slack_ids.py
│   └── merge_client_duplicates.py   # One-shot merge of auto-created client rows into canonical
├── tests/                      # pytest suite — see Live System State for count
└── data/                       # GITIGNORED. Source files for ingestion live here:
                                #   data/client_seed/       (Active++ CSV export)
                                #   data/fathom_backlog/    (Fathom .txt transcript exports)
                                #   data/course_content/    (HTML lesson files)
                                # Secondary dirs (data/fathom_ingest, data/slack_ingest, data/content_ingest)
                                # hold pipeline state / logs.
```

## Conventions

### Code

- **Python:** PEP 8. Type hints everywhere. Format with `black`, lint with `ruff`.
- **TypeScript:** Strict mode on. Format with Prettier, lint with ESLint.
- **No one-letter variables** except tight loops (`i`, `j`).
- **Functions do one thing.** Split if exceeding ~50 lines.
- **Pure functions where possible.** Side effects (DB writes, API calls) isolated in thin layers.

### Naming

- Python files/modules: `snake_case.py`
- Python classes: `PascalCase`
- Python functions/variables: `snake_case`
- TypeScript files: `kebab-case.ts` or `PascalCase.tsx` for components
- Database tables: `snake_case`, plural (`clients`, `calls`, `messages`)
- Database columns: `snake_case`
- Environment variables: `SCREAMING_SNAKE_CASE`

### Documentation (Non-Negotiable)

Every substantive change updates documentation in the same commit.

- **New database table** → new file in `docs/schema/` with: purpose, columns, relationships, what populates it, what reads from it, example queries
- **New agent** → new file in `docs/agents/` with: purpose, inputs, outputs, data dependencies, escalation rules, eval criteria
- **New ingestion pipeline** → runbook in `docs/runbooks/` covering: what it does, schedule, failure modes, debugging
- **Significant architectural decision** → new ADR in `docs/decisions/` using the standard template

Documentation is not optional and not written "later." It ships alongside the code.

### Commits

- Commit frequently — every meaningful unit of work, even if imperfect
- **One logical change per commit.** If you find yourself typing " and " or " also " in a commit message, split it.
- Commit messages: short, declarative, present tense (imperative mood)
  - Good: `add clients table migration`
  - Good: `ingest fathom transcripts into KB`
  - Good: `fix slack bot threading on DM replies`
  - Bad: `updates`, `fixed stuff`, `wip`
- **Never commit with failing tests.** Run `pytest tests/` first.
- Never commit secrets. Run `git diff` before every commit to scan for keys.

**Commit policy:** At the end of each meaningful unit of work (a feature complete, a migration applied, a file fully refactored), commit with a clear message following our convention. Do not commit half-finished work. Do not commit if tests/validation fail. Push to remote at the end of each session.

### Client Identity Resolution (alternate emails / alternate names)

The Fathom classifier resolves call participants to `clients` rows by email first, then by display name. Both lookups consult `clients.metadata` jsonb arrays:

- `metadata.alternate_emails` — emails the client has used historically (e.g., the email on their Fathom account vs. the one on their Active++ record).
- `metadata.alternate_names` — display names the client has used historically (e.g., "King Musa" on Fathom vs. "Musa Elmaghrabi" on the roster).

Both arrays are consulted case-insensitively, whitespace-stripped. When you merge an auto-created duplicate client row into a canonical row (see `scripts/merge_client_duplicates.py`), write the auto row's email and full_name into these arrays on the real row so future ingestion resolves cleanly without re-creating the duplicate. Any new ingestion path that resolves humans-to-clients should consult these fields before creating a new row.

### Error Handling

- External API calls always wrapped with retry + timeout + structured logging
- Database writes transactional when multiple tables are affected
- Agent failures escalate to HITL rather than silently failing
- Never swallow exceptions without logging them

## Critical Rules

### Never Do

- **Never commit `.env`, `.env.local`, or any file with credentials.**
- **Never install a new major dependency without asking first.** Adding `langchain` or similar heavy frameworks is a big commitment.
- **Never write code without updating the corresponding documentation.** Code and docs ship together.
- **Never couple agent logic to a specific external tool.** Agents query the KB. If you find yourself writing `fathom_client.get_call(...)` inside an agent, stop — move the fetch into the ingestion layer, persist to Supabase, then query from the agent.
- **Never bypass the HITL pattern.** If an agent is uncertain, escalate. Do not guess confidently.
- **Never use `print()` for anything that should persist.** Use structured logging via `shared/logging.py`.
- **Never write to `documents` or `document_chunks` without running through the validator.** `shared.ingestion.validate.validate_document_metadata()` / `validate_chunk_metadata()` enforces the contract every chunk in the KB depends on. Bypassing it poisons retrieval.

### Always Do

- **Always ingest data through the ingestion layer, not from agents.** If an agent needs data not yet in the KB, extend an ingestion pipeline — do not reach out from the agent.
- **Always run the metadata validator before inserting into `documents` / `document_chunks`.** Every ingestion pipeline in this repo does; new ones must follow suit.
- **Always write an eval before considering an agent "done."** Target: minimum 20 golden examples per agent, 90% pass rate to ship. *V1 carve-out:* Ella V1 ships without a formal eval harness (replaced by live team testing in `#ella-test` Thu/Fri) — this is documented in `docs/agents/ella-v1-scope.md` and `docs/future-ideas.md` as a V1.1 follow-up.
- **Always ask before introducing new external services, libraries, or languages.**
- **Always read the relevant `docs/` files before editing a component.**

## Current Focus

**Phase 0 foundation: complete.** All ingestion pipelines built and applied. Counts reflect **cloud** Supabase as of F1.4 (2026-04-24): Fathom calls (516 calls, 388 `call_transcript_chunk` documents, 4,329 call-transcript chunks — see Table fill below for the full breakdown), Active++ clients (100 canonical + 34 Fathom auto-created `needs_review` rows), course content (297 lessons, 651 chunks). Slack history (2,914 messages across 8 channels) exists on **local** only — cloud Slack ingestion deferred per `docs/future-ideas.md`. Shared utilities, validators, and HITL infrastructure in place.

**Phase 1 in progress: Ella V1 build.** Agent code live in `agents/ella/`. Slack webhook live on Vercel, Event Subscriptions enabled, `app_mention` subscribed and verified. Smoke test passed in `#ella-test-drakeonly` (Drake @mentioned → in-thread reply grounded in course-content retrieval). F1.4 (2026-04-24) landed the Fathom backlog into cloud, so Ella now has call-transcript retrieval for all 7 pilot clients. Next session picks up with: the Fathom webhook for live call ingestion (see Next Session Priorities), then team testing Thu/Fri, then client beta Monday in 7 pilot channels.

**Pilot clients for Ella V1 beta:** Fernando G, Javi Pena, Musa Elmaghrabi, Jenny Burnett, Dhamen Hothi, Trevor Heck, Art Nuno. (Nicholas LoScalzo deferred — see `docs/future-ideas.md`.) Scott has already announced Ella to these channels; she ships Monday.

### Deferrals worth knowing about

Documented in `docs/future-ideas.md` with explicit revisit triggers:

- LLM-based summary + action-item generation for backlog calls (Fathom `.txt` exports carry neither; `call_action_items` stays empty until the webhook path ships).
- Fathom webhook integration (live calls → summaries + action items).
- Drive-sourced content ingestion (today's pipeline reads from `data/course_content/`; Drive API + version-awareness comes later).
- `team_members.slack_user_id` backfill sweep for unresolved Slack authors (~94 of 2,914 messages are `unknown`).
- Browser-direct RLS policies (V1 is service-role only).
- Atomic per-call ingest via Postgres RPC (V1 pipeline is non-atomic + idempotent on re-run).
- Ella V1.1 items: cool-down on correction, formal eval harness, per-channel `ella_enabled` gating, thumbs-up/down reactions, impersonation/replay mode, Nicholas LoScalzo onboarding.

## Live System State

As of 2026-04-24:

- **Cloud Supabase** is the production target. Project ref `sjjovsjcfffrftnraocu` (region us-east-2, Ohio). All 10 migrations applied (`0001_core_entities` through `0010_kb_search_exclude_transcript_chunks`). Accessed via the pooler URL stored in `supabase/.temp/pooler-url`; the DB password lives in `.env.local` as `SUPABASE_DB_PASSWORD` (quoted because it contains a `#`).
- **Local Supabase** (Docker stack at `127.0.0.1:54321`, Postgres on `:54322`) is a dev-only mirror — useful for harness runs, inspection, and copying reference data. Not consulted by any deployed component. `.env.local`'s `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` now carry cloud values; local connections require explicit `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
- **Vercel deployment** live at `https://ai-enablement-sigma.vercel.app/api/slack_events`. `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on the project now point at cloud (verified via API); redeployed after the swap. `vercel.json` pins `runtime: @vercel/python@4.3.1` and `maxDuration: 60`. Full operational detail in `docs/runbooks/slack_webhook.md`; cloud-push specifics in `docs/runbooks/cloud_supabase.md`.
- **Slack app:** configured, installed in `#ella-test-drakeonly` (Drake-only test channel, mapped to Javi Pena's `client_id` as a temporary fixture — see followups for the plan to move off this), `#ella-test` (team test channel, not yet remapped), and the 7 pilot client channels. Event Subscriptions enabled; `app_mention` subscribed; Request URL verified green against the Vercel endpoint.
- **Ella:** agent code in `agents/ella/`. Escalation detection uses a structured `[ESCALATE]` marker — see `docs/agents/ella.md` § System Prompt Direction point 10. Architecture is synchronous (not threaded) because Vercel's Python runtime kills background threads at response time — see `docs/runbooks/slack_webhook.md`. **Live in `#ella-test-drakeonly`** — smoke test passed: Drake @mentioned, Ella replied in-thread grounded in course-content retrieval. **Call-context retrieval now live** — F1.4 landed 388 client-call `call_transcript_chunk` documents (345 active, 43 inactive pending needs_review promotion) with 4,329 chunks, all 7 pilot clients present with their coaching history; kb_query spot-checked 2026-04-24 confirming per-client scoping works and no cross-client leakage. `agent_runs.duration_ms` still `NULL` — deferred per `docs/followups.md`.
- **Fathom webhook handler:** `api/fathom_events.py` **deployed to Vercel** via commits `bc4cbbb..e9431da` (F2.5, 2026-04-24). Re-registered live 2026-04-27 after M1.1 surfaced the Fathom-UI viewport-clipping bug that had blocked the original registration. `GET https://ai-enablement-sigma.vercel.app/api/fathom_events` returns 200. Locally verified across all 5 HTTP paths in F2.4 (happy / duplicate-replay / bad-signature / malformed-payload / ingest-failure). **First real delivery still pending** — registration only completed 2026-04-27; no team coaching calls have finished Fathom post-processing since then. M1.2.5 cron will produce the empirical proof end-to-end. Full architecture in `docs/architecture/fathom_webhook.md`; resume procedure in `docs/runbooks/fathom_webhook.md`.
- **Fathom backfill cron:** `api/fathom_backfill.py` **built and locally verified** in M1.2 (2026-04-27). Daily 08:00 UTC sweep via Vercel Cron (configured in `vercel.json`). Auth via `FATHOM_BACKFILL_AUTH_TOKEN` bearer + `CRON_SECRET`; queries Fathom `GET /meetings` with cursor pagination; reuses `record_from_webhook` adapter (GET /meetings returns the same Meeting schema as the webhook); per-sweep cap of 50 ingests with `more_remaining=true` continuation; idempotent on `(source, external_id)`. Per-meeting failures are isolated and logged as `webhook_deliveries` rows with `source='fathom_cron'`. **Not yet deployed** — M1.2.5 deploys + sets `FATHOM_API_KEY` and `FATHOM_BACKFILL_AUTH_TOKEN` env vars in Vercel + manual-triggers the first sweep. Slack-format converter (M1.3) and webhook handler (F2.4) are unaffected.
- **Table fill (cloud, post-F2.3 — 2026-04-24):**
  - `team_members` — 9 (7 with `slack_user_id`, copied from local during push)
  - `clients` — 134 (100 Active++ canonical + 34 auto-created by F1.4 Fathom ingest, all tagged `needs_review` — see `docs/followups.md` § "Auto-created client review workflow")
  - `slack_channels` — 101 (100 from seed + `#ella-test-drakeonly` fixture mapped to Javi Pena)
  - `client_team_assignments` — 100
  - `calls` — 516 (all `source='fathom'`, from 2025-08 through 2026-04-24T16:38Z) — by category: client 388, internal 62, external 54, unclassified 6, excluded 6
  - `call_participants` — 1,404
  - `call_action_items` — 0 (TXT backlog doesn't carry them; live webhook path now supports populating them — F2.3 built `_upsert_action_items` in the pipeline, awaits F2.4 handler + first live delivery)
  - `documents` — 685 (297 `course_lesson` + 388 `call_transcript_chunk`; of the 388, 345 are `is_active=true` and 43 are `is_active=false` — the 43 map 1:1 to medium-confidence client calls whose participant auto-created, awaiting human review). **No `call_summary` docs yet** — same reason as action_items (webhook-delivered, no live deliveries yet). F2.3 built `_ensure_summary_document` in the pipeline.
  - `document_chunks` — 4,980 (651 course-lesson chunks + 4,329 transcript chunks)
  - `slack_messages` — 0 (90-day backfill deferred; not needed for V1 retrieval per `docs/future-ideas.md` § "Slack messages as a retrieval surface")
  - `webhook_deliveries` — 0 (new in migration 0011; populated once F2.4 ships the handler and receives its first delivery)
  - `agent_runs` — 5 (from smoke tests and local harness runs against cloud)
  - **Still empty**: `escalations`, `agent_feedback`, `nps_submissions`, `client_health_scores`, `alerts`, `call_action_items`, `webhook_deliveries` (the last two populate once the live Fathom webhook starts delivering in F2.5).
- **Test suite:** 270 passing (34 on the Ella module).

## Next Session Priorities

Pick these up in order:

1. **M1.2.5 — Deploy `api/fathom_backfill.py` + first manual cron run.** M1.2 (2026-04-27) built and locally verified the backfill handler (auth-only paths green; Fathom-against-cloud paths skipped because `FATHOM_API_KEY` isn't in `.env.local`). M1.2.5 is the deploy + activation step: (a) generate `FATHOM_BACKFILL_AUTH_TOKEN` via `openssl rand -hex 32`, save to Bitwarden; (b) generate `FATHOM_API_KEY` from the Fathom team account, save to Bitwarden; (c) set `FATHOM_API_KEY`, `FATHOM_BACKFILL_AUTH_TOKEN`, and `CRON_SECRET` (same value as `FATHOM_BACKFILL_AUTH_TOKEN`) on Vercel Production scope; (d) push the M1.2 commit (handler + `vercel.json` cron entry); (e) manually trigger the first sweep via `curl -i -X POST -H "Authorization: Bearer <token>" https://.../api/fathom_backfill` and verify the summary JSON shows `meetings_seen > 0`, `already_present > 0` (proves idempotency against F1.4 backlog), and any `ingested` count covers post-registration weekend calls; (f) verify downstream rows landed for ingested external_ids. Full step-by-step in `docs/runbooks/fathom_webhook.md` § Backfill cron / Deploy. The first sweep also serves as M1.1's final verification — it'll surface any post-fix-registration weekend calls AND any ingest-pipeline issues that haven't been exercised against real Fathom data yet.
2. **F2.5 first-real-delivery verification — closes automatically with M1.2.5.** Once M1.2.5's first sweep produces a `processing_status='processed'` row in `webhook_deliveries` for a real Fathom call, the followup entry "F2.5 first-real-delivery verification" closes. The webhook itself remains a separate verification — first organic team-call delivery to `api/fathom_events.py` will produce a `source='fathom_webhook'` row alongside the cron's `source='fathom_cron'` rows. Until both have landed cleanly at least once, treat the live path as "deployed but unverified end-to-end with real data."
3. **Slack history 90-day backfill into cloud + continuous ingestion.** Currently cloud has 0 `slack_messages` — local has 2,914 but that data was never pushed. Per `docs/future-ideas.md` § "Slack messages as a retrieval surface", backfill isn't required for V1 Ella retrieval (she's grounded in course content + Fathom transcripts + now summaries via F2.4), but the CSM Co-Pilot V2 needs pilot-channel Slack context for health signals. Shape: the existing `ingestion/slack/` REST-only backfill runs against cloud; then a webhook subscription to `message.channels`, `message.groups` for the pilot 7 channels captures new messages continuously.
4. **Team-test channel setup with synthetic test client.** Per `docs/future-ideas.md` § "Test-fixture client for team-only Ella test channels" (now active). Create a `clients` row tagged `test_fixture`, remap `#ella-test` (or a new channel — Drake's call) to that client so team testing stops riding on Javi Pena's context.
5. **`reply_broadcast=true` behavior change.** Ella's threaded replies are currently private to the thread; setting `reply_broadcast=true` on the `chat.postMessage` call makes the reply visible in the main channel while staying threaded. Spec note in `docs/agents/ella.md` § Response Location; not yet in `api/slack_events.py`.
6. **Pilot rollout to the remaining 6 client channels.** Javi Pena is already carrying the fixture pattern. Bring in Fernando G, Musa Elmaghrabi, Jenny Burnett, Dhamen Hothi, Trevor Heck, Art Nuno — confirm the Slack app is installed in each, confirm each has a `clients` row + `slack_channels` row (`seed_clients.py` already covered this), run one @mention per channel as a smoke. **All 7 pilots have retrievable call transcripts now** — at least 3 calls each (Javi 7, Musa 3, Dhamen 8, Nicholas 8, Fernando 9, Jenny 8, Trevor 6, Art 3).

**Note:** the F1.5 classifier-bug fix (9 client-category calls with NULL primary_client_id) is deferred per Drake's decision to handle via manual review rather than code fix. Not in priorities.

## Working With Claude Code — Prompting Tips

Give Claude Code context like you'd give a new senior engineer, not like a magic wish granter.

Bad:

> Build the Slack bot.

Good:

> We're building Slack Bot V1 per `docs/agents/ella.md`. Ingest from the `documents` and `slack_messages` tables via `shared/kb_query.py`. Follow the HITL pattern in `shared/hitl.py`. Start with the incoming Slack event handler. Write code, update `docs/agents/ella.md` as you go, add at least 10 golden examples to `evals/ella/`.

After Claude Code generates meaningful code, ask: **"Explain what this does and what could go wrong."** Catches most issues before they compound.

## Update Policy for This File

Update CLAUDE.md whenever:
- A core principle is clarified or extended
- A stack choice changes
- A new major convention is adopted
- The current focus shifts to a new phase
- The "Live System State" snapshot drifts from reality

Treat it as living documentation. A stale CLAUDE.md is worse than no CLAUDE.md.
