# CLAUDE.md

Primary context for any Claude Code instance working on this repo. Read this fully before making changes.

## Project Purpose

Internal AI enablement system for a coaching/consulting agency. Replaces and augments human work across customer success, sales, and operations. The consumer business runs on this system first; later, the same system will be deployed to other agencies as a productized consulting offering.

**Immediate focus:** M5 V1-adoption — cleanup fully closed; Scott onboarding (transition off the master sheet onto Gregory) is tomorrow's session. Ella V1 in pilot (live, awaiting Nabeel feedback before pilot rollout to remaining 6 channels) — unchanged since M4. See § Current Focus for the active work breakdown.

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
│   ├── migrations/             # Numbered SQL migration files (0001–0021 applied to cloud via Studio + manual ledger)
│   └── seed/                   # Seed data for local testing
├── ingestion/                  # Data ingestion pipelines (all built and applied locally)
│   ├── fathom/                 # Call transcripts — backlog `.txt` path + realtime webhook live
│   ├── slack/                  # Channel history backfill (REST only; Events API deferred)
│   ├── content/                # Filesystem-sourced HTML lessons (Drive API deferred)
│   └── crm/                    # (planned)
├── api/                        # Vercel Python serverless functions (6 deployed)
│   ├── slack_events.py         # Ella's Slack handler (M1.x)
│   ├── fathom_events.py        # Fathom realtime webhook (M4.1 restored)
│   ├── fathom_backfill.py      # Daily cron — Fathom backlog backstop
│   ├── gregory_brain_cron.py   # Weekly cron — Gregory brain sweep
│   ├── airtable_nps_webhook.py # Airtable NPS Path 1 receiver (M5.4)
│   ├── accountability_roster.py # Path 2 outbound roster GET endpoint (Make.com daily pull)
│   └── airtable_onboarding_webhook.py # Path 3 inbound onboarding form receiver (M5.9)
├── app/                        # Next.js 14 dashboard routes (Gregory)
├── components/                 # Dashboard UI — top-nav, ui/* primitives, client-detail/*
├── lib/                        # Dashboard utilities — db/, supabase/, etc.
├── agents/                     # Agent implementations
│   ├── ella/                   # Slack Bot V1 — agent.py, retrieval.py, prompts.py,
│   │                           # escalation.py, slack_handler.py
│   ├── gregory/                # Brain V1.1 — signal computations, scoring rubric, concerns gen
│   └── csm_copilot/            # (planned — follows Ella)
├── orchestration/              # n8n workflow exports (JSON)
├── shared/                     # Shared Python utilities
│   ├── claude_client.py        # Anthropic API wrapper (cost tracking via run_id)
│   ├── kb_query.py             # Knowledge base retrieval (wraps match_document_chunks RPC)
│   ├── hitl.py                 # Human-in-the-loop escalation helper
│   ├── logging.py              # Structured logging + agent_runs lifecycle (start_agent_run / end_agent_run)
│   ├── db.py                   # Supabase client setup
│   └── ingestion/
│       └── validate.py         # documents / document_chunks metadata validator — REQUIRED for new pipelines
├── evals/                      # Golden datasets + eval runner (empty for now; Ella V1 ships without)
├── scripts/                    # Active tooling — re-runnable seeds, local test harnesses, admin tasks, one-shots
│   ├── seed_clients.py         # Load Active++ view into clients + client_team_assignments
│   ├── import_master_sheet.py  # Financial Master Sheet → cloud, dry-run + apply (M4 Chunk C)
│   ├── backfill_nps_from_airtable.py    # One-shot Airtable NPS Survery → Gregory backfill (M5.4)
│   ├── run_gregory_brain.py    # Manual Gregory brain trigger (CLI alongside the cron path)
│   ├── test_ella_locally.py    # Reusable Ella-handler driver (pre-launch + bug repro)
│   ├── test_fathom_backfill_locally.py  # Local harness for the Fathom cron path
│   ├── test_fathom_webhook_locally.py   # Local 5-path test loop for the Fathom webhook
│   ├── test_airtable_nps_webhook_locally.py  # Local 8-path test loop for the Airtable receiver (M5.4)
│   ├── test_airtable_onboarding_webhook_locally.py  # Local 11-path test loop for the Path 3 onboarding receiver (M5.9)
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

