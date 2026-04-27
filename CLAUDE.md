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

**Phase 0 foundation: complete.** All ingestion pipelines built and applied. See "Table fill (cloud)" below for current counts. Slack history (2,914 messages across 8 channels) exists on **local** only — cloud Slack ingestion deferred per `docs/future-ideas.md`. Shared utilities, validators, and HITL infrastructure in place.

**Phase 1: Ella V1 — live and operating, polish in progress.** Agent code in `agents/ella/`. Slack webhook live, smoke-tested, replying with native Slack mrkdwn (M1.3) and posting via `@ella` user token (M1.4.3) so replies render with no APP tag in `#ella-test-drakeonly`. Fathom backlog fully ingested (F1.4); live cron sweep operating daily and ran its first real sweep 2026-04-27 (M1.2.5) producing the first `call_summary` documents and `call_action_items` rows in cloud. **Phase 1 polish remaining:** awaiting Nabeel's read on whether M1.4.3's user-token-reply addresses his "looks unprofessional" feedback before pilot rollout to remaining 6 channels (M1.4.5).

**Phase 2 starting: CSM Co-Pilot V1.** Per Drake's plan, the next agent build. Same data layer, team-side surface. Detail in Next Session Priorities #2 below.

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

As of 2026-04-27 (M1 close-out):

