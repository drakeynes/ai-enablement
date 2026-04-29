# CLAUDE.md

Primary context for any Claude Code instance working on this repo. Read this fully before making changes.

## Project Purpose

Internal AI enablement system for a coaching/consulting agency. Replaces and augments human work across customer success, sales, and operations. The consumer business runs on this system first; later, the same system will be deployed to other agencies as a productized consulting offering.

**Immediate focus:** Ella V1 in pilot (live, awaiting Nabeel feedback before pilot rollout to remaining 6 channels). Gregory V1 dashboard scaffold + Clients pages live (M2.3a + M2.3b shipped 2026-04-28; behavior smoke test pending). Calls pages next (M3.1), then Gregory's brain V1.1 (M3.2). Drake-led Aman manual review and the merge feature (M2.3c) deferred until after M3.1 + M3.2.

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
├── scripts/                    # Active tooling — re-runnable seeds, local test harnesses, admin tasks
│   ├── seed_clients.py         # Load Active++ view into clients + client_team_assignments
│   ├── test_ella_locally.py    # Reusable Ella-handler driver (pre-launch + bug repro)
│   ├── test_fathom_backfill_locally.py  # Local harness for the Fathom cron path
│   ├── test_fathom_webhook_locally.py   # Local 5-path test loop for the Fathom webhook
│   └── archive/                # One-shot historical scripts — kept for reference, not re-run
│       ├── README.md
│       ├── merge_client_duplicates.py        # Replaced by Gregory dashboard merge (M3.2)
│       ├── backfill_summary_docs_for_fathom_cron.py  # M1.2.5 in-flight repair
│       └── backfill_team_slack_ids.py        # One-shot post-seed Slack ID resolver
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

Both arrays are consulted case-insensitively, whitespace-stripped. When you merge an auto-created duplicate client row into a canonical row, the auto row's email and full_name must be written into these arrays on the real row so future ingestion resolves cleanly without re-creating the duplicate. The canonical merge surface is the Gregory dashboard's "Merge into…" flow on the Clients detail page (migration `0015_merge_clients_function.sql` handles the alternates sync atomically as part of the merge). The historical `scripts/archive/merge_client_duplicates.py` did the same thing for the four pilot pairs already merged and remains as reference. Any new ingestion path that resolves humans-to-clients should consult these fields before creating a new row.

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

**Phase 0 foundation: complete.** All ingestion pipelines built and applied. Slack history (2,914 messages across 8 channels) exists on **local** only — cloud Slack ingestion deferred per `docs/future-ideas.md`. Shared utilities, validators, and HITL infrastructure in place.

**Phase 1: Ella V1 — live and operating, polish in progress.** Agent code in `agents/ella/`. Slack webhook live, smoke-tested, replying with native Slack mrkdwn (M1.3) and posting via `@ella` user token (M1.4.3) so replies render with no APP tag in `#ella-test-drakeonly`. Fathom backlog fully ingested (F1.4); live cron sweep operating daily. **Phase 1 polish remaining:** awaiting Nabeel's read on whether M1.4.3's user-token-reply addresses his "looks unprofessional" feedback before pilot rollout to remaining 6 channels (M1.4.5).

**Phase 2: Gregory dashboard V1 — COMPLETE.** Clients pages (list + detail + inline-save + CSM-swap dialog), Calls pages (list + detail + edit-mode classification with `call_classification_history` writes), and the merge feature for auto-created clients (TypeScript-native via the `merge_clients` RPC) all shipped and verified live during M3. M2.3b behavior smoke test passed in M3.1; M3.2 stress-tested the merge accumulator across three sequential merges into one canonical (Vid Velayutham); M3.3 produced exactly one `call_classification_history` row from a live UI edit. See `docs/agents/gregory.md` § Build log for the full M2.3a → M3.3 detail.

**Phase 2: Gregory brain V1.1 — COMPLETE (architecture).** Agent at `agents/gregory/` with deterministic signal computations (call cadence, open / overdue action items, NPS), scoring rubric → green/yellow/red tier with insufficient-data default, and Claude-driven concerns generation. First all-active sweep landed 132 `client_health_scores` rows with tier distribution 93 green / 40 yellow / 0 red. Health Score indicator on the dashboard now shows real numbers + tier + factors breakdown for every active client. **Concerns generation gated behind `GREGORY_CONCERNS_ENABLED` env var (default false)** pending Nabeel decision on LLM cost (~$5–10/month at weekly cadence; ~85% of clients have empty input today, so most calls would skip Claude per the per-client gate). Weekly cron at `/api/gregory_brain_cron` (Mondays 09:00 UTC) — first scheduled fire happens next Monday. Manual trigger available via `scripts/run_gregory_brain.py`.

