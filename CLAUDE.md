# CLAUDE.md

Primary context for any Claude Code instance working on this repo. Read this fully before making changes.

## Project Purpose

Internal AI enablement system for a coaching/consulting agency. Replaces and augments human work across customer success, sales, and operations. The consumer business runs on this system first; later, the same system will be deployed to other agencies as a productized consulting offering.

**Immediate focus:** M5 V1-adoption pivot. Gregory replaces the Financial Master Sheet so Scott will adopt it daily; Monday 2026-05-04 onboarding call is the transition. Ella V1 in pilot (live, awaiting Nabeel feedback before pilot rollout to remaining 6 channels) — unchanged since M4. See § Current Focus for the active work breakdown.

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
│   └── accountability_roster.py # Path 2 outbound roster GET endpoint (Make.com daily pull)
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

M5 mid-pivot — V1 adoption focus. Driving framing came from Scott's 1:1 on 2026-05-01: V1 = "match the Financial Master Sheet so Scott will adopt Gregory daily." Anything Scott doesn't adopt is V2 territory regardless of architectural cleanliness. M5.3 / M5.3b / M5.4 all shipped against this framing. Monday 2026-05-04 is Scott's onboarding call where he transitions off the master sheet onto Gregory; Drake's manual cleanup over the weekend (2026-05-03 / 04) brings every active client up to date so the dashboard is the source of truth from Monday onward.