- **Cloud Supabase** is the production target. Project ref `sjjovsjcfffrftnraocu` (region us-east-2, Ohio). 11 migrations applied (`0001_core_entities` through `0011_webhook_deliveries_and_doc_type_unique`). Accessed via the pooler URL stored in `supabase/.temp/pooler-url`; the DB password lives in `.env.local` as `SUPABASE_DB_PASSWORD` (quoted because it contains a `#`).
- **Local Supabase** (Docker stack at `127.0.0.1:54321`, Postgres on `:54322`) is a dev-only mirror — useful for harness runs and inspection. Not consulted by any deployed component. `.env.local`'s `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` carry cloud values; local connections require explicit `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
- **Vercel deployment** live at `https://ai-enablement-sigma.vercel.app`. Three serverless functions registered in `vercel.json`: `api/slack_events.py` (Ella's Slack handler, `maxDuration: 60`), `api/fathom_events.py` (Fathom webhook, `maxDuration: 60`), `api/fathom_backfill.py` (daily cron, `maxDuration: 300`). Vercel Cron schedule `0 8 * * *` (08:00 UTC daily) targets `/api/fathom_backfill`. Env vars in production: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_USER_TOKEN` (M1.4), `FATHOM_WEBHOOK_SECRET`, `FATHOM_API_KEY`, `FATHOM_BACKFILL_AUTH_TOKEN`, `CRON_SECRET`.
- **Slack app:** configured, installed in `#ella-test-drakeonly` (Drake-only test, mapped to Javi Pena's `client_id` as a temporary fixture), `#ella-test`, and the 7 pilot client channels. Event Subscriptions enabled; `app_mention` subscribed; signing-secret-verified. Bot scopes + new `chat:write` user scope (M1.4.1). The `@ella` Slack user account exists, was added as an app Collaborator to enable the OAuth flow, ran the install as Ella, and produced the `xoxp-` user token now in Vercel as `SLACK_USER_TOKEN`. Ella the user is currently invited to `#ella-test-drakeonly` only — pilot channels still pending (M1.4.5).
- **Ella:** agent code in `agents/ella/`. Sync handler (Vercel kills threads on return — see `docs/runbooks/slack_webhook.md`). M1.3 (2026-04-27) shipped `shared/slack_format.py` (markdown→mrkdwn converter, wired in `agents/ella/slack_handler.py`); replies now render with native Slack bold/italic. M1.4.3 (2026-04-27) shipped two-token posting in `api/slack_events.py:_post_to_slack` — tries `SLACK_USER_TOKEN` (xoxp-, no APP tag) first, falls back to `SLACK_BOT_TOKEN` (xoxb-, with APP tag) on any failure. **Reply path is APP-tag-free in `#ella-test-drakeonly` as of M1.4.3 deploy.** Known constraint: the inbound `app_mention` event is Slack-app-scoped, so the user-side @-mention still shows the bot as the mention target — the *response* renders as the user. Awaiting Nabeel's read on whether this addresses his ask. M1.4.5 (pilot rollout) holds until that comes back. `agent_runs.duration_ms` still `NULL` — deferred per `docs/followups.md`.
- **Fathom webhook handler:** `api/fathom_events.py` deployed and registered with Fathom. **Two F2.1 doc-vs-reality bugs caught at deploy and fixed in M1.2.5:** (a) outbound auth uses `X-Api-Key`, not the OpenAPI-documented `Authorization: Bearer`; (b) `default_summary` field is `markdown_formatted`, not the spec-driven `markdown`/`text`/etc. fallback list. Both have unit tests pinning the corrected behavior. **Webhook itself has not yet received an organic Fathom delivery** — `webhook_deliveries.source='fathom_webhook'` is still 0. The cron path has been doing all the catch-up so far (31 cron-sourced rows). When a real coaching call finishes Fathom post-processing while our webhook is reachable, that path activates. Architecture in `docs/architecture/fathom_webhook.md`; ops in `docs/runbooks/fathom_webhook.md`.
- **Fathom backfill cron:** `api/fathom_backfill.py` deployed (M1.2 / M1.2.5). Daily 08:00 UTC via Vercel Cron. First real sweep ran 2026-04-27: 29 calls ingested (15 client + 14 non-client), 153 action items, 15 summaries (after the `markdown_formatted` adapter fix + targeted backfill via `scripts/backfill_summary_docs_for_fathom_cron.py`). Race-condition pattern observed — concurrent manual triggers can hit `calls_source_external_id_key` collisions. Documented in followups; not a real-world issue at daily cadence.
- **Table fill (cloud, post-M1 close-out — 2026-04-27):**
  - `team_members` — 9 (7 with `slack_user_id`)
  - `clients` — 134 (100 Active++ canonical + 34 auto-created from F1.4/M1.2.5 Fathom ingest, all tagged `needs_review`)
  - `slack_channels` — 101
  - `client_team_assignments` — 100
  - `calls` — 545 (516 from F1.4 backlog + 29 from M1.2.5 cron sweep). All `source='fathom'`. Most-recent `started_at` reflects the latest cron-ingested call.
  - `call_participants` — 1,503 (1,404 from F1.4 + 99 from M1.2.5)
  - `call_action_items` — 153 (M1.2.5 — first ingestion of this table)
  - `documents` — 715 (297 `course_lesson` + 403 `call_transcript_chunk` + **15 `call_summary`** — the call_summary count is new since M1.2.5)
  - `document_chunks` — 5,150 (651 course + 4,484 transcript + 15 summary chunks; embedded via `text-embedding-3-small`)
  - `webhook_deliveries` — 31 (29 `processed` + 2 `failed`-via-race; all `source='fathom_cron'`. Zero `source='fathom_webhook'` rows yet — the live webhook handler has been reachable but no delivery has organically arrived through it.)
  - `slack_messages` — 0 (90-day backfill deferred per `docs/future-ideas.md`)
  - `agent_runs` — 24 (smoke tests + harness runs)
  - **Still empty**: `escalations`, `agent_feedback`, `nps_submissions`, `client_health_scores`, `alerts`, `slack_messages`.
- **Test suite:** 344 passing (270 baseline + 14 M1.4.3 user-token tests + 16 F2.3 webhook-adapter tests + 42 M1.3 slack-format tests + 2 F2.3 markdown_formatted tests).

## Next Session Priorities

Pick these up in order. **Read this section first** when starting a new session — it's the single source of truth for where to start.

1. **Aman sales-call classification — discovery + design first, then implement.** Drake noticed Aman's prospect/sales calls don't have a clean classifier category. Today they likely land as `external` (per `ingestion/fathom/classifier.py:_classify_by_participants` — non-team participant + no client match → external) which means **no transcript chunks land in the KB** (since `_INDEXABLE_CATEGORIES = {"client"}`). For CSM Co-Pilot V1, this is a prerequisite: if sales-call content surfaces unfiltered to CSMs, the agent reasons over content that isn't its scope. Decisions to make: (a) keep as `external` and document the omission, (b) add a new `sales` category to the classifier and route sales-call content to a dedicated index, (c) use tags on existing `external` rows to flag "Aman-recorded" and filter at retrieval. Each has different schema implications — the classifier change is `ingestion/fathom/classifier.py:_classify_by_participants` + possibly a new entry in `_INDEXABLE_CATEGORIES`; tags would need a `calls.tags` column or use the existing `metadata` jsonb. **Read-only discovery first.** Then design. Then implement. Then backfill any of Aman's existing calls (query: `select count(*) from calls where call_category='external' and primary_client_id is null and id in (select call_id from call_participants where email='aman@theaipartner.io')`). Prerequisite for #2 below.

2. **CSM Co-Pilot V1 scoping.** Second agent on the roadmap (Ella was first). Lives team-side, helps CSMs draft follow-ups, surface insights from their clients' calls, manage their book. Same data layer as Ella (Supabase + kb_query + claude_client + hitl), different surface (Slack agent in CSM team channels, NOT client channels). Per CLAUDE.md project purpose, this is the second pillar of the agency's AI enablement system. **This week's main deliverable per Drake's plan.** Start with the same discovery shape as Ella's V1 — read `docs/agents/ella.md` and `docs/agents/ella-v1-scope.md` to mirror that pattern. Likely needs: new `agents/csm_copilot/` directory, new system prompt grounded in CSM workflows, retrieval scoped to a CSM's assigned clients (via `client_team_assignments`), new `escalations` and `agent_feedback` consumption patterns. **Wait until #1 is done** so sales-call content doesn't accidentally surface to CSMs.

3. **Slack history 90-day backfill into cloud + continuous ingestion.** Deferred to next week per Drake's call. Don't start until CSM Co-Pilot V1 is in good shape. Currently cloud has 0 `slack_messages`. Per `docs/future-ideas.md` § "Slack messages as a retrieval surface", needed for CSM Co-Pilot V2 (health signals from pilot-channel conversation patterns) but not for V1.

4. **Ella V2 conversational behavior items (4 batched).** Per `docs/future-ideas.md` § "Ella V2 — conversational behavior" — out-of-thread replies, prior-thread context, bare-mention handling, speaker identification. **Deferred until after CSM Co-Pilot V1 ships** — these are polish, not blockers.

5. **M1.4.5 — Pilot rollout of @ella user account to remaining 6 pilot channels.** **PENDING NABEEL'S READ on M1.4.3.** The current state: Ella's *replies* render with no APP tag (user-token path), but the *@-mention to invoke her* still targets the bot (because Slack's app_mention event subscription is bound to the bot user — that's a Slack architectural constraint, not a code choice). This may or may not address Nabeel's "looks unprofessional" feedback. If yes → invite @ella user to Fernando G / Musa / Jenny / Dhamen / Trevor / Art channels and ship as-is. If no → workaround design needed (e.g., custom mention pattern, slash command, or accept the constraint and document it).

**Deferred items not in priorities** (intentionally — see `docs/followups.md` for revisit triggers):
- F1.5 classifier bug (9 client-category calls with NULL primary_client_id — Drake's call to handle via manual review rather than code fix)
- 4 minor non-load-bearing Fathom payload fields the adapter drops (`meeting_title`, `created_at`, `calendar_invitees_domains_type`, `recorded_by.team`)
- Cron sweep race condition (only matters if cadence moves below daily)
- Fathom webhook secret rotation runbook (needed before first rotation, not urgent)
- Slack `reply_broadcast=true` behavior change for Ella threaded replies

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