**Next phase to scope: TBD.** Candidates after the Fathom webhook diagnostic + Nabeel sync land: NPS ingestion (would unlock the latent Gregory NPS signal beyond neutral default), Slack ingestion to cloud (would unlock the deferred Slack engagement signal), CSM Co-Pilot V1 (the next named agent), or M2.5 Aman manual review using the now-shipped Calls page (was originally next-up before M3 took over).

**Pilot clients for Ella V1 beta:** Fernando G, Javi Pena, Musa Elmaghrabi, Jenny Burnett, Dhamen Hothi, Trevor Heck, Art Nuno. (Nicholas LoScalzo deferred — see `docs/future-ideas.md`.) Scott has already announced Ella to these channels.

### Deferrals worth knowing about

Documented in `docs/future-ideas.md` and `docs/followups.md` with explicit revisit triggers:

- Fathom webhook subscription registration (realtime path silent for 7+ days; cron is the sole working ingest path — followup logged for ~15 min next-session diagnostic).
- NPS ingestion pipeline (no signals in cloud; Gregory's `latest_nps` reads as neutral for every client).
- Cloud Slack ingestion (slack_messages cloud table empty; Gregory's Slack engagement signal intentionally absent in V1.1).
- Drive-sourced content ingestion (today's pipeline reads from `data/course_content/`; Drive API + version-awareness comes later).
- `team_members.slack_user_id` backfill sweep for unresolved Slack authors (~94 of 2,914 messages are `unknown`).
- Browser-direct RLS policies (V1 is service-role only).
- Atomic per-call ingest via Postgres RPC (V1 pipeline is non-atomic + idempotent on re-run).
- Ella V1.1 items: cool-down on correction, formal eval harness, per-channel `ella_enabled` gating, thumbs-up/down reactions, impersonation/replay mode, Nicholas LoScalzo onboarding.
- Gregory rubric polish: never-called clients land green via the "0 action items = clean docket" interpretation; followup logged with two resolution options.
- Surface `alternate_emails` / `alternate_names` on Clients detail page (M3.2 follow-up; merge data is correct, the dashboard just doesn't render it).
- `calls.summary` column unused (cron writes summaries to `documents` instead; either backfill or drop in a small migration).

## Live System State

As of 2026-04-29 (M3 close-out):

- **Cloud Supabase** is the production target. Project ref `sjjovsjcfffrftnraocu` (region us-east-2, Ohio). **16 migrations applied** (`0001_core_entities` through `0016_update_call_classification_function`). 0015 (`merge_clients` RPC, M3.2) and 0016 (`update_call_classification` RPC, M3.3) both applied via Studio + manual ledger registration this session and dual-verified (function exists in `pg_proc` with right signature + `security definer = true`; ledger row landed). Accessed via the pooler URL stored in `supabase/.temp/pooler-url`; the DB password lives in `.env.local` as `SUPABASE_DB_PASSWORD` (quoted because it contains a `#`).
- **Local Supabase** (Docker stack at `127.0.0.1:54321`, Postgres on `:54322`) is a dev-only mirror — useful for harness runs and inspection. Not consulted by any deployed component. `.env.local`'s `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` carry cloud values; local connections require explicit `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
- **Vercel deployment** live at `https://ai-enablement-sigma.vercel.app`. Single project, mixed-framework: Next.js 14 dashboard at repo root + **four** Python serverless functions in `api/`. `vercel.json` declares `"framework": "nextjs"` (required — explicit `functions` block suppresses Vercel's framework auto-detection without it) plus per-file Python runtimes: `api/slack_events.py` (Ella's Slack handler, `maxDuration: 60`), `api/fathom_events.py` (Fathom webhook, `maxDuration: 60`), `api/fathom_backfill.py` (daily cron, `maxDuration: 300`), `api/gregory_brain_cron.py` (weekly cron, `maxDuration: 300` — added M3.4). Vercel Cron schedules: `0 8 * * *` (daily 08:00 UTC) targets `/api/fathom_backfill`; `0 9 * * 1` (weekly Mondays 09:00 UTC) targets `/api/gregory_brain_cron` (first scheduled fire happens next Monday). Env vars in production: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_USER_TOKEN`, `FATHOM_WEBHOOK_SECRET`, `FATHOM_API_KEY`, `FATHOM_BACKFILL_AUTH_TOKEN`, `CRON_SECRET`, **`GREGORY_BRAIN_CRON_AUTH_TOKEN`** (M3.4, set by Drake post-push). `GREGORY_CONCERNS_ENABLED` is intentionally unset — Gregory brain treats anything other than `true`/`1`/`yes` as off.
- **Gregory dashboard** live. Routes: `/login`, `/clients`, `/clients/[id]`, `/calls`, `/calls/[id]` — all five fully functional. Auth via Supabase Auth (email/password, manually invited users). Auth gate via Server Component layout. Two Supabase clients by privilege: anon key + cookies for the auth gate (`lib/supabase/server.ts`), service role + no cookies + `'server-only'` guard for data reads (`lib/supabase/admin.ts`). RLS off in spirit for V1. **Clients pages** behavior-verified end-to-end in M3.1 (smoke test passed: list + filter + sort + inline edit + CSM swap). **Merge feature** live (M3.2) with the "Merge into…" button on `needs_review`-tagged client detail pages — TypeScript-native via the `merge_clients` RPC; the historical Python `scripts/archive/merge_client_duplicates.py` remains for reference. **Calls pages** live (M3.3) with edit-mode classification on Section 2; Save writes one row per changed field to `call_classification_history` via the `update_call_classification` RPC. Reusable `SearchableClientSelect` component shared across the merge dialog (M3.2) and Calls list filter (M3.3). **Health Score indicator** on `/clients/[id]` now renders for every active client (133 health-score rows live; tier distribution 93 green / 40 yellow / 0 red).
- **Slack app:** configured, installed in `#ella-test-drakeonly` (Drake-only test, mapped to Javi Pena's `client_id` as a temporary fixture), `#ella-test`, and the 7 pilot client channels. Event Subscriptions enabled; `app_mention` subscribed; signing-secret-verified. Bot scopes + `chat:write` user scope (M1.4.1). The `@ella` Slack user account ran the install and produced the `xoxp-` user token in Vercel as `SLACK_USER_TOKEN`. Ella the user is currently invited to `#ella-test-drakeonly` only — pilot channels still pending (M1.4.5).
- **Ella:** agent code in `agents/ella/`. M1.3 mrkdwn formatter live; M1.4.3 user-token reply path live (no APP tag in `#ella-test-drakeonly`). Awaiting Nabeel's read; M1.4.5 pilot rollout gated on it. `agent_runs.duration_ms` still `NULL` for Ella's runs — deferred per `docs/followups.md`. (Gregory's runs DO populate `duration_ms` — the M3.4 wiring closes that gap for the new agent.)
- **Fathom webhook handler:** `api/fathom_events.py` deployed. **Realtime path silent for 7+ days** (`webhook_deliveries.source='fathom_webhook'` count over the last 7 days = 0). The daily backfill cron has been the sole ingest path (46 `fathom_cron` deliveries in the same window, all processed cleanly). Diagnosis steps logged in `docs/followups.md` for next session; ~15 min check.
- **Fathom backfill cron:** `api/fathom_backfill.py` deployed. Daily 08:00 UTC. Currently the only working ingest path; reliable since M1.2.5.
- **Gregory brain (M3.4):** agent code in `agents/gregory/`. First all-active sweep ran 2026-04-29 evening as a manual trigger via `scripts/run_gregory_brain.py --all` — landed **133 `agent_runs` rows** (1 single-client Vid verification + 132 all-active sweep, every per-client compute opens its own row, all `trigger_type='manual'`, all `status='success'`, `duration_ms` populated) and **133 `client_health_scores` rows** with 1:1 traceability via `computed_by_run_id`. Tier distribution: 93 green / 40 yellow / 0 red; zero `insufficient_data` rows. **Concerns generation gated** (`GREGORY_CONCERNS_ENABLED` env var unset → flag false → no Claude calls in this sweep). First scheduled cron run lands next Monday 09:00 UTC.
- **Test suite:** 381 passing (344 prior baseline + 37 new M3.4 Gregory tests covering signal math, scoring rubric edge cases, concerns-parser robustness, and end-to-end agent wiring).

## Next Session Priorities

Pick these up in order. **Read this section first** when starting a new session — it's the single source of truth for where to start.

1. **Diagnose Fathom realtime webhook silence (FIRST task, ~15 min).** `webhook_deliveries.source='fathom_webhook'` count over the last 7 days = 0; the daily backfill cron has been the sole ingest path. Most likely the webhook subscription dropped at Fathom's side. Steps in `docs/followups.md` § "Fathom realtime webhook silent for 7+ days":
   - Log into Fathom → API/webhook settings → check whether a subscription against `https://ai-enablement-sigma.vercel.app/api/fathom_events` is registered and active.
   - If MISSING → re-register per `docs/runbooks/fathom_webhook.md`, capture new `whsec_` secret, update Vercel `FATHOM_WEBHOOK_SECRET`, redeploy.
   - If PRESENT → check Vercel function logs for `/api/fathom_events` (401s = signature mismatch; absence = Fathom's edge dropping).
   - Verify with a short test recording (≥90 sec) and watch `webhook_deliveries` for the new row.
   Time-sensitive because the freshness gap (up to 24h on cron-only) shouldn't drift longer.

2. **Nabeel sync on two open decisions.** Conversation-blockers, not engineering work:
   - **(a) M1.4.3 user-token reply read** (open since M1.4.3 ship; still pending). Does the no-APP-tag reply path address the "looks unprofessional" feedback? Gates **(3)** below.
   - **(b) `GREGORY_CONCERNS_ENABLED` greenlight on LLM spend** (~$5–10/month at weekly cadence; per-client gating skips Claude when input is empty, so most of today's 132 clients would skip on first run anyway). Architecture is fully built and live; flipping the Vercel env var to `true` activates concerns generation on next Monday's cron run. Gates **(4)** below.

3. **M1.4.5 — pilot rollout if (2a) greenlit.** Invite the `@ella` Slack user to the 6 remaining pilot channels (Fernando G / Musa / Jenny / Dhamen / Trevor / Art). ~30 min via Slack channel UI. No code work.

4. **Manual single-client verification of `GREGORY_CONCERNS_ENABLED` if (2b) greenlit.** Flip the env var in Vercel to `true`, run `python scripts/run_gregory_brain.py --email <pilot-with-summaries>` for one client (Vid Velayutham has summary coverage and is a known-shape test target), review the concerns Claude produced for shape and quality (look in `factors.concerns[]` of the produced row). Only after that's clean does the Monday cron run all-active with concerns on.

5. **Repo polish carry-overs (small, can be batched into one short session):**
   - Surface `metadata.alternate_emails` / `metadata.alternate_names` on Clients detail page Section 1 (M3.2 follow-up; data is correct, dashboard just doesn't render). ~30 min.
   - Resolve the `calls.summary` unused column (M3.3 follow-up; either backfill at ingest or drop in a small migration). ~30 min plus the migration.
   - Gregory rubric quirk fix (M3.4 follow-up; never-called clients land green via the "0 action items = clean docket" interpretation). Lean: scope `insufficient_data=true` to "no cadence" rather than only the all-neutral case. ~30 min plus a re-run to refresh the 132 health-score rows.

6. **(deferred) NPS ingestion pipeline.** Would activate Gregory's `latest_nps` signal beyond neutral default. Design conversation needed first (where do scores come from? Survey tool integration? Manual entry via dashboard?).

7. **(deferred) Slack 90-day backfill to cloud.** Unchanged. Would unblock a fifth Gregory signal (Slack engagement) once added.

8. **(deferred) M2.5 — Aman manual review using the now-shipped Calls page.** Unchanged. Reclassify ~66 external calls one-at-a-time via the Calls page Needs-review filter. Pure dashboard usage; no engineering work.

9. **(deferred) CSM Co-Pilot V1.** The next named agent. Was Phase 3 in the original Phase plan; no architectural blockers now that Gregory brain is shipped.

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