**Today's session (2026-05-04) shipped:**
- M5.6 hotfix — three regressions surfaced by visual smoke. Bug 1 (status edit silent) + Bug 2 (csm_standing edit silent) shared one pre-existing root cause: a stale-closure bug in `EditableField`'s enum/three_state_bool `setTimeout(commit, 0)` onChange path that landed in M4 (commit `19f4e50`) and went untested via the dashboard end-to-end until the M5.6 visual smoke. Fix in `components/client-detail/editable-field.tsx`: `commit` now accepts an optional `draftOverride` and the select onChange passes `e.target.value` directly (no setTimeout). Affects every enum + three_state_bool field (status / csm_standing / trustpilot / ghl_adoption / sales_group_candidate / dfy_setting); single fix covers all. Bug 3 — `change_primary_csm` errored on swap-back-to-archived-CSM (A→B→A) due to the `client_team_assignments` UNIQUE constraint; migration 0023 replaces 0014's RPC with the `ON CONFLICT DO UPDATE` pattern (mirroring the M5.6 cascade trigger). Hotfix commits `8d27e1e` (migration 0023) → `c2d59f4` (EditableField fix) on origin/main. A11y gap on EditableField `<select>`/`<Input>` (missing id/name/htmlFor) noted during diagnosis, ruled out as cause of Bug 1, logged to followups for a focused refactor.
- M5.6 — DB-level status cascade. When `clients.status` moves to a negative value (ghost/paused/leave/churned), an in-transaction trigger flips `csm_standing → 'at_risk'`, `accountability_enabled → false`, `nps_enabled → false`, and reassigns `primary_csm` to the new **Scott Chasing** sentinel team_member (UUID `ccea0921-7fc1-4375-bcc7-1ab91733be73`). Trustpilot is explicitly NOT touched. Cascade is one-directional (off-only) — manual CSM overrides on the toggles are not sticky; a future negative status transition re-fires and flips them off again. Migration `0022_status_cascade.sql` adds the 2 client cols + `team_members.is_csm boolean`, the Scott Chasing sentinel, the BEFORE/AFTER triggers, and updates `update_client_status_with_history` to set a `SET LOCAL app.current_user_id` GUC the AFTER trigger reads for human attribution. Cascade-induced history rows carry the structured `note` format `cascade:status_to_<status>:by:<uuid_or_NULL>` (or `cascade:backfill:m5.6` for the data backfill). 82 negative-status clients backfilled — 65 got history rows, 17 are silent toggles (snapshot at `docs/data/m5_6_silent_toggle_backfill.md`, recovery query in `docs/followups.md`). `is_csm=true` set on the four real CSMs + Scott Chasing — Primary CSM dropdowns now show 5 options (Lou Perez / Nabeel Junaid / Nico Sandoval / Scott Chasing / Scott Wilson). Two new toggles in Section 6 (Adoption & Programs) with active+off amber warning hint when status=active AND toggle=false. SQL smoke verified the SECURITY DEFINER + SET LOCAL pattern works (probe A — RPC with GUC landed Lou's UUID; probe B — direct UPDATE in fresh transaction landed `:by:NULL`, no leak). Visual smoke pending push.

**Previous session (2026-05-03) shipped:**
- M5.3 — `clients.status` vocabulary expansion (`leave` added, first DB-level CHECK constraint) + default-hide UI on `/clients` list page
- M5.3b — `clients.trustpilot_status` vocabulary rename (`yes`/`no`/`ask`/`asked`, was `given`/`declined`/`not_asked`/`pending`)
- M5.4 schema — `clients.nps_standing` column + Gregory Bot sentinel team_member + `update_client_from_nps_segment` RPC
- M5.4 receiver — `api/airtable_nps_webhook.py` deployed + Airtable native automation enabled + 59-client backfill applied via `scripts/backfill_nps_from_airtable.py`
- M5.4 follow-up — `NpsStandingPill` in Section 2 replacing prior `Latest NPS` field; manual `lib/supabase/types.ts` edit (CLI regen broken in this environment, hand-edit logged as followup)
- M5.5 — comprehensive filter bar on `/clients` (shipped + pushed; visual smoke implicitly verified during M5.6 smoke 2026-05-04 — Drake exercised the Primary CSM dropdown + status filter while testing M5.6 fields). 9-dropdown row replaces the chip+single-CSM-dropdown layout: 5 active multi-selects (Status / Primary CSM / CSM Standing / NPS Standing / Trustpilot), 1 single-value toggle (Needs review), 3 disabled placeholders (Accountability / NPS toggle / Country) signaling next-slice work. New `lib/client-vocab.ts` vocab module + reusable `MultiSelectDropdown` primitive. URL state: comma-separated multi-values, OR-within / AND-across, status absent-vs-empty sentinel for default-trio pre-check. `primary_csm_id` URL param renamed to `primary_csm` (deliberate break of M3-walkthrough bookmarks; Monday is fresh-start onboarding). Smoke checkpoint passed (build clean, 7/7 SQL count probes sensible against cloud). Closes one M5.4 followup (NPS pill mapping share).

**Phase 0 foundation: complete.** All ingestion pipelines built and applied. Slack history (2,914 messages across 8 channels) exists on **local** only — cloud Slack ingestion deferred per `docs/future-ideas.md`. Shared utilities, validators, and HITL infrastructure in place.

**Phase 1: Ella V1 — live and operating, polish in progress.** Agent code in `agents/ella/`. Slack webhook live, smoke-tested, replying with native Slack mrkdwn (M1.3) and posting via `@ella` user token (M1.4.3) so replies render with no APP tag in `#ella-test-drakeonly`. Fathom backlog fully ingested; realtime webhook restored M4.1 (id `FTVBjD_JqTfjEzVA`) and naturally exercised by the 2026-05-01 CSM sync's recordings. **Phase 1 polish remaining:** awaiting Nabeel's read on whether M1.4.3's user-token-reply addresses his "looks unprofessional" feedback before pilot rollout to remaining 6 channels (M1.4.5).

**Phase 2: Gregory dashboard V1 — M5 V1 adoption pivot in progress.** M3 shipped the Clients pages (list + detail + inline-save + CSM-swap dialog), Calls pages (list + detail + edit-mode classification + `call_classification_history`), and the merge feature for auto-created clients. M4 added the V1 client page schema (7-section detail-page, inline-edit, history-writing RPCs, NPS-entry, master-sheet import — 197 active clients). M5 has been refining for adoption: status vocab + trustpilot vocab match Scott's master sheet (M5.3 + M5.3b); NPS Path 1 (Airtable → Gregory) is live (M5.4); NPS Standing surfaces in Section 2 (M5.4 follow-up); comprehensive 9-dropdown filter bar on `/clients` shipped 2026-05-03 (M5.5); DB-level status cascade + Scott Chasing sentinel + accountability/NPS toggles shipped 2026-05-04 with same-day hotfix for three regressions surfaced by visual smoke (M5.6 + hotfix). See `docs/agents/gregory.md` § Build log for the full timeline.

**Phase 2: Gregory brain V1.1 — V2 territory now.** Agent at `agents/gregory/` with deterministic signal computations + scoring rubric + Claude-driven concerns generation. First all-active sweep landed 133 `client_health_scores` rows (93 green / 40 yellow / 0 red); next sweep runs against 197 clients. **Concerns generation still gated** (`GREGORY_CONCERNS_ENABLED` env var unset). Weekly cron at `/api/gregory_brain_cron` (Mondays 09:00 UTC). Per the M5 V1-adoption pivot, the brain's summary-driven concerns work moved to V2 — sits on top of an adopted V1, not underneath an unadopted one. The health score indicator continues to render as-is in Section 2; flipping the concerns flag when summary density grows organically is a one-toggle action whenever V2 cycles begin.

**Phase 3 candidates (post-Monday onboarding, M5 backlog):** status cascade with Scott Chasing column + auto csm_standing transitions, trustpilot auto-correct on standing change (Scott's Loom 2), Path 2 outbound writeback architecture (pending Make.com walkthrough Monday with Zain), inactivity flag, Australia/US country tagging, CSM-edit lockdown (Scott's Loom 1). V2 territory: action item HITL (AI-draft → CSM-review → client-send), CSM Co-Pilot V1, classifier extensions for new title prefixes, Gregory concerns activation, NPS score piping (V1.5).

**Pilot clients for Ella V1 beta:** Fernando G, Javi Pena, Musa Elmaghrabi, Jenny Burnett, Dhamen Hothi, Trevor Heck, Art Nuno. (Nicholas LoScalzo deferred — see `docs/future-ideas.md`.) Scott has already announced Ella to these channels.

### Deferrals worth knowing about

Documented in `docs/future-ideas.md` and `docs/followups.md` with explicit revisit triggers:

- Path 2 outbound writeback architecture (Gregory → Airtable / future master-sheet replacement). Pending Make.com walkthrough with Zain Monday 2026-05-04.
- Cloud Slack ingestion (slack_messages cloud table empty; Gregory's Slack engagement signal intentionally absent in V1.1).
- Drive-sourced content ingestion (today's pipeline reads from `data/course_content/`; Drive API + version-awareness comes later).
- `team_members.slack_user_id` backfill sweep for unresolved Slack authors (~94 of 2,914 messages are `unknown`).
- Browser-direct RLS policies (V1 is service-role only).
- Atomic per-call ingest via Postgres RPC (V1 pipeline is non-atomic + idempotent on re-run).
- Ella V1.1 items: cool-down on correction, formal eval harness, per-channel `ella_enabled` gating, thumbs-up/down reactions, impersonation/replay mode, Nicholas LoScalzo onboarding.
- Gregory rubric polish: never-called clients land green via the "0 action items = clean docket" interpretation; followup logged with two resolution options.
- Surface `alternate_emails` / `alternate_names` on Clients detail page (M3.2 follow-up; merge data is correct, the dashboard just doesn't render it).
- `calls.summary` column unused (cron writes summaries to `documents` instead; either backfill or drop in a small migration).
- Email-mismatch cleanup queue from M5.4 NPS backfill (Jonathan Duran-Rojas + Luis Malo). Drake handling over the weekend.
- 4 manual-override-sticky NPS divergences (Tina Hussain / Jenny Burnett / Mary Kissiedu / Saavan Patel — all CSM-judged-harsher-than-NPS). Discussion item for Monday onboarding, not a code task.
- Master-sheet-seed treatment for csm_standing auto-derive eligibility — architectural question pending Monday onboarding decision (current behavior: master-sheet-seeded csm_standing rows have `changed_by=NULL` → ineligible for auto-derive forever).
- `lib/supabase/types.ts` manual edits required until Supabase CLI regen path is restored.
- Action item editing HITL (AI-draft → CSM-review → client-send, per Nabeel's transcript vision). V2 territory.
- Repo cleanup pass — broader sweep beyond `scripts/` (per existing followup).

## Live System State

As of 2026-05-04 (M5.6 status cascade + hotfix close-out — all shipped):

- **Cloud Supabase** is the production target. Project ref `sjjovsjcfffrftnraocu` (region us-east-2, Ohio). **23 migrations applied** (`0001_core_entities` through `0023_change_primary_csm_on_conflict`). 0017 added 14 columns to `clients` + 1 column to `nps_submissions` + 4 history/upsell tables (M4 Chunk A). 0018 added 4 `security definer` Postgres functions for atomic update + history-row writes (M4 Chunk B2). 0019 (`status_add_leave`) added the first DB-level CHECK on `clients.status` and expanded the vocabulary to include `leave`; replaced `update_client_status_with_history` to mirror the new allowlist (M5.3). 0020 (`trustpilot_rename_vocab`) renamed `clients.trustpilot_status` 1:1 to match Scott's master sheet (`given`→`yes`, `declined`→`no`, `not_asked`→`ask`, `pending`→`asked`) (M5.3b). 0021 (`nps_standing_and_gregory_bot`) added `clients.nps_standing` + Gregory Bot sentinel team_member (UUID `cfcea32a-062d-4269-ae0f-959adac8f597`) + `update_client_from_nps_segment` RPC for the Airtable Path 1 receiver (M5.4). 0022 (`status_cascade`) added `clients.accountability_enabled` + `clients.nps_enabled` + `team_members.is_csm` + Scott Chasing sentinel (UUID `ccea0921-7fc1-4375-bcc7-1ab91733be73`) + BEFORE/AFTER triggers on `clients` for the negative-status cascade + GUC-aware update of `update_client_status_with_history` for human attribution on cascade history rows (M5.6). 0023 (`change_primary_csm_on_conflict`) replaced the 0014 RPC with an `ON CONFLICT DO UPDATE` variant so dashboard-driven swap-back-to-archived-CSM (A → B → A) succeeds instead of erroring on the unique key — mirrors the M5.6 cascade trigger's pattern (M5.6 hotfix). All applied via Studio + manual ledger registration + dual-verified (0022/0023 applied via psycopg2 since psql isn't installed in this environment, but the dual-verify pattern held). Accessed via the pooler URL stored in `supabase/.temp/pooler-url`; the DB password lives in `.env.local` as `SUPABASE_DB_PASSWORD` (quoted because it contains a `#`).
- **Local Supabase** (Docker stack at `127.0.0.1:54321`, Postgres on `:54322`) is a dev-only mirror — useful for harness runs and inspection. Not consulted by any deployed component. `.env.local`'s `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` carry cloud values; local connections require explicit `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
- **Vercel deployment** live at `https://ai-enablement-sigma.vercel.app`. Single project, mixed-framework: Next.js 14 dashboard at repo root + **six** Python serverless functions in `api/`. `vercel.json` declares `"framework": "nextjs"` (required — explicit `functions` block suppresses Vercel's framework auto-detection without it) plus per-file Python runtimes: `api/slack_events.py` (Ella's Slack handler, `maxDuration: 60`), `api/fathom_events.py` (Fathom webhook, `maxDuration: 60`), `api/fathom_backfill.py` (daily cron, `maxDuration: 300`), `api/gregory_brain_cron.py` (weekly cron, `maxDuration: 300`), `api/airtable_nps_webhook.py` (Airtable NPS receiver, `maxDuration: 60` — added M5.4 Path 1), `api/accountability_roster.py` (Make.com Path 2 outbound roster GET, `maxDuration: 60` — added 2026-05-04). Vercel Cron schedules: `0 8 * * *` (daily 08:00 UTC) → `/api/fathom_backfill`; `0 9 * * 1` (weekly Mondays 09:00 UTC) → `/api/gregory_brain_cron`. Env vars in production: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_USER_TOKEN`, `FATHOM_WEBHOOK_SECRET`, `FATHOM_API_KEY`, `FATHOM_BACKFILL_AUTH_TOKEN`, `CRON_SECRET`, `GREGORY_BRAIN_CRON_AUTH_TOKEN`, `AIRTABLE_NPS_WEBHOOK_SECRET` (M5.4), `MAKE_OUTBOUND_ROSTER_SECRET` (Path 2 outbound, 2026-05-04). `GREGORY_CONCERNS_ENABLED` is intentionally unset — Gregory brain treats anything other than `true`/`1`/`yes` as off.
- **Gregory dashboard** live with the V1 client page schema (M4) + M5 vocab updates + M5.5 filter bar + M5.6 cascade toggles (shipped 2026-05-04, visual smoke passed same day after a hotfix for three regressions — see Build log). Routes: `/login`, `/clients`, `/clients/[id]`, `/calls`, `/calls/[id]`. The client detail page is the v3 7-section layout (Identity & Contact / Lifecycle & Standing / Financials / Activity & Action Items / Profile & Background / Adoption & Programs / Notes) with full inline-edit. Status / journey_stage / csm_standing edits route through the migration-0018 RPC functions for atomic update + history-row writes (status RPC was replaced in 0019 to include `leave` in the allowlist). Section 2 NPS Standing pill (M5.4) renders `clients.nps_standing` via `components/client-detail/nps-standing-pill.tsx` (replaced the M4 "Latest NPS" field which read `nps_submissions.score` — that field stays in the data layer for V1.5 score-piping but no UI surfaces it today). NpsEntryForm (manual NPS-score entry from a CSM) preserved below the pill — different data source. List page filter bar (M5.5) is a 9-dropdown row: 5 active multi-selects (Status / Primary CSM / CSM Standing / NPS Standing / Trustpilot), 1 single-value toggle (Needs review), 3 disabled placeholders (Accountability / NPS toggle / Country) signaling next-slice work. Status pre-checks `active+paused+ghost` via the absent-param sentinel (the prior M5.3 "Show churned & leave" toggle chip is gone — checking Churned/Leave in the Status dropdown now does that job). Vocab module at `lib/client-vocab.ts` is the single source of truth shared with the inline-edit dropdowns + the NpsStandingPill. Adoption section's trustpilot dropdown surfaces vocab `Yes` / `No` / `Ask` / `Asked` (M5.3b, options imported from vocab module post-M5.5). Auth via Supabase Auth (email/password, manually invited users) via the (authenticated) layout. Two Supabase clients by privilege: anon key + cookies for the auth gate, service role + `'server-only'` guard for data reads.
- **`clients` table population (post-M5.6 backfill):** **197 non-archived clients** (113 active + 27 paused + 3 ghost + 0 leave + 52 churned + 2 unaccounted-for-since-M5.5-probe). Post-M5.6: every negative-status client (82 total) has `csm_standing='at_risk'` + `accountability_enabled=false` + `nps_enabled=false`; every active client (113) has the toggles at default `true`. `csm_standing` distribution shifted (41 happy / 61 content / 33+82=115 at_risk / 4 problem) due to the M5.6 backfill flipping all 82 negative-status clients to `at_risk` regardless of prior state. 173 have `contracted_revenue`; 115 have `trustpilot_status` (21 yes / 69 no / 21 ask / 4 asked — values renamed in 0020, distribution unchanged; M5.6 explicitly does not touch trustpilot). 24 `client_upsells` rows. **`clients.nps_standing` populated for 59 active clients** (10 at_risk / 22 neutral / 27 promoter; 138 NULL — clients without an Airtable NPS Survery submission). `client_status_history` has 209 rows (unchanged in M5.6 — cascade writes to standing history, not status history). `client_standing_history` grew from 139 → 204+ rows in M5.6: 65 `cascade:backfill:m5.6` rows from the migration data backfill (Gregory Bot attributed) + 3 cascade-fired rows from the SQL smoke probes on Allison Jayme Boeshans + Amaan Mehmood (history is immutable so the smoke rows persist; they're labeled with smoke timestamps and `cascade:status_to_paused:by:<lou-uuid>`, `cascade:status_to_paused:by:NULL`, `cascade:status_to_ghost:by:NULL` per the structured note format). 17 silent-toggle clients (negative status + already-at_risk) flipped without history rows; snapshot at `docs/data/m5_6_silent_toggle_backfill.md`, recovery query in `docs/followups.md`. 7 placeholder emails + 4 Aleks-orphan clients tracked as cleanup followups. 2 emails in cleanup queue from M5.4 backfill 404s (Jonathan Duran-Rojas + Luis Malo). 32 currently-CSM-owned negative-status clients (Lou 18 / Scott Wilson 13 / Nabeel 1) keep their assignments — primary_csm reassignment intentionally skipped for the M5.6 backfill; cascade only auto-reassigns going forward on new negative-status transitions.
- **Slack app:** configured, installed in `#ella-test-drakeonly` (Drake-only test, mapped to Javi Pena's `client_id` as a temporary fixture), `#ella-test`, and the 7 pilot client channels. Event Subscriptions enabled; `app_mention` subscribed; signing-secret-verified. Bot scopes + `chat:write` user scope (M1.4.1). The `@ella` Slack user account ran the install and produced the `xoxp-` user token in Vercel as `SLACK_USER_TOKEN`. Ella the user is currently invited to `#ella-test-drakeonly` only — pilot channels still pending (M1.4.5).
- **Ella:** agent code in `agents/ella/`. M1.3 mrkdwn formatter live; M1.4.3 user-token reply path live (no APP tag in `#ella-test-drakeonly`). Awaiting Nabeel's read; M1.4.5 pilot rollout gated on it. `agent_runs.duration_ms` still `NULL` for Ella's runs — deferred per `docs/followups.md`.
- **Fathom webhook handler (M4.1 closed):** `api/fathom_events.py` deployed and **realtime path live**. M4.1 re-registered fresh via `POST /external/v1/webhooks` (id `FTVBjD_JqTfjEzVA`), rotated `whsec_` secret into Vercel, redeployed, verified bad-signature → 401 path. End-to-end smoke test naturally exercised by the 2026-05-01 CSM sync's recordings.
- **Fathom backfill cron:** `api/fathom_backfill.py` deployed. Daily 08:00 UTC. Backstop to the realtime webhook; reliable since M1.2.5.
- **Airtable NPS webhook receiver (M5.4 Path 1):** `api/airtable_nps_webhook.py` deployed. Auth via `X-Webhook-Secret` header (`AIRTABLE_NPS_WEBHOOK_SECRET` env var, `hmac.compare_digest`). Calls `update_client_from_nps_segment(email, segment)` after normalizing Airtable's raw segment string (`Strong / Promoter` / `Neutral` / `At Risk`) to lowercase. Override-sticky csm_standing semantics enforced inside the RPC: auto-derive only when current `csm_standing` is null OR the most recent `client_standing_history.changed_by = Gregory Bot UUID`. Make.com automation enabled in Airtable (Survey Date or Segment Classification field changes auto-fire the webhook). Historical 79-row Survery table backfilled via `scripts/backfill_nps_from_airtable.py` on 2026-05-03 — 61 deduped clients, 59 success, 2 404 (email mismatch, in cleanup queue). 8-path local test harness at `scripts/test_airtable_nps_webhook_locally.py`.
- **Accountability + NPS daily roster (Path 2 outbound, 2026-05-04):** `api/accountability_roster.py` deployed. GET endpoint Make.com pulls daily, replacing the Financial Master Sheet as the source of truth for Zain's existing accountability + NPS automation. Auth via `X-Webhook-Secret` header (`MAKE_OUTBOUND_ROSTER_SECRET` env var, `hmac.compare_digest`). Returns `{generated_at, count, clients[]}` where each client carries `client_email`, `slack_user_id`, `slack_channel_id`, `accountability_enabled`, `nps_enabled`. Single-query embedded join on `slack_channels`; per-client filter mirrors `getClientById`'s slack_channel selection (most recently created non-archived). Server-side filter excludes NULL slack_user_id, missing channel, or NULL email so every row in the response is actionable. Live count at deploy: **100 actionable clients out of 195 non-archived** (95 filtered — surfaces a client→Slack-identity coverage gap worth a sweep). 7-path local test harness at `scripts/test_accountability_roster_locally.py` (22/22 green at deploy time). No status filter — Make.com filters on the booleans on its side.
- **Gregory brain (M3.4):** agent code in `agents/gregory/`. First all-active sweep produced 133 `client_health_scores` rows (tier distribution 93 green / 40 yellow / 0 red). **Concerns generation still gated** (`GREGORY_CONCERNS_ENABLED` env var unset; the activation moved to V2 territory per the M5 V1-adoption pivot — sits on top of adopted V1). Next weekly cron sweep (Mondays 09:00 UTC) will run across 197 active clients (was 132 at first sweep).
- **Test suite:** 381 passing. M5 work shipped without new tests; UI-side validation came via tsc + ESLint + `next build` clean, end-to-end DB smoke tests for the new RPCs against cloud, and Python harness runs for the Airtable receiver.

## Next Session Priorities

Pick these up in order. **Read this section first** when starting a new session — it's the single source of truth for where to start.

**M5.5 + M5.6 + Path 2 outbound closed.** M5.5 (filter bar — shipped 2026-05-03). M5.6 (status cascade + Scott Chasing + accountability/NPS toggles + same-day hotfix — shipped 2026-05-04). Path 2 outbound roster (`api/accountability_roster.py` — daily-pull GET endpoint Make.com hits, replacing the Financial Master Sheet — shipped 2026-05-04). Path 2's framing was reshaped by the Make.com walkthrough with Zain: it's a daily-pull GET, not the event-driven UPDATE listener previously sketched; Zain's Make.com scenario already runs on a daily-pull cadence so the simpler shape was the cleaner contract. See `docs/agents/gregory.md` § Build log for full close-outs.

1. **Trustpilot auto-correct on standing change + Country promotion to client page (in one chunk).** Trustpilot auto-correct (Scott's Loom 2) sits on top of the M5.6 cascade infrastructure — same trigger pattern, different rule (`csm_standing` → certain transitions auto-flip `trustpilot_status` to a corresponding state). Country is currently a tag on `clients.metadata.country` (USA/AUS); promote to a real column on `clients` with display + filter surfaces, which retires the disabled "Country" placeholder dropdown from M5.5. Bundled into one chunk because both touch the client-page schema and the M5.5 filter bar.

2. **May meetings tracker + inactivity flag (in one chunk).** Both are aggregations on existing call data. Inactivity flag = end-of-week-2 monthly meeting count (Scott's Loom 2 framing); May meetings tracker = related view of who's met who in the current month. Bundled because the underlying call-aggregation queries are the same shape.

3. **Manual cleanup pass.** Drake's full client-data cleanup walkthrough — happens after all Scott features ship so cleanup happens against a stable feature set. Includes the M4 Chunk C carry-overs (21 non-churn auto-creates cross-check, 4 Aleks-orphan reassignments, 7 placeholder emails), the 32 currently-CSM-owned negative-status clients from M5.6 (Lou 18 / Scott Wilson 13 / Nabeel 1 — Drake decides whether to reassign to Scott Chasing), email-mismatch cleanup from M5.4 NPS backfill (Jonathan Duran-Rojas + Luis Malo), and the client→Slack-identity coverage gap surfaced by Path 2's deploy (95 of 195 non-archived clients filtered out — NULL `slack_user_id` or no resolvable `slack_channels` row). Note: today's session (2026-05-04) tracker P2 is also a cleanup pass; if today's run covers the listed scope this priority is done before tomorrow.

**Below the four (deferred until adoption stabilizes):** CSM-edit lockdown (Scott's Loom 1), email-mismatch cleanup from M5.4 backfill (Jonathan Duran-Rojas + Luis Malo), NPS score piping (V1.5), V2 territory (action item HITL, CSM Co-Pilot V1, classifier extensions, Gregory concerns activation).

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