M5 V1 adoption — cleanup fully closed; Scott begins daily Gregory use starting tomorrow. Driving framing came from Scott's 1:1 on 2026-05-01: V1 = "match the Financial Master Sheet so Scott will adopt Gregory daily." Anything Scott doesn't adopt is V2 territory regardless of architectural cleanliness. The 2026-05-04 → 2026-05-05 window closed every adoption-blocker: dashboard surfaces match the master sheet vocab + cascade semantics; Path 2 outbound roster replaced the master sheet as Make.com's daily source; Gregory clients now match the canonical CSV 1:1 (188 ↔ 188); 4 historical NPS 404s resolved. Post-cleanup, the dashboard is the source of truth. Monday 2026-05-06 onboarding transitions Scott off the master sheet onto Gregory.

**Recent close-outs (2026-05-04 → 2026-05-05) — see `docs/agents/gregory.md` § Build log for the full timeline:**
- **M5.6** + same-day hotfix — DB-level status cascade (negative-going status auto-flips csm_standing/toggles/primary_csm), Scott Chasing sentinel, accountability/nps toggles. Three visual-smoke regressions caught + fixed (EditableField stale-closure, change_primary_csm ON CONFLICT).
- **Path 2 outbound roster** — `api/accountability_roster.py` deployed; Make.com daily-pull GET endpoint replacing the Financial Master Sheet as Zain's automation source. Reshaped from event-driven UPDATE listener by the Make.com walkthrough with Zain.
- **M5 cleanup pass** (3 scripts) — `cleanup_master_sheet_reconcile.py` + `cleanup_master_sheet_completeness.py` + `archive_misclassified_clients.py`. Reconcile applied 95 + 24 writes (status flips, csm_standing flips, primary_csm reassignments, trustpilot, handover notes). Completeness autocreated 8 + filled 180 country / 180 start_date / 92 phone / 1 slack_user_id / 29 slack_channels. Walkthrough closed 12 merges + 13 detags. Archive closed 3 misclassified (Andrés González hiring interview, Aman internal teammate, Branden Bledsoe Isabel-rep). End state: 188 non-archived clients perfect 1:1 with the 188-row master sheet.
- **NPS 404 resolution** — `add_alternate_emails_batch.py` closed 4 historical mismatches (Cheston, Yeshlin, Luis, Jonathan); NPS backfill re-run moved 59 → 61 successes / 2 → 0 client-not-found.
- **Earlier in the week**: M5.3 status vocab + leave (2026-04-29), M5.3b trustpilot rename, M5.4 NPS Path 1 receiver + 79-row backfill, M5.5 9-dropdown filter bar on `/clients` (2026-05-03).

**Phase 0 foundation: complete.** All ingestion pipelines built and applied. Slack history (2,914 messages across 8 channels) exists on **local** only — cloud Slack ingestion deferred per `docs/future-ideas.md`. Shared utilities, validators, and HITL infrastructure in place.

**Phase 1: Ella V1 — live and operating, polish in progress.** Agent code in `agents/ella/`. Slack webhook live, smoke-tested, replying with native Slack mrkdwn (M1.3) and posting via `@ella` user token (M1.4.3) so replies render with no APP tag in `#ella-test-drakeonly`. Fathom backlog fully ingested; realtime webhook restored M4.1 (id `FTVBjD_JqTfjEzVA`) and naturally exercised by the 2026-05-01 CSM sync's recordings. **Phase 1 polish remaining:** awaiting Nabeel's read on whether M1.4.3's user-token-reply addresses his "looks unprofessional" feedback before pilot rollout to remaining 6 channels (M1.4.5).

**Phase 2: Gregory dashboard V1 — M5 V1 adoption shipped, ready for Scott's daily use.** M3 shipped the Clients pages (list + detail + inline-save + CSM-swap dialog), Calls pages (list + detail + edit-mode classification + `call_classification_history`), and the merge feature for auto-created clients. M4 added the V1 client page schema (7-section detail-page, inline-edit, history-writing RPCs, NPS-entry, master-sheet import). M5 refined for adoption: status vocab + trustpilot vocab match Scott's master sheet (M5.3 + M5.3b); NPS Path 1 (Airtable → Gregory) is live (M5.4); NPS Standing surfaces in Section 2 (M5.4 follow-up); 9-dropdown filter bar on `/clients` (M5.5); DB-level status cascade + Scott Chasing sentinel + accountability/NPS toggles (M5.6 + same-day hotfix); Path 2 outbound roster (Make.com daily-pull GET); full master sheet ↔ Gregory cleanup (reconcile + completeness + walkthrough + misclassified-client archive — 188 ↔ 188 perfect 1:1). See `docs/agents/gregory.md` § Build log for the full timeline.

