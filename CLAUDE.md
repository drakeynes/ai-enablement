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

Wrapping M4 (V1 client page schema). All four chunks shipped: 0017 schema migration (14 columns + 4 tables), 0018 history-RPCs migration, B1 read-only 7-section detail page, B2 inline-edit + NPS-entry, C master sheet import (197 active clients now in cloud, 69 auto-created). CSM team onboarding to the dashboard at tomorrow's 11am EST sync, including the new call titling convention rollout (`docs/conventions/call_titling.md`). Next session likely picks up post-rollout cleanup + the item Nabeel flags after seeing the live dashboard.

**Phase 0 foundation: complete.** All ingestion pipelines built and applied. Slack history (2,914 messages across 8 channels) exists on **local** only — cloud Slack ingestion deferred per `docs/future-ideas.md`. Shared utilities, validators, and HITL infrastructure in place.

**Phase 1: Ella V1 — live and operating, polish in progress.** Agent code in `agents/ella/`. Slack webhook live, smoke-tested, replying with native Slack mrkdwn (M1.3) and posting via `@ella` user token (M1.4.3) so replies render with no APP tag in `#ella-test-drakeonly`. Fathom backlog fully ingested; realtime webhook restored M4.1 (id `FTVBjD_JqTfjEzVA`) with end-to-end smoke test pending tomorrow's natural CSM-call traffic. **Phase 1 polish remaining:** awaiting Nabeel's read on whether M1.4.3's user-token-reply addresses his "looks unprofessional" feedback before pilot rollout to remaining 6 channels (M1.4.5).

**Phase 2: Gregory dashboard V1 — COMPLETE through M4.** M3 shipped the Clients pages (list + detail + inline-save + CSM-swap dialog), Calls pages (list + detail + edit-mode classification + `call_classification_history`), and the merge feature for auto-created clients (TypeScript-native via the `merge_clients` RPC). M4 extended this with the V1 client page schema: 7-section detail-page layout, inline-edit on every editable field, history-writing RPCs for status / journey_stage / csm_standing, NPS-entry inline form, and master-sheet-imported data live (197 active clients, 69 auto-created). See `docs/agents/gregory.md` § Build log for the full timeline; `docs/client-page-schema-spec.md` is the M4 source of truth.

**Phase 2: Gregory brain V1.1 — COMPLETE (architecture).** Agent at `agents/gregory/` with deterministic signal computations (call cadence, open / overdue action items, NPS), scoring rubric → green/yellow/red tier with insufficient-data default, and Claude-driven concerns generation. First all-active sweep landed 133 `client_health_scores` rows with tier distribution 93 green / 40 yellow / 0 red. Health Score indicator on the dashboard renders real numbers + tier + factors breakdown for every active client. **Concerns generation still gated** (`GREGORY_CONCERNS_ENABLED` env var unset). Weekly cron at `/api/gregory_brain_cron` (Mondays 09:00 UTC). Note: post-M4 Chunk C, the next sweep will run across 197 clients (was 132); rubric behavior on the new auto-created rows is an open observation.

**Phase 3 candidates (post-M4 rollout):** action item editing (HITL — AI-draft → CSM-review → client-send, per Nabeel's transcript vision), CSM Co-Pilot V1, NPS / Airtable webhook receiver. List-page filters and repo cleanup are smaller deferred items.

**Pilot clients for Ella V1 beta:** Fernando G, Javi Pena, Musa Elmaghrabi, Jenny Burnett, Dhamen Hothi, Trevor Heck, Art Nuno. (Nicholas LoScalzo deferred — see `docs/future-ideas.md`.) Scott has already announced Ella to these channels.

### Deferrals worth knowing about

Documented in `docs/future-ideas.md` and `docs/followups.md` with explicit revisit triggers:

- Fathom realtime webhook smoke test (M4.1 restored the subscription via re-registration + secret rotation + redeploy; bad-signature 401 path verified. End-to-end smoke test against a real Fathom recording still pending — exercised passively whenever any team member records).
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

As of 2026-05-01 (M4 close-out):

- **Cloud Supabase** is the production target. Project ref `sjjovsjcfffrftnraocu` (region us-east-2, Ohio). **18 migrations applied** (`0001_core_entities` through `0018_client_history_rpcs`). 0017 added 14 columns to `clients` (country, birth_year, location, occupation, csm_standing, archetype, contracted_revenue, upfront_cash_collected, arrears, arrears_note, trustpilot_status, ghl_adoption, sales_group_candidate, dfy_setting), 1 column to `nps_submissions` (`recorded_by`), and 4 new tables: `client_upsells` (cascade-delete), `client_status_history` / `client_journey_stage_history` / `client_standing_history` (no-cascade, append-only). 0018 added 4 `security definer` Postgres functions for atomic update + history-row writes (`update_client_status_with_history`, `update_client_journey_stage_with_history`, `update_client_csm_standing_with_history`, `insert_nps_submission`). Both applied via Studio + manual ledger registration + dual-verified. Accessed via the pooler URL stored in `supabase/.temp/pooler-url`; the DB password lives in `.env.local` as `SUPABASE_DB_PASSWORD` (quoted because it contains a `#`).
- **Local Supabase** (Docker stack at `127.0.0.1:54321`, Postgres on `:54322`) is a dev-only mirror — useful for harness runs and inspection. Not consulted by any deployed component. `.env.local`'s `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` carry cloud values; local connections require explicit `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
- **Vercel deployment** live at `https://ai-enablement-sigma.vercel.app`. Single project, mixed-framework: Next.js 14 dashboard at repo root + **five** Python serverless functions in `api/`. `vercel.json` declares `"framework": "nextjs"` (required — explicit `functions` block suppresses Vercel's framework auto-detection without it) plus per-file Python runtimes: `api/slack_events.py` (Ella's Slack handler, `maxDuration: 60`), `api/fathom_events.py` (Fathom webhook, `maxDuration: 60`), `api/fathom_backfill.py` (daily cron, `maxDuration: 300`), `api/gregory_brain_cron.py` (weekly cron, `maxDuration: 300`), `api/airtable_nps_webhook.py` (Airtable NPS receiver, `maxDuration: 60` — added M5.4 Path 1). Vercel Cron schedules: `0 8 * * *` (daily 08:00 UTC) → `/api/fathom_backfill`; `0 9 * * 1` (weekly Mondays 09:00 UTC) → `/api/gregory_brain_cron`. Env vars in production: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_USER_TOKEN`, `FATHOM_WEBHOOK_SECRET`, `FATHOM_API_KEY`, `FATHOM_BACKFILL_AUTH_TOKEN`, `CRON_SECRET`, `GREGORY_BRAIN_CRON_AUTH_TOKEN`, `AIRTABLE_NPS_WEBHOOK_SECRET` (M5.4 — must be set in Production scope before the receiver goes live, else every request returns 500). `GREGORY_CONCERNS_ENABLED` is intentionally unset — Gregory brain treats anything other than `true`/`1`/`yes` as off.
- **Gregory dashboard** live with the V1 client page schema (M4). Routes: `/login`, `/clients`, `/clients/[id]`, `/calls`, `/calls/[id]`. The client detail page is the v3 7-section layout (Identity & Contact / Lifecycle & Standing / Financials / Activity & Action Items / Profile & Background / Adoption & Programs / Notes) with full inline-edit. Status / journey_stage / csm_standing edits route through the migration-0018 RPC functions for atomic update + history-row writes; `clients.notes` and the simpler whitelisted columns route through `updateClientField`. NPS-entry inline form on Section 2 calls `insert_nps_submission`. Section 5 (Profile & Background) writes to `clients.metadata.profile.*` jsonb via read-modify-write that preserves alternate_emails / alternate_names. PrimaryCsmField keeps the dialog-confirm pattern. Auth via Supabase Auth (email/password, manually invited users) via the (authenticated) layout. Two Supabase clients by privilege: anon key + cookies for the auth gate, service role + `'server-only'` guard for data reads.
- **`clients` table population (post-M4 Chunk C apply):** **197 non-archived clients** (128 pre-M4 baseline + 69 auto-creates from the master sheet importer — 48 churn + 21 non-churn per Drake's amendment to the spec). 137 have `csm_standing` set; 173 have `contracted_revenue`; 115 have `trustpilot_status`. 24 `client_upsells` rows. `client_status_history` has 209 rows (128 migration-seed + 81 import-seed). `client_standing_history` has 137 rows (all import-seed; migration didn't seed it). Spot-check: Ashan Fernando matched, Mubeen Siddiqui auto-created paused with Lou-CSM, Andy V auto-created with placeholder email, Mark Dawson auto-created churned with Scott-CSM (incidental bug-fix from the importer's auto-create restructure). Importer is idempotent — re-runs produce 0 net writes. 7 placeholder emails + 4 Aleks-orphan clients tracked as cleanup followups.
- **Slack app:** configured, installed in `#ella-test-drakeonly` (Drake-only test, mapped to Javi Pena's `client_id` as a temporary fixture), `#ella-test`, and the 7 pilot client channels. Event Subscriptions enabled; `app_mention` subscribed; signing-secret-verified. Bot scopes + `chat:write` user scope (M1.4.1). The `@ella` Slack user account ran the install and produced the `xoxp-` user token in Vercel as `SLACK_USER_TOKEN`. Ella the user is currently invited to `#ella-test-drakeonly` only — pilot channels still pending (M1.4.5).
- **Ella:** agent code in `agents/ella/`. M1.3 mrkdwn formatter live; M1.4.3 user-token reply path live (no APP tag in `#ella-test-drakeonly`). Awaiting Nabeel's read; M1.4.5 pilot rollout gated on it. `agent_runs.duration_ms` still `NULL` for Ella's runs — deferred per `docs/followups.md`.
- **Fathom webhook handler (M4.1 closed):** `api/fathom_events.py` deployed and **realtime path live again**. M4.1 diagnosed the F2.5-era subscription was silent from inception (0 `fathom_webhook` rows ever, not just 7-day window — the OpenAPI-documented `GET /webhooks` endpoint never existed at Fathom, so the original runbook's diagnostic was based on a fabricated path). Re-registered fresh via `POST /external/v1/webhooks` (id `FTVBjD_JqTfjEzVA`), rotated `whsec_` secret into Vercel, redeployed, verified bad-signature → 401 path. Smoke-test still pending (real Fathom recording needed to confirm end-to-end delivery — flagged for tomorrow's CSM rollout window).
- **Fathom backfill cron:** `api/fathom_backfill.py` deployed. Daily 08:00 UTC. Backstop to the realtime webhook; reliable since M1.2.5.
- **Gregory brain (M3.4):** agent code in `agents/gregory/`. First all-active sweep produced 133 `client_health_scores` rows (tier distribution 93 green / 40 yellow / 0 red). **Concerns generation still gated** (`GREGORY_CONCERNS_ENABLED` env var unset). Weekly cron fires Mondays 09:00 UTC. Note: with M4 Chunk C's import landing 69 new clients (mostly churned), the next sweep will land more rows than 133. Whether it stays gated is an open call (was originally gated on summary backfill — that priority shifted post-Nabeel-vision).
- **Test suite:** 381 passing (344 prior + 37 M3.4 Gregory tests). M4 work shipped without new tests; UI-side validation came via tsc + ESLint + `next build` clean across B1/B2 and end-to-end DB smoke tests for the 0018 RPCs.

## Next Session Priorities

Pick these up in order. **Read this section first** when starting a new session — it's the single source of truth for where to start.

1. **Tomorrow morning: 11am EST CSM sync.** Roll out the call titling convention (`[Client]`, `[Discovery]`, `[Client x Prospect]`) per `docs/conventions/call_titling.md`. Onboard the CSM team to the new dashboard. No engineering work — Drake-led, but expect feedback from the team that turns into next-session priorities. The Fathom webhook smoke test (real recording → `webhook_deliveries.source='fathom_webhook'` row) is naturally exercised by the rollout if any team member records that day.

2. **Manual data cleanup post-import.** All tracked in `docs/followups.md` under "Master sheet importer — three carry-overs":
   - 21 non-churn auto-creates need cross-check against existing-cloud-data-in-other-forms (manual review when time permits — risk: any might already be in cloud under a different identity).
   - 4 Aleks-orphan clients (Colin Hill, Ming-Shih Wang, Jose Trejo, Alex Crosby) need primary_csm reassigned via the dashboard's Primary CSM dropdown.
   - 7 placeholder emails (`<slug>+import@placeholder.invalid`) need cleanup if real emails surface (6 churned + Andy V).
   ~30 min batch when convenient.

3. **`GREGORY_CONCERNS_ENABLED` flag flip.** Was originally gated on summary backfill (M4.2 in the SOD plan); deprioritized post-Nabeel-vision pivot. Now lower priority — CSM dashboard onboarding is the bigger immediate win. Concerns can flip whenever summary density grows organically or via a future targeted backfill. Architecture is fully built; activation is one env-var toggle.

4. **NPS / Airtable webhook integration.** Nabeel + Zain will provide an Airtable webhook for automatic NPS pipe-in. Schema is ready (`recorded_by` on `nps_submissions`, `insert_nps_submission` RPC); receiver work queued. Likely a small Vercel serverless function in `api/` that validates the Airtable payload and calls the RPC.

5. **Action item editing (HITL).** Section 4 action items are read-only in V1. Per Nabeel's transcript vision, the AI-draft → CSM-review → client-send flow is the highest-leverage CSM-facing feature. Real chunk of work — scope it carefully when picked up. Likely needs its own multi-chunk arc.

6. **List-page filters (deferred from M4).** Add `csm_standing`, `ghl_adoption`, `trustpilot_status` filters to the `/clients` list page. Mirrors the existing status / journey_stage filter pattern; mostly UI work since the columns are now populated.

7. **Repo cleanup pass (M4.5 stretch from earlier today).** Broader sweep beyond `scripts/`. Drake will scope when the slot opens. Per `docs/followups.md` § "Repo cleanup pass — broader sweep beyond `scripts/`".

8. **(deferred) Nabeel sync on two open decisions.** Carry-over from M3 — still active:
   - **M1.4.3 user-token reply read** — does the no-APP-tag path address the "looks unprofessional" feedback? Gates M1.4.5 pilot-channel rollout for Ella.
   - **`GREGORY_CONCERNS_ENABLED` greenlight on LLM spend** — see (3) above; tied to summary density rather than spend approval now.

9. **(deferred) Slack 90-day backfill to cloud, M2.5 Aman manual review, CSM Co-Pilot V1.** Unchanged from prior priorities lists.

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