**Phase 2: Gregory brain V1.1 — V2 territory now.** Agent at `agents/gregory/` with deterministic signal computations + scoring rubric + Claude-driven concerns generation. First all-active sweep landed 133 `client_health_scores` rows (93 green / 40 yellow / 0 red); next sweep runs against the post-cleanup 188 non-archived clients. **Concerns generation still gated** (`GREGORY_CONCERNS_ENABLED` env var unset). Weekly cron at `/api/gregory_brain_cron` (Mondays 09:00 UTC). Per the M5 V1-adoption pivot, the brain's summary-driven concerns work moved to V2 — sits on top of an adopted V1, not underneath an unadopted one. The health score indicator continues to render as-is in Section 2; flipping the concerns flag when summary density grows organically is a one-toggle action whenever V2 cycles begin.

**Phase 3 candidates (post-onboarding, M5 backlog):** trustpilot auto-correct on standing change (Scott's Loom 2 — sits on top of M5.6 cascade infrastructure), country promotion to a real `clients` column (Australia/US tagging — currently `clients.country` populated by completeness pass; the M5.5 disabled "Country" filter dropdown is the next-slice surface), May meetings tracker + inactivity flag (call-count aggregation), CSM-edit lockdown (Scott's Loom 1). V2 territory: action item HITL (AI-draft → CSM-review → client-send), CSM Co-Pilot V1, classifier extensions for new title prefixes + classifier tuning (hiring-interview FP, representative-of-existing-client FP, iMIP email handling — see followups), Gregory concerns activation, NPS score piping (V1.5).

**Pilot clients for Ella V1 beta:** Fernando G, Javi Pena, Musa Elmaghrabi, Jenny Burnett, Dhamen Hothi, Trevor Heck, Art Nuno. (Nicholas LoScalzo deferred — see `docs/future-ideas.md`.) Scott has already announced Ella to these channels.

### Deferrals worth knowing about

Documented in `docs/future-ideas.md` and `docs/followups.md` with explicit revisit triggers:

- ~~Path 3 inbound (onboarding form receiver) — shipped M5.9 (2026-05-05).~~ Future Gregory→Airtable outbound writebacks beyond accountability/NPS (e.g., csm_standing changes flowing back to Airtable) remain deferred until a concrete need surfaces. The "Path 3" label in the codebase now refers to the M5.9 inbound onboarding receiver; outbound writebacks would be a future Path 4 if/when needed.
- Cloud Slack ingestion (slack_messages cloud table empty; Gregory's Slack engagement signal intentionally absent in V1.1).
- Drive-sourced content ingestion (today's pipeline reads from `data/course_content/`; Drive API + version-awareness comes later).
- `team_members.slack_user_id` backfill sweep for unresolved Slack authors (~94 of 2,914 messages are `unknown`).
- Browser-direct RLS policies (V1 is service-role only).
- Atomic per-call ingest via Postgres RPC (V1 pipeline is non-atomic + idempotent on re-run).
- Ella V1.1 items: cool-down on correction, formal eval harness, per-channel `ella_enabled` gating, thumbs-up/down reactions, impersonation/replay mode, Nicholas LoScalzo onboarding.
- Gregory rubric polish: never-called clients land green via the "0 action items = clean docket" interpretation; followup logged with two resolution options.
- Surface `alternate_emails` / `alternate_names` on Clients detail page (M3.2 follow-up; merge data is correct, the dashboard just doesn't render it).
- `calls.summary` column unused (cron writes summaries to `documents` instead; either backfill or drop in a small migration).
- 4 manual-override-sticky NPS divergences (Tina Hussain / Jenny Burnett / Mary Kissiedu / Saavan Patel — all CSM-judged-harsher-than-NPS). Discussion item for Scott's onboarding, not a code task.
- Master-sheet-seed treatment for csm_standing auto-derive eligibility — architectural question pending Monday onboarding decision (current behavior: master-sheet-seeded csm_standing rows have `changed_by=NULL` → ineligible for auto-derive forever).
- `lib/supabase/types.ts` manual edits required until Supabase CLI regen path is restored.
- Action item editing HITL (AI-draft → CSM-review → client-send, per Nabeel's transcript vision). V2 territory.
- Repo cleanup pass — broader sweep beyond `scripts/` (per existing followup).

## Live System State

As of 2026-05-05 (M5 cleanup fully closed — Path 2 deployed, Gregory ↔ master sheet 1:1, NPS 404s resolved):

- **Cloud Supabase** is the production target. Project ref `sjjovsjcfffrftnraocu` (region us-east-2, Ohio). **25 migrations applied** (`0001_core_entities` through `0025_create_or_update_client_from_onboarding`). 0017 added 14 columns to `clients` + 1 column to `nps_submissions` + 4 history/upsell tables (M4 Chunk A). 0018 added 4 `security definer` Postgres functions for atomic update + history-row writes (M4 Chunk B2). 0019 (`status_add_leave`) added the first DB-level CHECK on `clients.status` and expanded the vocabulary to include `leave`; replaced `update_client_status_with_history` to mirror the new allowlist (M5.3). 0020 (`trustpilot_rename_vocab`) renamed `clients.trustpilot_status` 1:1 to match Scott's master sheet (`given`→`yes`, `declined`→`no`, `not_asked`→`ask`, `pending`→`asked`) (M5.3b). 0021 (`nps_standing_and_gregory_bot`) added `clients.nps_standing` + Gregory Bot sentinel team_member (UUID `cfcea32a-062d-4269-ae0f-959adac8f597`) + `update_client_from_nps_segment` RPC for the Airtable Path 1 receiver (M5.4). 0022 (`status_cascade`) added `clients.accountability_enabled` + `clients.nps_enabled` + `team_members.is_csm` + Scott Chasing sentinel (UUID `ccea0921-7fc1-4375-bcc7-1ab91733be73`) + BEFORE/AFTER triggers on `clients` for the negative-status cascade + GUC-aware update of `update_client_status_with_history` for human attribution on cascade history rows (M5.6). 0023 (`change_primary_csm_on_conflict`) replaced the 0014 RPC with an `ON CONFLICT DO UPDATE` variant so dashboard-driven swap-back-to-archived-CSM (A → B → A) succeeds instead of erroring on the unique key — mirrors the M5.6 cascade trigger's pattern (M5.6 hotfix). 0024 (`trustpilot_cascade_on_happy`) added a one-directional BEFORE UPDATE trigger that auto-flips `clients.trustpilot_status` to `'ask'` when `csm_standing` transitions to `'happy'`; alphabetically-ordered against the M5.6 status cascade so negative-going status dominates if both trigger conditions co-occur in one UPDATE (M5.7). 0025 (`create_or_update_client_from_onboarding`) added the security-definer RPC for Path 3 inbound (the Airtable onboarding form receiver): match-or-create on email + alternate_emails with three branches (active match → updated; archived match → reactivated; no match → created), seeds status/csm_standing history rows attributed to Gregory Bot, raises structured exceptions for slack_user_id / slack_channel_id conflicts the receiver translates to HTTP 409 (M5.9). All applied via Studio + manual ledger registration + dual-verified (0022/0023/0024/0025 applied via psycopg2 since psql isn't installed in this environment, but the dual-verify pattern held). Accessed via the pooler URL stored in `supabase/.temp/pooler-url`; the DB password lives in `.env.local` as `SUPABASE_DB_PASSWORD` (quoted because it contains a `#`).
- **Local Supabase** (Docker stack at `127.0.0.1:54321`, Postgres on `:54322`) is a dev-only mirror — useful for harness runs and inspection. Not consulted by any deployed component. `.env.local`'s `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` carry cloud values; local connections require explicit `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
- **Vercel deployment** live at `https://ai-enablement-sigma.vercel.app`. Single project, mixed-framework: Next.js 14 dashboard at repo root + **seven** Python serverless functions in `api/`. `vercel.json` declares `"framework": "nextjs"` (required — explicit `functions` block suppresses Vercel's framework auto-detection without it) plus per-file Python runtimes: `api/slack_events.py` (Ella's Slack handler, `maxDuration: 60`), `api/fathom_events.py` (Fathom webhook, `maxDuration: 60`), `api/fathom_backfill.py` (daily cron, `maxDuration: 300`), `api/gregory_brain_cron.py` (weekly cron, `maxDuration: 300`), `api/airtable_nps_webhook.py` (Airtable NPS receiver, `maxDuration: 60` — added M5.4 Path 1), `api/accountability_roster.py` (Make.com Path 2 outbound roster GET, `maxDuration: 60` — added 2026-05-04), `api/airtable_onboarding_webhook.py` (Path 3 inbound onboarding form receiver, `maxDuration: 60` — added M5.9). Vercel Cron schedules: `0 8 * * *` (daily 08:00 UTC) → `/api/fathom_backfill`; `0 9 * * 1` (weekly Mondays 09:00 UTC) → `/api/gregory_brain_cron`. Env vars in production: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_USER_TOKEN`, `FATHOM_WEBHOOK_SECRET`, `FATHOM_API_KEY`, `FATHOM_BACKFILL_AUTH_TOKEN`, `CRON_SECRET`, `GREGORY_BRAIN_CRON_AUTH_TOKEN`, `AIRTABLE_NPS_WEBHOOK_SECRET` (M5.4), `MAKE_OUTBOUND_ROSTER_SECRET` (Path 2 outbound, 2026-05-04), `AIRTABLE_ONBOARDING_WEBHOOK_SECRET` (Path 3 inbound, M5.9). `GREGORY_CONCERNS_ENABLED` is intentionally unset — Gregory brain treats anything other than `true`/`1`/`yes` as off.
- **Gregory dashboard** live with the V1 client page schema (M4) + M5 vocab updates + M5.5 filter bar + M5.6 cascade toggles (shipped 2026-05-04, visual smoke passed same day after a hotfix for three regressions — see Build log). Routes: `/login`, `/clients`, `/clients/[id]`, `/calls`, `/calls/[id]`. The client detail page is the v3 7-section layout (Identity & Contact / Lifecycle & Standing / Financials / Activity & Action Items / Profile & Background / Adoption & Programs / Notes) with full inline-edit. Status / journey_stage / csm_standing edits route through the migration-0018 RPC functions for atomic update + history-row writes (status RPC was replaced in 0019 to include `leave` in the allowlist). Section 2 NPS Standing pill (M5.4) renders `clients.nps_standing` via `components/client-detail/nps-standing-pill.tsx` (replaced the M4 "Latest NPS" field which read `nps_submissions.score` — that field stays in the data layer for V1.5 score-piping but no UI surfaces it today). NpsEntryForm (manual NPS-score entry from a CSM) preserved below the pill — different data source. List page filter bar (M5.5) is a 9-dropdown row: 5 active multi-selects (Status / Primary CSM / CSM Standing / NPS Standing / Trustpilot), 1 single-value toggle (Needs review), 3 disabled placeholders (Accountability / NPS toggle / Country) signaling next-slice work. Status pre-checks `active+paused+ghost` via the absent-param sentinel (the prior M5.3 "Show churned & leave" toggle chip is gone — checking Churned/Leave in the Status dropdown now does that job). Vocab module at `lib/client-vocab.ts` is the single source of truth shared with the inline-edit dropdowns + the NpsStandingPill. Adoption section's trustpilot dropdown surfaces vocab `Yes` / `No` / `Ask` / `Asked` (M5.3b, options imported from vocab module post-M5.5). Auth via Supabase Auth (email/password, manually invited users) via the (authenticated) layout. Two Supabase clients by privilege: anon key + cookies for the auth gate, service role + `'server-only'` guard for data reads.
- **`clients` table population (post-cleanup, 2026-05-05):** **188 non-archived clients** — perfect 1:1 with the 188-row canonical master sheet at `data/master_sheet/master-sheet-05-04/`. Post-cleanup state: every negative-status client has `csm_standing='at_risk'` + `accountability_enabled=false` + `nps_enabled=false` (M5.6 cascade); every active client has the toggles at default `true`. `country` populated USA/AUS for every CSV-matched client (180 fills via completeness pass; 15 NULL belong to non-CSV legacy clients). `start_date` populated for every CSV-matched client (180 fills). 4 N/A-status autocreates carry `metadata.original_master_sheet_status='N/A'` for forensics (Vaishali Adla, Scott Stauffenberg, Clyde Vinson, Rachelle Hernandez). 3 misclassified clients soft-archived with `metadata.archived_via='m5_cleanup_misclassification_archive'` (Andrés González, Aman, Branden Bledsoe). **`clients.nps_standing` populated for 61 active clients** (was 59 — Jonathan + Luis closed via the alternate-emails resync). `client_status_history` + `client_standing_history` carry the M5.6 cascade backfill rows (`cascade:backfill:m5.6`, `cascade:status_to_<x>:by:<uuid>`) + the cleanup pass rows (`cleanup:m5_master_sheet_reconcile`, `cleanup:m5_completeness`) — all SQL-joinable to attribute every cleanup-driven row to its pass. Reconcile dry-run is fully idempotent against the canonical CSV (0 Tier 1 changes).
- **Slack app:** configured, installed in `#ella-test-drakeonly` (Drake-only test, mapped to Javi Pena's `client_id` as a temporary fixture), `#ella-test`, and the 7 pilot client channels. Event Subscriptions enabled; `app_mention` subscribed; signing-secret-verified. Bot scopes + `chat:write` user scope (M1.4.1). The `@ella` Slack user account ran the install and produced the `xoxp-` user token in Vercel as `SLACK_USER_TOKEN`. Ella the user is currently invited to `#ella-test-drakeonly` only — pilot channels still pending (M1.4.5).
- **Ella:** agent code in `agents/ella/`. M1.3 mrkdwn formatter live; M1.4.3 user-token reply path live (no APP tag in `#ella-test-drakeonly`). Awaiting Nabeel's read; M1.4.5 pilot rollout gated on it. `agent_runs.duration_ms` still `NULL` for Ella's runs — deferred per `docs/followups.md`.
- **Fathom webhook handler (M4.1 closed):** `api/fathom_events.py` deployed and **realtime path live**. M4.1 re-registered fresh via `POST /external/v1/webhooks` (id `FTVBjD_JqTfjEzVA`), rotated `whsec_` secret into Vercel, redeployed, verified bad-signature → 401 path. End-to-end smoke test naturally exercised by the 2026-05-01 CSM sync's recordings.
- **Fathom backfill cron:** `api/fathom_backfill.py` deployed. Daily 08:00 UTC. Backstop to the realtime webhook; reliable since M1.2.5.
- **Airtable NPS webhook receiver (M5.4 Path 1):** `api/airtable_nps_webhook.py` deployed. Auth via `X-Webhook-Secret` header (`AIRTABLE_NPS_WEBHOOK_SECRET` env var, `hmac.compare_digest`). Calls `update_client_from_nps_segment(email, segment)` after normalizing Airtable's raw segment string (`Strong / Promoter` / `Neutral` / `At Risk`) to lowercase. Override-sticky csm_standing semantics enforced inside the RPC: auto-derive only when current `csm_standing` is null OR the most recent `client_standing_history.changed_by = Gregory Bot UUID`. Make.com automation enabled in Airtable (Survey Date or Segment Classification field changes auto-fire the webhook). Historical 79-row Survery table backfilled via `scripts/backfill_nps_from_airtable.py` on 2026-05-03 — 61 deduped clients, 59 success, 2 404 (email mismatch, in cleanup queue). 8-path local test harness at `scripts/test_airtable_nps_webhook_locally.py`.

- **Airtable onboarding form receiver (M5.9 Path 3 inbound):** `api/airtable_onboarding_webhook.py` deployed. Auth via `X-Webhook-Secret` header (`AIRTABLE_ONBOARDING_WEBHOOK_SECRET` env var, `hmac.compare_digest`). 7-field payload (full_name / email / phone / country / date_joined / slack_user_id / slack_channel_id), all required. Calls `create_or_update_client_from_onboarding` (migration 0025) which match-or-creates on email + alternate_emails. Three branches surface in the response `action` field: `created` (new INSERT with status='active' + csm_standing='content' + tags=['needs_review'] + Gregory Bot–attributed history seeds), `updated` (existing active match — backfill nullable fields, refresh status/csm_standing/tags, never overwrite established data), `reactivated` (existing archived match — clear `archived_at`, then same field updates as `updated`). Slack ID conflicts (slack_user_id mismatch, slack_channel_id mismatch on this client, channel id owned by different client) raise structured exceptions the receiver translates to HTTP 409 — anti-overwrite by design. 11-path local test harness at `scripts/test_airtable_onboarding_webhook_locally.py` (74/74 green at deploy time; self-seeds an `onboarding-test-update-<token>@nowhere.invalid` fixture rather than relying on production fixture clients).
- **Accountability + NPS daily roster (Path 2 outbound, 2026-05-04):** `api/accountability_roster.py` deployed. GET endpoint Make.com pulls daily, replacing the Financial Master Sheet as the source of truth for Zain's existing accountability + NPS automation. Auth via `X-Webhook-Secret` header (`MAKE_OUTBOUND_ROSTER_SECRET` env var, `hmac.compare_digest`). Returns `{generated_at, count, clients[]}` where each client carries `client_email`, `full_name` (M5.7), `country` + `advisor_first_name` (M5.8), `slack_user_id`, `slack_channel_id`, `accountability_enabled`, `nps_enabled`. `advisor_first_name` is derived from the active primary_csm's `team_members.full_name` via `full_name.split()[0].capitalize()` (whitespace-split, leading-cap-rest-lower; null when no active primary_csm). Single-query embedded join on `slack_channels` + `client_team_assignments(team_members)`; per-client filters mirror `getClientById`'s rules (slack_channel: most recently created non-archived; primary_csm: role='primary_csm' AND unassigned_at IS NULL). Server-side eligibility filter excludes NULL slack_user_id, missing channel, or NULL email so every row is actionable; primary_csm is NOT part of eligibility (clients without a CSM still surface, advisor_first_name emits null). Live count at deploy: **100 actionable clients out of 195 non-archived** (95 filtered); after M5 completeness sweep + M5.7 ship: **128 / 188** (M5.8 unchanged from M5.7). 7-path local test harness at `scripts/test_accountability_roster_locally.py` (22/22 → 23/23 with M5.7 → 27/27 with M5.8). No status filter — Make.com filters on the booleans on its side.
- **Gregory brain (M3.4):** agent code in `agents/gregory/`. First all-active sweep produced 133 `client_health_scores` rows (tier distribution 93 green / 40 yellow / 0 red). **Concerns generation still gated** (`GREGORY_CONCERNS_ENABLED` env var unset; the activation moved to V2 territory per the M5 V1-adoption pivot — sits on top of adopted V1). Next weekly cron sweep (Mondays 09:00 UTC) will run across 197 active clients (was 132 at first sweep).
- **M5 master sheet reconcile + completeness + misclassification archive (cleanup pass, 2026-05-04 → 2026-05-05):** `scripts/cleanup_master_sheet_reconcile.py` — two-phase USA + AUS CSV diff + tiered apply. First run landed 95 explicit DB writes touching ~70 unique clients: 36 status flips, 32 csm_standing flips (4 cascade-redundant skipped), 22 primary_csm reassignments, 13 trustpilot flips, 8 handover notes. **Delta re-run** against the canonical CSVs at `data/master_sheet/master-sheet-05-04/` landed 24 additional primary_csm reverts (cascade had reassigned negative-status clients to Scott Chasing during the prior apply; CSV still had the original real CSM). **Completeness pass** (`scripts/cleanup_master_sheet_completeness.py`) then autocreated 8 unmatched clients (4 N/A statuses → 'churned' with `metadata.original_master_sheet_status='N/A'` for forensics) and filled NULL gaps in crucial fields: 180 country (USA/AUS by tab), 180 start_date, 92 phone, 1 slack_user_id, 29 slack_channels inserts/relinks. **needs_review walkthrough** 2026-05-05 (Drake-driven): 12 merges via the dashboard merge flow, ~13 manual detags, and the 3 misclassification archives below. **Misclassification archive** (`scripts/archive_misclassified_clients.py`, 2026-05-05): 3 Fathom-misclassified clients soft-archived — Andrés González (hiring interview, 3 calls → `external`), Aman (internal teammate, 1 call → `internal`), Branden Bledsoe (Isabel Bledsoe's representative, 1 call repointed to Isabel). 4 linked documents flipped to `is_active=false`. End state: **188 non-archived clients** (perfect 1:1 match to the 188-row master sheet — zero extras on Gregory side, zero unmatched on CSV side). All writes attributed to Gregory Bot UUID with notes `cleanup:m5_master_sheet_reconcile`, `cleanup:m5_completeness`, and `metadata.archived_via='m5_cleanup_misclassification_archive'` for SQL audit. Tier 2 + Tier 3 ambiguities + walkthrough close-out live in `docs/data/m5_cleanup_scott_notes.md` for Scott's onboarding meeting. All three scripts idempotent on re-run; cleanup is the canonical CSV-vs-Gregory reconciler (`import_master_sheet.py` is the build-time seed, not the steady-state tool).
- **Test suite:** 381 passing. M5 work shipped without new tests; UI-side validation came via tsc + ESLint + `next build` clean, end-to-end DB smoke tests for the new RPCs against cloud, and Python harness runs for the Airtable receiver.

## Next Session Priorities

Pick these up in order. **Read this section first** when starting a new session — it's the single source of truth for where to start.

**M5 cleanup fully closed (2026-05-04 → 2026-05-05).** M5.5 (filter bar) → M5.6 (status cascade + hotfix) → Path 2 outbound roster (Make.com daily-pull GET) → M5 cleanup pass (reconcile + completeness + walkthrough + misclassified-client archive — Gregory matches the canonical master sheet 1:1, 188 ↔ 188) → NPS 404 resolution (4 historical mismatches closed via alternate-emails resync). All cleanup work is on origin/main; the dashboard is the source of truth from tomorrow onward. See `docs/agents/gregory.md` § Build log for full close-outs.

1. **Onboard Scott on Gregory for daily use (tomorrow's session).** Walkthrough so Scott transitions off the master sheet onto Gregory. Tier 2 + Tier 3 ambiguities + walkthrough audit trail live in `docs/data/m5_cleanup_scott_notes.md` for the meeting itself: 18 remaining Tier 2 items (slack_user_id ambiguities, email mismatches that can't auto-fill), 15 "Owing Money" standings (CSM annotation), 4 Aleks-owned reassignments (M4 Chunk C carry-over), 67 NPS Standing CSV-vs-Gregory differences (informational; Path 1 owns the column), 4 N/A-as-churned autocreates for Scott's eyeball (discoverable via `WHERE metadata->>'original_master_sheet_status' = 'N/A'`), and 2 positive-transition clients (Marcus Miller, Allison Jayme Boeshans) whose toggles need manual re-activation since the M5.6 cascade is off-only by design.

2. **Trustpilot auto-correct on standing change + Country promotion to client page (in one chunk).** Trustpilot auto-correct (Scott's Loom 2) sits on top of the M5.6 cascade infrastructure — same trigger pattern, different rule (`csm_standing` → certain transitions auto-flip `trustpilot_status`). Country is now populated as a real column via the completeness pass (USA/AUS by tab); the next slice is a migration that promotes it to a CHECK-constrained vocab + a filter surface that retires the disabled "Country" placeholder dropdown from M5.5. Bundled into one chunk because both touch the client-page schema and the M5.5 filter bar.

3. **May meetings tracker + inactivity flag (in one chunk).** Both are aggregations on existing call data. Inactivity flag = end-of-week-2 monthly meeting count (Scott's Loom 2 framing); May meetings tracker = related view of who's met who in the current month. Bundled because the underlying call-aggregation queries are the same shape.

**Below the three (deferred until adoption stabilizes):** CSM-edit lockdown (Scott's Loom 1), NPS score piping (V1.5), classifier tuning (hiring-interview FP, representative-of-existing-client FP, iMIP email handling — see followups for details), V2 territory (action item HITL, CSM Co-Pilot V1, Gregory concerns activation).

**Deferred-decision (Monday onboarding):** master-sheet-import seed treatment for auto-derive eligibility. Per the M5.4 backfill, all 137 master-sheet-seeded `csm_standing` rows are sticky (changed_by=NULL → ineligible for auto-derive). Scott's onboarding decides whether to retroactively reattribute those history rows to Gregory Bot OR keep the current "seed-locked" semantics.

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
