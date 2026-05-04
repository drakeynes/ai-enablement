# Gregory — CSM Co-Pilot

## What Gregory is

A web dashboard hosted on Vercel that gives CSMs (and admins) clear, low-friction visibility into their book of business. Each client gets a profile with status, recent activity, action items, and a Gregory-computed health score with concerns.

Gregory has two halves:

1. **The dashboard surface** (V1) — Next.js app at `/dashboard` that reads from and writes to Supabase. Two pages: Clients and Calls.
2. **The brain** (V1.1, deferred) — Python agent that reads call summaries, action items, NPS, and Slack signals to compute health scores + concerns, writes to `client_health_scores`.

V1 ships the surface with real data where it exists today (call cadence, action items) and clear empty states for what Gregory's brain will fill in later (health score, concerns, NPS once ingested).

## Why a dashboard, not a Slack agent

Gregory's job is *visibility into a portfolio of clients*. Slack is a conversational surface — good for ad-hoc questions ("what's the latest with Javi?"), bad for scanning 30 clients to spot the one that needs attention this week. The CSM workflow Gregory supports is "open the dashboard, scan the list, click into the worrying ones" — that's a UI workflow, not a chat workflow.

Ella (client-facing) lives in Slack because clients live in Slack. Gregory (CSM-facing) lives on the web because CSMs need a portfolio view.

## Surface

### Auth

Supabase Auth with email/password. Team members manually invited via Supabase Studio for V1 (CSM rollout in V2 once permissions are scoped). No magic-link or SSO in V1.

`auth.users.id` joins to `team_members` via email match. RLS off for V1 (app-level auth gate is sufficient for the small internal user base); RLS on for V2 when CSMs get access and we need per-CSM scoping.

### Navigation

Top nav only. Two items: **Clients** | **Calls**. User avatar + logout on the right. No sidebar (premature for 2 pages).

### Routes

- `/login` — auth landing
- `/clients` — list view, default landing after login
- `/clients/[id]` — detail view
- `/calls` — list view
- `/calls/[id]` — detail view
- `/settings` — placeholder for V1 (auth profile)

## Brain V1.1

The "brain" is the agent that computes per-client health scores and writes them to `client_health_scores`. Lives at `agents/gregory/`. Mirrors Ella's layout: `agent.py` (entry), `signals.py` (deterministic signal computations), `scoring.py` (rubric → score + tier), `concerns.py` (Claude-driven qualitative watchpoints), `prompts.py` (concerns prompt). Each invocation opens an `agent_runs` row, runs, writes one `client_health_scores` row per client, closes the run with telemetry.

### Signals (V1.1)

Four deterministic signals, each emitting a `Signal` dict written verbatim into `factors.signals[]`:

| Signal | Source | Bands / scale | Weight | Missing-data behavior |
|---|---|---|---|---|
| `call_cadence` | days since most recent `calls.started_at` where `primary_client_id = client` | <14d → 100; 14-30d → 50; >30d → 0 | 0.40 | "no calls" → neutral 50, note explains |
| `open_action_items` | count of `call_action_items` where `owner_client_id=client AND status='open'` | 100 baseline, −5 per item, floor 0 | 0.20 | 0 items → 100 (clean docket; not "missing") |
| `overdue_action_items` | as above, plus `due_date < today` | 100 baseline, −15 per item, floor 0 | 0.20 | 0 items → 100 |
| `latest_nps` | most recent `nps_submissions.score` for the client | raw 0-10 scaled to 0-100 | 0.20 | "no NPS" → neutral 50 (V1.1 reality: nps_submissions is empty) |

**Slack engagement** is intentionally absent in V1.1 — `slack_messages` cloud table is empty (local-only ingestion per `docs/future-ideas.md`). Add it as a fifth signal once cloud Slack ingestion lands; re-balance weights at that time.

### Scoring rubric

```
final_score = sum(signal.weight * signal.contribution) / sum(weights)
            clamped to 0-100, rounded to int.

tier:  >=70 → green
       40-69 → yellow
       <40  → red
```

**Insufficient-data default.** When every signal returned the neutral contribution (i.e. nothing is known about the client), the brain ships `score=50, tier=yellow, factors.overall_reasoning='Insufficient signal data; defaulting to yellow.'`. Never green by accident on no data.

Thresholds and band cutoffs are V1.1 starting points. The math is fully transparent in `factors.signals[]` — a reviewer reading the dashboard's "Why this score" expand can recompute the score by hand. Iterate as miscalibration surfaces.

### Concerns generation (gated)

Concerns are Claude-driven qualitative watchpoints — short text + severity (low/medium/high) + `source_call_ids[]`. Lands in `factors.concerns[]`, which the dashboard's `ConcernsIndicator` reads and renders.

The Claude call is gated behind the `GREGORY_CONCERNS_ENABLED` env var (deploy-flippable, no commit needed). **Default OFF for V1.1.0.** Reasoning: the input to the concerns prompt is recent `call_summary` documents — and at the time of M3.4 ship, there are ~22 such documents across 132 active clients. Roughly 85% of clients would have empty input; paying for the LLM call to hand Claude nothing is wasteful. The flag flips to `true` in Vercel env vars once summary coverage densifies (Fathom webhook + cron continue ingesting; this should resolve organically over weeks).

When the flag is on but a particular client has no summaries AND no open action items, the brain still skips the Claude call — same "don't burn tokens for empty input" stance, applied per-client.

Sonnet by default (`shared.claude_client.DEFAULT_MODEL`). Swap to Opus by passing `model='claude-opus-4-7'` if review shows shallow reasoning.

### Cron schedule

Weekly, Mondays 09:00 UTC, via `vercel.json` cron declaration → `api/gregory_brain_cron.py` → `compute_health_for_all_active()`. Reasoning for weekly (not daily): signal change rate is slow (call cadence moves day-to-day for ~5 clients; action-item churn is gradual), and at scale the LLM cost compounds. Re-eval cadence once dashboard usage tells us something. Manual sweeps via `scripts/run_gregory_brain.py --all` between cron runs are fine.

The cron lands an hour after the daily Fathom backfill (08:00 UTC) so any calls / action items ingested overnight are visible to the brain.

### Public entry points

- `compute_health_for_client(client_id)` — single client. Used by `scripts/run_gregory_brain.py` and tests.
- `compute_health_for_all_active()` — sweep every active client. Per-client failures isolated; one bad client doesn't halt the sweep. Each per-client run gets its own `agent_runs` row (clean per-client cost / duration accounting).

### Operational notes

- **No locking.** Concurrent runs (cron + manual overlap) write duplicate rows per client. Dashboard reads "latest per client", so dups are noise not corruption.
- **History preserved by design.** `client_health_scores` is append-only; every run produces one row per client. Reviewing trend over time is just `select score, tier, computed_at from client_health_scores where client_id=? order by computed_at desc`.
- **Traceability.** `client_health_scores.computed_by_run_id` FK → `agent_runs.id`. Every score row points back to the run that produced it; cost / duration / errors live there.

## Pages

### Clients page — list view

Sortable table, one row per client. Default sort: by health score ascending (worst first) once Gregory exists; by `last_call_date` descending for V1.

Columns:

| Column | Source | Notes |
|--------|--------|-------|
| Full name | `clients.full_name` | Click → detail view |
| Status | `clients.status` | Color pill (active / paused / ghost / leave / churned). List page default-hides `churned` + `leave`; "Show churned & leave" toggle chip reveals them. Explicit status filter (e.g. `?status=churned`) wins over the default-hide. |
| Journey stage | `clients.journey_stage` | onboarding / active / churning / churned / alumni |
| Primary CSM | `client_team_assignments` where role='primary_csm' | Latest active assignment |
| Health score | `client_health_scores` (latest) | Numeric + tier pill; empty for V1 |
| Last call | `max(calls.started_at)` where `primary_client_id = client.id` | Days-ago format with color coding |
| Open action items | count of `call_action_items` where `owner_client_id = client.id` and `status='open'` | "3 open (1 overdue)" if any past due_date |
| Tags | `clients.tags` | Chip display |

Search: filter on name + email. Filter chips: status, journey stage, primary CSM, "has open action items".

### Clients page — detail view

Vertical layout, 7 collapsible sections (default expanded) via native `<details>`/`<summary>`. The structure changed in M4 Chunk B (post-migration 0017) — what was a 6-implicit-section layout reorganized into 7 explicit sections that surface the new schema (14 columns + nps_submissions.recorded_by + 4 new tables). M4 Chunk B2 wires inline-save on every editable field: click swaps the read-only display into an input/select/textarea, blur or Enter saves, Escape cancels. Status / journey_stage / csm_standing route through history-writing RPCs (migration 0018) so every edit leaves an audit row in the corresponding `*_history` table. metadata.profile.* fields go through a read-modify-write on `clients.metadata`. The needs_review tag triggers a Merge button at the top of the page (orthogonal to the sections, preserved from M3.2).

**Section 1 — Identity & Contact:** Identity- and contact-level fields, mostly editable in B2. `clients.full_name`, primary `clients.email`, alternate emails (from `clients.metadata.alternate_emails`), phone, country (new), time zone, birth year (new — rendered as "Born YYYY"), location/city (new), occupation (new), status, primary CSM (active assignment from `client_team_assignments`), and tags. Three sub-fields are truly read-only (no edit affordance): Slack channel id (joined from `slack_channels` filtered to active, most recent by `created_at`), Slack user id (`clients.slack_user_id`), signup date (`clients.start_date`).

**Section 2 — Lifecycle & Standing:** CSM-judgment fields plus system-derived signals. Editable-in-B2: journey_stage (with note "Stage taxonomy in design — free-text for now"), csm_standing (enum: happy/content/at_risk/problem — new), latest NPS score (read from most recent `nps_submissions.score`), archetype (new — free-text V1, enum once Drake/Nabeel finalize). System-derived: Health score from latest `client_health_scores` row (preserved indicator with tier pill, "why this score" expand of the factors jsonb), and Concerns as a collapsible sub-section under Health score that distinguishes three empty states: "Gregory has not yet evaluated this client" when no health row exists, "No concerns currently surfaced" when a health row exists but `factors.concerns[]` is empty, and the existing list rendering (text + severity pill + linked source calls) when concerns are present.

**Section 3 — Financials:** Editable in B2: contracted_revenue (numeric, dollars), upfront_cash_collected, arrears (note: column has `not null default 0`, so existing clients render `$0.00` — distinguishing "0 because we set it" from "0 because we never imported a value" is not a V1 concern), arrears_note.

**Section 4 — Activity & Action Items:** System-derived activity counts (total calls, total Slack messages, total NPS submissions) rendered as stat blocks alongside two pipeline-pending placeholders (total accountability submissions, course content consumption). Recent calls list shows top 5 with a "Show all calls" expansion that reveals the rest from the same query (no extra round trip). Action items sub-section shows ALL action items grouped by status (open → done → cancelled), collapsing the tail behind a "Show N older action items" toggle when total > 10. Replaces what M2.3b shipped as the open-only Section 6.

**Section 5 — Profile & Background:** All five fields live in `clients.metadata.profile` (jsonb sub-object), NOT as columns on `clients` — the schema spec deliberately keeps these in jsonb until query patterns justify promotion. Editable in B2: niche, offer, traffic_strategy, and SWOT split into 4 sub-fields (strengths, weaknesses, opportunities, threats). Empty by default.

**Section 6 — Adoption & Programs:** Editable in B2: trustpilot_status (enum: yes/no/ask/asked — vocab matches Scott's master sheet, renamed in 0020 from not_asked/pending/given/declined), ghl_adoption (enum: never_adopted/affiliate/saas/inactive — new), sales_group_candidate (boolean three-state: yes/no/not assessed — new), dfy_setting (boolean three-state — new). Plus an Upsells sub-section listing rows from the new `client_upsells` table (sorted sold_at desc nulls last) — amount, product, sold_at, notes per row.

**Section 7 — Notes:** Editable in B2: single text area rendering `clients.notes` (column added in 0012). Empty state shows "No notes yet — click to add" with a dashed-border affordance. Markdown rendering deferred to V1.1 polish.

### Calls page — list view

Sortable table, one row per call. Default sort: `started_at` descending. Secondary "Needs review" toggle re-sorts by `classification_confidence` ascending.

Columns:

| Column | Source | Notes |
|--------|--------|-------|
| Date | `calls.started_at` | |
| Title | `calls.title` | Click → detail view |
| Category | `calls.call_category` | Color pill (client/internal/external/unclassified/excluded) |
| Primary client | join via `primary_client_id` | "—" if null |
| Participants | `call_participants` | "Alice + 3 others" format |
| Duration | `calls.duration_seconds` | mm:ss formatted |
| Confidence | `calls.classification_confidence` | 0-1, color-coded; surfaces low-confidence |
| Retrievable | `calls.is_retrievable_by_client_agents` | Icon |

Search: participant name/email + call title.

Filter chips: by category, by client, **by "Needs review"** (low confidence OR unclassified OR primary_client_id is null when category=client). The "Needs review" filter is the Aman-classification and F1.5-bug review queue.

### Calls page — detail view

**Edit mode + explicit Save/Cancel** for this page. Higher-stakes edits (category and primary_client_id directly affect Ella retrieval).

**Section 1 — Metadata (read-only):** title, started_at, duration, source, external_id, ingested_at, recording_url (link).

**Section 2 — Classification (editable):** category (dropdown), call_type (dropdown), primary_client (searchable dropdown of clients, required when category=client), confidence (read-only, original auto value), method (read-only, auto-set to 'manual' on save), is_retrievable_by_client_agents (read-only, auto-derived from category + primary_client_id presence).

On save, an entry is written to `call_classification_history` (migration 0013) capturing what changed, who changed it, when.

**Section 3 — Participants (read-only):** Table of name/email/role/matched_client/matched_team_member. Unmatched participants flagged visually.

**Section 4 — Summary (read-only):** `calls.summary` if present, otherwise empty state: "No summary — Fathom .txt exports don't carry summaries. Cron-ingested calls have summaries."

**Section 5 — Action items (read-only for V1):** List from `call_action_items` for this call.

**Section 6 — Transcript (collapsed by default):** Toggle to expand, read-only scrollable.

## Schema changes

Two new migrations. Both lightweight, neither destructive.

### `0012_clients_notes.sql`

Adds a single nullable `notes` text column to `clients`. Edited inline by team members on the client detail page.

### `0013_call_classification_history.sql`

New append-only audit table for manual edits to `call_category`, `call_type`, and `primary_client_id` from the Calls detail page. Constrained `field_name` enum to those three fields. Application-side writes (not trigger-based) so the audit logic stays visible in dashboard code rather than hidden in a trigger.

## Airtable NPS integration (V1 — M5.4)

Airtable is the source of truth for NPS Survey segments. Gregory mirrors each client's segment classification into `clients.nps_standing` and conditionally auto-derives `clients.csm_standing` from it.

**Architecture — three layers, one direction:**

1. **Airtable Survey** (external) — captures NPS scores + classifies clients into segments. Fires a webhook into the Vercel receiver on segment change. Source of truth for the segment classification.
2. **Receiver** (`api/airtable_nps.py`, next chunk) — small Vercel serverless function. Validates the webhook payload, normalizes Airtable's raw segment strings to lowercase (`"Strong / Promoter"` → `promoter`, `"Neutral"` → `neutral`, `"At Risk"` → `at_risk`), then calls the combined RPC. No business logic at this layer; it's a thin adapter.
3. **`update_client_from_nps_segment` RPC** (migration 0021) — does the work in one transaction. Always writes `clients.nps_standing`. Conditionally auto-derives `clients.csm_standing` per override-sticky semantics.

**Override-sticky semantics (Scott-confirmed behavior B — manual CSM judgment wins):**

The auto-derive only writes `csm_standing` when EITHER:
- `clients.csm_standing IS NULL` (no prior value), OR
- the most recent `client_standing_history` row for the client has `changed_by = Gregory Bot UUID` (`cfcea32a-062d-4269-ae0f-959adac8f597`).

If neither holds — i.e., a CSM has manually set `csm_standing` via the dashboard — the RPC skips the auto-derive and only writes `nps_standing`. The manual judgment is sticky until a CSM clears it (back to null) or until Gregory Bot is the most recent author again. The `Gregory Bot` `team_members` row (added in 0021, role `system_bot`) exists solely to make this manual-vs-auto distinction queryable from the existing `client_standing_history.changed_by` column — no separate `is_automated` flag needed.

**Segment → csm_standing mapping** (encoded only inside the RPC; receiver passes the segment, DB does the work):

| `nps_standing` | derived `csm_standing` |
|---|---|
| `promoter` | `happy` |
| `neutral` | `content` |
| `at_risk` | `at_risk` |

`'problem'` `csm_standing` has no auto-derive path — only manual CSM judgment. The function never writes `csm_standing = 'problem'`.

**Why the auto-derive delegates rather than writing directly:** the RPC `PERFORM update_client_csm_standing_with_history(...)` rather than UPDATE'ing `clients.csm_standing` directly. Reusing the 0018 RPC keeps the audit logic + idempotency (no-op when value unchanged → no history row written) in one place. The Gregory Bot UUID is passed as `p_changed_by` and `'auto-derived from NPS segment <segment>'` as `p_note` so the history row carries enough context to reconstruct what happened.

### Receiver implementation (M5.4)

Endpoint: `POST https://ai-enablement-sigma.vercel.app/api/airtable_nps_webhook`. Source code: `api/airtable_nps_webhook.py`. Friendly `GET` returns 200 with `{"status": "ok", "endpoint": "airtable_nps_webhook", "accepts": "POST"}` for browser/uptime probes.

**Auth.** `X-Webhook-Secret` HTTP header. Server compares against `AIRTABLE_NPS_WEBHOOK_SECRET` env var via `hmac.compare_digest` (constant-time). Missing or mismatched → 401 with `{"error": "unauthorized"}`, no DB write. Missing env var (deployment misconfiguration) → 500 with `{"error": "misconfigured"}`. Note: this is shared-secret auth, NOT HMAC signature like Fathom — Make.com supports custom headers cleanly, signature-based auth would require Make-side computation.

**Payload shape (Make.com → receiver):**

```json
{
  "client_email": "ada@example.com",
  "segment": "Strong / Promoter",
  "airtable_record_id": "recXyz123",
  "submitted_at": "2026-05-01T15:30:00Z"
}
```

`client_email` and `segment` are required. `airtable_record_id` is optional but persisted on `webhook_deliveries.call_external_id` for forensics + queryability via the existing `(source, call_external_id)` partial index. `submitted_at` is captured in the `payload` jsonb but not used in the V1 logic.

**Segment normalization at the receiver boundary** (case-insensitive, whitespace-stripped):

| Airtable raw | Normalized |
|---|---|
| `Strong / Promoter` | `promoter` |
| `Neutral` | `neutral` |
| `At Risk` | `at_risk` |

Unrecognized → 400 with `{"error": "invalid_segment", "accepted": ["Strong / Promoter", "Neutral", "At Risk"]}`. The accepted list shows canonical Airtable forms (not the lowercased internal lookup keys) so Make.com configurators see the strings to send.

**Response shapes:**

| Status | Body | When |
|---|---|---|
| 200 | `{"status": "ok", "delivery_id": "airtable_nps_<uuid>", "client_id": "<uuid>", "nps_standing": "<seg>", "csm_standing": "<value\|null>", "auto_derive_applied": true\|false}` | RPC succeeded |
| 400 | `{"error": "invalid_json"}` | body not parseable JSON |
| 400 | `{"error": "missing_field", "detail": "<which>"}` | required field missing or empty |
| 400 | `{"error": "wrong_type", "detail": "<which> must be a string..."}` | type mismatch |
| 400 | `{"error": "invalid_segment", "detail": "...", "accepted": [...]}` | segment value not in the three known forms |
| 401 | `{"error": "unauthorized"}` | missing or wrong `X-Webhook-Secret` |
| 404 | `{"error": "client_not_found", "email": "<input>"}` | RPC raised "no active client matches email" — primary `clients.email` and `metadata.alternate_emails` both missed |
| 500 | `{"error": "misconfigured"}` | `AIRTABLE_NPS_WEBHOOK_SECRET` env var unset |
| 500 | `{"error": "rpc_failed"}` | any other RPC exception |
| 500 | `{"error": "internal_error"}` | unhandled exception in handler |

`auto_derive_applied` is a best-effort inference: post-RPC `csm_standing` matches what the segment-mapping would produce. Intentionally NOT a precise "we just wrote it" signal — the RPC's idempotency + the override-sticky branch means the value can match without a write happening this call. The boolean answers "value matches the mapping," not "the auto-derive ran." Source of truth for actual writes is `client_standing_history.changed_by` — a Gregory Bot UUID on the most recent row means the auto-derive ran.

**Audit trail.** Every request that passes auth lands a `webhook_deliveries` row with `source='airtable_nps_webhook'`. Status transitions: `received` (initial insert) → `processed` (RPC success) | `failed` (404/500) | `malformed` (400). Auth failures (401) write NO row — same gate-before-DB pattern as the Fathom webhook handler. The `webhook_id` PK is `airtable_nps_<uuid4>` per request (no native idempotency token from Airtable; UUID-per-request gives every delivery a unique row, which matches the V1 "no idempotency layer" decision).

**Local test harness:** `scripts/test_airtable_nps_webhook_locally.py` spins up the real `handler` class via `http.server.HTTPServer` in a background thread (same pattern Vercel uses), fires 8 paths (2 happy + 6 negative), verifies HTTP responses + cloud DB state via direct psycopg2, cleans up the test client (Branden Bledsoe — selected as a low-profile active client with null csm_standing and no history rows pre-test) in try/finally. Run via `.venv/bin/python scripts/test_airtable_nps_webhook_locally.py`. Sets a test secret if `AIRTABLE_NPS_WEBHOOK_SECRET` is unset.

**Historical backfill (one-shot):** `scripts/backfill_nps_from_airtable.py` walks the Airtable NPS Survery table, dedupes to the latest Survey Date per linked NPS Clients record, and POSTs each surviving row through the production receiver — same code path as Airtable's automation, same audit trail. Default mode is dry-run; `--apply` fires real requests. First run: 2026-05-03 (M5.4 follow-up after the receiver went live). Runbook at `docs/runbooks/backfill_nps_from_airtable.md` covers modes, report buckets, and the 404 triage flow (the `sent_404_client_not_found` bucket surfaces email mismatches between Airtable and Gregory — useful signal for `clients.metadata.alternate_emails` cleanup). Idempotent — re-runs land identical end states modulo extra `webhook_deliveries` audit rows.

**Dashboard rendering:** `clients.nps_standing` renders in **Section 2 — Lifecycle & Standing** of the client detail page (`components/client-detail/lifecycle-section.tsx`) via the `NpsStandingPill` component (`components/client-detail/nps-standing-pill.tsx`). Replaced the prior `Latest NPS` field that read `nps_submissions.score`; that field is empty for nearly every client because score-piping is deferred to V1.5. The `NpsEntryForm` for manual NPS-score entry stays below the pill (different data source — writes `nps_submissions`, not `nps_standing`). Pill colors are deliberately distinct from status / health-tier palettes to avoid visual collision: `promoter` indigo, `neutral` slate, `at_risk` orange. Null renders as em-dash placeholder (138 of 197 active clients post-backfill have no Airtable submission yet).

## Repo location

Next.js at repo root, alongside the existing Python serverless functions in `api/`. The "dashboard" label survives as a conceptual grouping (Next.js routes live under `app/`, dashboard helpers under `components/` and `lib/`) rather than a literal top-level directory.

```
ai-enablement/
├── api/                     # existing Python serverless functions
├── app/                     # Next.js 14 app router (dashboard routes)
│   ├── (authenticated)/     #   route group — auth-gated layout wraps all child routes
│   │   ├── clients/         #     /clients list + /clients/[id] detail
│   │   └── calls/           #     /calls list + /calls/[id] detail (M3.1)
│   ├── login/               #   /login
│   ├── layout.tsx           #   root layout (html, body, fonts)
│   └── page.tsx             #   root → redirects to /clients
├── components/              # shared UI (top-nav, ui/* shadcn primitives)
├── lib/                     # dashboard utilities
│   ├── db/clients.ts        #   data layer (uses service-role client)
│   └── supabase/            #   client/server/admin Supabase factories + types
├── ingestion/               # existing
├── shared/                  # existing Python utilities
├── supabase/                # existing migrations / seeds
├── package.json             # NEW (Next.js + Tailwind + shadcn deps)
├── next.config.mjs          # NEW
├── tsconfig.json            # NEW
├── pyproject.toml           # existing
├── vercel.json              # MODIFIED — declares framework + Python functions
└── CLAUDE.md
```

### Why Next.js at root, not in `dashboard/`

The original M2.3 spec planned a nested `dashboard/` directory. Reality forced Next.js to repo root because Vercel auto-detects Next.js from a *root-level* `package.json` with a `next` dependency. With Next.js nested, Vercel would need either (a) a project-level `rootDirectory` setting (which would then exclude the existing `api/*.py` serverless functions from the deploy), (b) the legacy `builds` block in `vercel.json` which mixes awkwardly with the modern `functions` block, or (c) a second Vercel project for the dashboard. None match the "single Vercel project; same deploy" constraint that gregory.md committed to.

Putting Next.js at root keeps a single Vercel project with both Next.js and Python serverless functions deploying together. The trade-off is repo-root visual clutter — `package.json`, `next.config.mjs`, `tsconfig.json`, `app/`, `components/`, `lib/` all sit alongside `pyproject.toml`, `api/`, `ingestion/`, `shared/`. Acceptable.

### vercel.json shape

The current `vercel.json` declares (a) the Python functions per file path, (b) the daily Fathom backfill cron, and (c) `"framework": "nextjs"` so Vercel builds the Next.js app alongside the Python functions.

The framework declaration is required, not optional. An explicit `functions` block in vercel.json suppresses Vercel's framework auto-detection from `package.json` — without `"framework": "nextjs"`, Vercel treats the project as static + functions and skips the Next.js build entirely (every dashboard route 404s). Caught and fixed during M2.3a deploy; documented in `docs/followups.md` as the lesson "explicit framework declaration is required when functions is also explicit."

## Stack

- Next.js 14 + TypeScript (per repo language policy)
- shadcn/ui for component primitives (table, dropdown, dialog, form)
- Tailwind for styling
- `@supabase/ssr` for server-side data access + auth
- `@supabase/supabase-js` for client-side hydration
- Generated TypeScript types from Supabase schema (avoid manual sync)

## Build phases

**M2.2** (this session, documentation only): scoping doc + migrations written but not applied + tracker + CLAUDE.md cleanup. No code.

**M2.3** (next session): scaffold + auth + Clients page (list + detail + inline save). Migrations applied. First deploy.

**M2.4** (following session): Calls page (list + detail + edit mode + classification_history writes).

**M2.5** (Drake-led): Aman manual review using the new Calls page. Reclassify ~66 external calls one-at-a-time via "Needs review" filter.

**V1.1 (later, separate session series):** Gregory's brain — Python agent that computes health scores + concerns, writes to `client_health_scores`. UI is already built against the locked `factors` jsonb shape; brain just needs to produce data in that shape.

## What V1 ships without

- No bulk operations on calls (Aman backlog done one-at-a-time)
- No automated sales-call classifier (deferred — manual via dashboard)
- No documents / chunks inspection (deferred to V2)
- No multi-CSM assignments in UI (schema supports, UI shows primary only)
- No CSM rollout / RLS / per-CSM scoping (V2)
- No Gregory brain (V1.1)
- No NPS ingestion pipeline (separate work)
- No Slack notifications from Gregory (V2+)

## Open architectural questions (deferred to V1.1)

- **Concerns vs score, separate or unified output?** V1.1 lean is unified (single jsonb on `client_health_scores`); could split into `client_concerns` table later if real distinction emerges.
- **`factors` jsonb final shape.** Locked-but-open per Drake's call. Proposed shape:

```json
{
  "signals": [
    {"name": "...", "weight": 0.3, "value": "...", "contribution": 15, "note": "..."}
  ],
  "concerns": [
    {"text": "Client mentioned doubt about the methodology in last 2 calls", "severity": "high", "source_call_ids": ["..."]}
  ],
  "overall_reasoning": "..."
}
```

V1 renders raw JSON acceptably; V1.1 nails the shape against whatever Gregory's brain actually produces.

## Working principles

Same as Ella — Gregory follows the four core principles in CLAUDE.md. Specifically:

- Dashboard reads from Supabase only; never queries Fathom or Slack directly.
- All Supabase access goes through a thin data layer (`lib/db/`) so swapping Supabase for another backend is contained.
- Page components are thin clients on the data layer; no business logic in pages.

## Build log

### M2.3a — Dashboard scaffold + auth (deployed 2026-04-28)

Shipped: Next.js 14 + TypeScript + Tailwind + shadcn scaffold at repo root. Supabase Auth wired (email/password). `/login`, auth-gated `/(authenticated)` route group, top nav with Clients / Calls links + logout. Migrations 0012 (`clients.notes`) and 0013 (`call_classification_history`) created as files. Deployed to https://ai-enablement-sigma.vercel.app.

Deviations from the M2.3a spec:

- **Next.js at repo root, not in `dashboard/`.** The original spec assumed a nested directory; Vercel auto-detection requires Next.js at root when `vercel.json` declares explicit functions. Spec section "Repo location" rewritten in this same housekeeping pass to reflect the actual layout.
- **Server Component auth gate, not middleware.** `@supabase/ssr` middleware crashes on Vercel Edge runtime (transitive dep uses Node-only `__dirname`). Replaced with a Server Component auth gate in `app/(authenticated)/layout.tsx` — both are documented Supabase patterns; the Server Component variant is functionally equivalent for our 2-user dashboard. Token refresh happens client-side in `@supabase/supabase-js` when tokens expire; no server-side refresh-on-every-request, which doesn't matter at our scale.
- **Cookie API uses `getAll`/`setAll`** (current pattern). The original spec used the deprecated `get`/`set`/`remove` triplet which crashes silently on Edge.
- **vercel.json required `"framework": "nextjs"`.** The original Task 7 analysis declared the vercel.json edit a no-op; that was wrong — an explicit `functions` block suppresses Vercel's framework auto-detection from `package.json`, so Next.js never built and every dashboard route 404'd. One-line fix.

### M2.3b — Clients pages (deployed 2026-04-28, smoke test pending)

Shipped: Data layer at `lib/db/clients.ts` (`getClientsList`, `getClientById`, `updateClient`, `changePrimaryCsm`). Migration 0014 (`change_primary_csm` Postgres function for atomic CSM reassignment). Clients list page with filters (status / journey / primary CSM / has open action items / auto-created needs review), debounced search on name + email, sortable columns, default sort `last_call_date desc nulls last`. Clients detail page with all 7 sections per spec — Identity (inline-save), Status (inline-save), Primary CSM (confirmation dialog + atomic swap via RPC), Indicators (4 cards: Health Score V1 empty, Call Cadence live, Concerns V1 empty, NPS live-or-empty), Recent Calls (read-only), Open Action Items (read-only), Notes (inline-save to `clients.notes`). Server Actions for inline-save and CSM swap. `needs_review` pill renders in the detail-page header with amber treatment.

Deviations from the M2.3b spec:

- **RLS fix required mid-session.** The data layer was first written using the auth-aware Supabase client (anon key + user session). All 134 clients in cloud, but page returned 0 because every public table has RLS enabled with zero policies (deny-default, already documented as a known issue in `docs/future-ideas.md`). Resolution: split into two Supabase clients — auth client (anon key + cookies, for user session in layout) and data client (service role + no cookies + `'server-only'` import guard, for `lib/db/` queries and `team_members` lookups in the page entry). This matches gregory.md's locked V1 spec ("RLS off for V1; app-level auth gate is sufficient"). Server-side-only constraint enforced; the service role key never reaches the browser bundle.
- **M2.3b smoke test steps 2–10 NOT YET RUN.** Step 1 (visual confirmation: page loads, all 134 clients populating) confirmed by Drake. Steps 2–10 (clicking into a client, inline edits actually persisting, CSM swap creating two `client_team_assignments` rows, filter chips narrowing the list, debounced search, sort toggling) are scheduled as the first task in M3.1 tomorrow. Building Calls pages on top of unverified Clients code would compound risk; the smoke test gates M3.1b.
- **`shadcn form` component skipped.** shadcn v4's registry didn't expose a `form` component under that name; the login form and detail-page inputs use plain controlled state + Server Actions instead of `react-hook-form`. Revisit if M3.x adds forms with non-trivial validation.
- **Tailwind v4 + shadcn v4** (not v3 as originally implied). shadcn v4's emitted components target Tailwind v4 utilities (`ring-3`, OKLCH theme colors, `@theme inline` directive, `@base-ui/react` primitives). Local upgrade was the cleaner path than backporting components to v3.

### M3.2 — Merge feature for auto-created clients (built 2026-04-29, deploy pending)

Shipped: end-to-end "Merge into…" flow on the Clients detail page for rows tagged `needs_review`. Five logical pieces:

- **Migration 0015 — `merge_clients(p_source_id uuid, p_target_id uuid) returns jsonb`.** Atomic plpgsql function performing all five merge steps in one transaction: (1) reattribute `call_participants.client_id`, (2) re-point `calls.primary_client_id` and flip `is_retrievable_by_client_agents=true`, (3) re-point + reactivate transcript_chunk `documents` whose `metadata.call_id` is in the source's call set, (4) soft-archive source via `archived_at=now()` + stamp `metadata.merged_into` / `metadata.merged_at`, (5) sync `metadata.alternate_emails` and `metadata.alternate_names` on target (always runs, dedupes via jsonb containment). Idempotency gate is `source.metadata.merged_into` — if set, steps 1–4 skip; step 5 always runs to fill retroactive gaps. Validation raises on: source missing, target missing, target archived, source not tagged `needs_review`, source == target. Returns a counts summary the dashboard surfaces in toasts.
- **Data layer at `lib/db/merge.ts`.** `mergeClient(sourceClientId, targetClientId)` calls the RPC and narrows raw Supabase errors into the dashboard's `success/error` result type. `listMergeCandidates(excludeClientId)` powers the dropdown — fetches `id, full_name, email` for every active client other than the source, ordered by name. Sibling file to `clients.ts` because merge is a multi-table operation, not a per-field client update.
- **Server Action `mergeClientAction` in `app/(authenticated)/clients/[id]/actions.ts`.** Wraps `mergeClient`, revalidates the source detail path, the target detail path, and the Clients list on success. No per-action auth verification — matches the existing actions pattern (the `(authenticated)` route-group layout gates every request to this path).
- **Reusable `SearchableClientSelect` at `components/searchable-client-select.tsx`.** Fetch-all-on-mount + client-side filter as the user types. ~134 rows comfortably; logged followups for the scaling triggers (~800 clients) and the transcript-doc-query scaling trigger (~50k transcript_chunk docs) so neither one becomes a surprise. Designed for reuse in the M3.3 Calls page primary-client picker.
- **`MergeClientButton` + dialog at `app/(authenticated)/clients/[id]/merge-client-button.tsx`.** Renders next to the amber `needs_review` pill in the detail-page header, only for `needs_review`-tagged clients. Dialog body explains the reattribution + archive consequence in plain language with the "reversible only by manual SQL" warning. On confirm: Server Action fires; on success the user is redirected to the target's detail page (the source is archived and would 404). On failure: error renders inline in the dialog and the dialog stays open.

Deviations from the originally-deferred M2.3c spec:

- **TypeScript-native via Postgres function, not a Vercel Python function.** The deferred spec called for `api/merge_clients.py` wrapping the existing `scripts/merge_client_duplicates.py`. Replaced with: (a) plpgsql function `merge_clients` in migration 0015 carrying the full merge body atomically, (b) TypeScript Server Action calling the RPC. Reasoning: the Python wrapper would have introduced an HTTP hop with no per-request transactionality (the script's 5 steps are sequential `UPDATE`s, partial-failure recovery is difficult), while the plpgsql function is single-transaction and matches the existing `change_primary_csm` pattern from M2.3b. The Python script was archived to `scripts/archive/merge_client_duplicates.py` in the same session as historical record of the four pilot pairs already merged.
- **Pulled forward in session ordering.** Originally slotted as M2.3c, deferred until after M3.3 Calls. M3.2 swapped this in (after the M3.1 smoke test) to clear the `needs_review` queue before Calls work begins.
- **No recovery runbook written.** The non-transactional-merge concern that motivated a runbook in option (a) is moot because the function is single-transaction by construction — partial failures roll back.
- **No SQL tests added.** The repo has no plpgsql test pattern today (Python tests live alongside Python code; the dashboard layer has no tests yet). Verification path: end-to-end test against a real source/target pair from the cloud `needs_review` queue, picked by Drake before deploy. The existing Python tests for `scripts/archive/merge_client_duplicates.py` stay as-is — they test the reference implementation, which is unchanged.

**Verified live 2026-04-29.** Migration 0015 applied to cloud via Studio + ledger registration; dual-verified (`pg_proc` returns `merge_clients` with 2 args returning `jsonb`, `security definer = true`; `supabase_migrations.schema_migrations` carries the 0015 row). Live merge ran beyond the recommended single Vid pair — three Vid rows existed (canonical `vid.velayutham@gmail.com` plus two auto-created at `vid@remodellectai.com` and `vid.velayutham@remodellectai.com`), so two sequential merges into the gmail canonical were performed. Both sources archived + stamped with target id; target accumulated *both* source emails into `metadata.alternate_emails` (the dedup-aware accumulator works correctly across sequential merges into the same target — a stronger stress test than a single pair); 5 calls re-pointed to target with `is_retrievable_by_client_agents = true`; transcript chunks reattributed and reactivated; zero orphan participants. Two visual flags surfaced and resolved: (a) "Call cadence didn't update" was a false alarm — most recent call across all three Vids was April 13, which the canonical already showed; (b) "Alternate emails not visible on the client detail page" was confirmed as a UI omission, not a merge bug — Section 1 (Identity) doesn't render `metadata.alternate_emails` / `alternate_names` because those fields are consumed server-side by the Fathom classifier. Logged in `docs/followups.md` as a small polish-pass fix.

### M3.3 — Calls page (built 2026-04-29, migration 0016 + deploy pending)

Shipped: end-to-end Calls list + detail with edit-mode classification save and per-changed-field audit rows. Five logical pieces:

- **Migration 0016 — `update_call_classification(p_call_id, p_changes jsonb, p_changed_by uuid)`.** Atomic plpgsql function applying classification edits in one transaction. Compares each incoming key in `p_changes` against the current row, writes one `call_classification_history` row per actually-changed field, then updates `calls`. Server-side enforcement: non-client category auto-clears `primary_client_id` (separate history row); `is_retrievable_by_client_agents` auto-derived (true iff `category='client' AND primary_client_id IS NOT NULL`); `classification_method` auto-set to `'manual'`. No-op silently when no fields differ. Same security-definer + jsonb-return shape as `merge_clients` and `change_primary_csm`.
- **Data layer at `lib/db/calls.ts`.** `getCallsList` does a single PostgREST round trip with nested `primary_client` and `call_participants` selects, then JS-side filters for the participant search (matches title + participant name/email). The `needs_review` filter is a three-way PostgREST `or()`: `confidence < 0.7`, `category = 'unclassified'`, or `(category = 'client' AND primary_client_id IS NULL)`. `getCallById` parallelizes participants / action items / summary / primary_client fetches. `updateCallClassification` wraps the RPC with whitelist enforcement (rejects non-editable field names before the round trip).
- **List view at `app/(authenticated)/calls/page.tsx`.** Sortable table with the 8 spec columns; default sort `started_at desc`; when the `Needs review` chip is on and no explicit sort is chosen, defaults to `confidence asc` so the lowest-confidence calls float to the top. Filter bar: category chips, "Filter by client…" button opening a `Dialog` with the M3.2 `SearchableClientSelect`, debounced 300ms search.
- **Detail view at `app/(authenticated)/calls/[id]/page.tsx`.** Six sections per spec. Section 2 is the only editable surface — explicit Edit button reveals dropdowns + Save/Cancel; Section 6 transcript is collapsed by default. The page entry passes the full client list to `ClassificationEdit` so the picker is always available without an extra round trip.
- **Server Action `updateCallClassificationAction`.** Wraps the data-layer fn, revalidates `/calls/${id}` and `/calls` on success, calls `router.refresh()` from the client to pick up the new state without a full nav. No per-action auth verification — route-group layout pattern, same as M3.2.

Deviations from the M3.3 spec:

- **Confidence threshold for "Needs review" set to 0.7.** Cloud distribution justified the choice: 6 calls below 0.5, 105 below 0.7, no rows in 0.7–0.8 (a clean cliff). 0.7 is the natural break — see §3 "What could go wrong" surfacing in this prompt's pre-build report.
- **Section 4 reads from `documents`, not `calls.summary`.** The original spec said "calls.summary if present, otherwise empty state." But `calls.summary` is empty for all 560 cloud rows; summaries live as `documents` rows of `document_type='call_summary'` keyed on `metadata.call_id`. `getCallById` queries `documents` for the latest matching row. Logged in followups: either backfill `calls.summary` from `documents` on ingest or drop the column.
- **`call_type` "(unset)" handling.** 175 of 560 calls have `call_type=null`. Read mode shows "(unset)" for null; edit mode dropdown's first option is `(Unset)` (value=`""`) which the function translates to `null`. All other enum values from migration 0003's column comment (`sales`, `onboarding`, `csm_check_in`, `coaching`, `team_sync`, `leadership`, `strategy`, `unknown`) included regardless of cloud-data presence.
- **Diff-only save.** UI builds a diff of fields that differ from the initial call values and sends only those. The function would also handle "send all 3" correctly (its `is distinct from` comparisons dedup), but the diff approach makes the audit trail honest about user intent.
- **`changed_by` is null in V1.** Migration 0013's column comment accommodated this: "auth.users to team_members join via email is best-effort." Server Action passes null; no per-action user resolution wired yet. Same pattern as `changeClientPrimaryCsm`'s reserved-but-unused `_current_user_team_member_id` parameter.
- **No SQL tests added.** Consistent with M2.3b / M3.2: the dashboard layer has no test pattern yet, and the plpgsql function isn't exercised by the existing Python suite.

**Migration 0016 not yet applied.** Drake applies via Studio + manual ledger registration before deploy.

**Verified live 2026-04-29.** Migration 0016 applied to cloud via Studio + ledger registration; dual-verified (function exists with three-arg signature `(p_call_id uuid, p_changes jsonb, p_changed_by uuid) returns jsonb`, `security definer = true`, ledger row landed). No-op smoke test (passing `'{}'::jsonb` for `p_changes`) returned the expected shape `{fields_changed: 0, history_rows_written: 0, auto_cleared_primary_client_id: false}`. Deploy hit one transient build failure that resolved on redeploy (logged separately in followups). Live UI smoke test on the cloud-deployed dashboard: edited a low-confidence call (Fathom external_id `137772208`) by changing its `call_type` via the detail page Save button. Outcome: exactly one row landed in `call_classification_history` with the correct `field_name='call_type'`, the prior value as `old_value`, the new value as `new_value`, and `changed_at` set to the save moment. `changed_by` is null per the V1 stance. Detail-page Section 2 reflected the new state on reload, `classification_method` showing `manual`. End-to-end verified.

### M3.4 — Gregory brain V1.1 (built 2026-04-29, deploy pending)

Shipped: end-to-end brain agent that computes per-client health scores + tier + (gated) concerns, plus weekly Vercel cron, manual-trigger script, and 37 unit tests. Architecture is complete; concerns generation is gated off until summary coverage densifies.

Pieces:

- **`agents/gregory/` package.** `signals.py` (4 deterministic signals — call cadence, open/overdue action items, latest NPS), `scoring.py` (rubric → 0-100 score + green/yellow/red tier, with insufficient-data default = yellow/50), `concerns.py` (Claude-driven, env-var-gated), `prompts.py` (concerns system prompt + user-message builder), `agent.py` (entry: `compute_health_for_client` + `compute_health_for_all_active`, agent_runs lifecycle wired with `duration_ms` populated — closes the duration-never-written gap for this agent).
- **Cron at `api/gregory_brain_cron.py`.** Weekly Mondays 09:00 UTC via `vercel.json`. BaseHTTPRequestHandler matching the `fathom_backfill` pattern. Bearer-token auth via `GREGORY_BRAIN_CRON_AUTH_TOKEN` (per-source namespaced env var, same convention as `FATHOM_BACKFILL_AUTH_TOKEN`).
- **Manual trigger at `scripts/run_gregory_brain.py`.** Three modes: `--client-id <uuid>`, `--email <addr>`, `--all`. Single-client mode is the M3.4 hard-stop verification path (Drake reviews one row in Studio before the all-active sweep lands).
- **Dashboard empty-state copy updated.** `ConcernsIndicator` and `HealthScoreIndicator` no longer say "Gregory will populate this in V1.1" — they now reflect the actual V1.1.0 state ("activates as call summary coverage grows" / "writes scores on the weekly cron run").

Spec deviations:

- **Concerns generation gated behind `GREGORY_CONCERNS_ENABLED` env var, default false.** Cloud reality at ship time: 22 `call_summary` documents across 132 active clients (~85% would have empty input). Paying the LLM cost to hand Claude nothing was the deciding factor. Architecture is complete; flag flips on without a code change once data densifies. Documented in this section's "Concerns generation (gated)" subsection above.
- **Cron weekly, not daily.** Signal change rate is slow (call cadence shifts day-to-day for ~5 clients tops; action items churn gradually). Weekly cadence is enough; daily would compound LLM cost when concerns flag flips on.
- **Slack engagement signal omitted.** `slack_messages` cloud table is empty (local-only ingestion). Add as a fifth signal once cloud Slack ingestion lands — re-balance weights at that time. Logged in followups.
- **No formal eval harness.** Same V1 carve-out as Ella. The 37 unit tests cover signal math, rubric, JSON parsing, and end-to-end wiring; golden-dataset eval is deferred until the rubric stabilizes.

**Migration count: 0.** No new migration required — `client_health_scores` and `agent_runs` already exist (migrations 0005, 0006).

**Not yet deployed.** Per M3.4 hard stops, Drake reviews `vercel.json` diff and confirms `GREGORY_BRAIN_CRON_AUTH_TOKEN` is set in Vercel before push + deploy. First cloud run is single-client (Drake-reviewed in Studio) before the all-active sweep lands.

**Verified live 2026-04-29.** Vercel deploy succeeded (one transient build failure during the day resolved on redeploy — pattern noted in followups). `GREGORY_BRAIN_CRON_AUTH_TOKEN` set in Vercel env vars. **Single-client verification on Vid Velayutham** produced `score=70, tier=green, insufficient_data=false, concerns=0`. Factors math checks out: cadence 16 days ago → contribution 50 (mid-band), open action items 0 → 100 (clean docket), overdue 0 → 100, NPS missing → neutral 50. Weighted: `0.4×50 + 0.2×100 + 0.2×100 + 0.2×50 = 70`. Tier `green` per the ≥70 threshold. **All-active sweep** (`scripts/run_gregory_brain.py --all`) completed in ~6 minutes, landing 132 `client_health_scores` rows + 132 `agent_runs` rows (per-client wiring, every compute opens its own row, all `status='success'`, `duration_ms` populated — closes the duration-never-written gap for this agent). Tier distribution: **93 green / 40 yellow / 0 red**, zero rows with `insufficient_data=true`. Concerns generation gated off (`GREGORY_CONCERNS_ENABLED` unset), so every `factors.concerns[]` is empty — confirmed in spot-checks of the dashboard's Concerns indicator (now reads "No concerns surfaced — concerns generation activates as call summary coverage grows" per the M3.4 empty-state copy update). One rubric quirk surfaced: never-called clients still land green via the "0 action items = clean docket" interpretation (logged as a followup with two resolution options).

First scheduled cron run hits next Monday 09:00 UTC. Manual sweeps via the script are fine in the meantime.

### M5.5 — Comprehensive filter bar on /clients (shipped 2026-05-03, visual smoke implicitly verified through M5.6 smoke 2026-05-04)

Shipped: replacement of the chip-row + single-CSM-dropdown filter bar with a row of 9 dropdowns. 5 active multi-selects, 1 single-value toggle, 3 disabled placeholders that signal next-slice work to Scott during Monday's onboarding. Highest-priority push #1 from the M5 V1-adoption pivot — Scott reads "match the master sheet so I'll adopt Gregory" and the filter bar is the surface he'll spend most of his daily time on.

Pieces:

- **`lib/client-vocab.ts` — single source of truth for the four UI-surfaced clients vocabularies.** Status / csm_standing / nps_standing / trustpilot_status, each as `*_OPTIONS` (`{value, label}[]` with `as const satisfies readonly VocabOption[]`) plus a `*_VALUES` derived array for membership checks. Mirrors the DB CHECK constraints from migrations 0019 (status), 0020 (trustpilot rename), and 0021 (nps_standing). Color treatments stay co-located with their pill components — vocab is shared, visual treatment is a per-component concern. Closes the M5.4 followup that anticipated this share when the M5.5 NPS Standing filter dropdown landed.
- **`app/(authenticated)/clients/multi-select-dropdown.tsx` — base-ui filter primitive.** Built on the existing `DropdownMenu` + `DropdownMenuCheckboxItem` from `components/ui/dropdown-menu.tsx`; no new primitive system installed. Trigger label modes: `'multi'` (default, "{label}: {first} +{N}") and `'toggle'` ("{label}: on"). Disabled variant renders the same trigger silhouette as a plain `<button disabled>` with a `title` attribute for the hover hint — no Tooltip primitive is available and installing a Radix-based shadcn Tooltip would fragment the codebase's base-ui-only component aesthetic.
- **Filter bar rewrite at `app/(authenticated)/clients/filter-bar.tsx`.** 9 dropdowns in a `flex flex-wrap` row: Status, Primary CSM, CSM Standing, NPS Standing, Trustpilot (active multi-selects); Needs review (single-value toggle); Accountability, NPS toggle, Country (disabled placeholders with hover-tooltip hints describing what each will gate on once it ships). Search input + "Clear filters" button on a row above. Search stays debounced 300ms.
- **URL state model.** Each multi-select serializes as comma-separated values (`?status=active,ghost`). OR-within-dropdown, AND-across-dropdowns. Status carries a default-vs-explicit-empty sentinel: param absent → pre-check the default trio (`['active', 'paused', 'ghost']`) and keep the URL clean; param empty (`?status=`) → "user has unchecked everything, show all statuses including churned/leave"; param populated → `.in()` clause. The writer collapses the default-trio case via *set equality* (order-independent), so re-checking the three defaults in any click order returns to a clean URL. Sort + dir are orthogonal — preserved by every `writeParams` call and by `clearAll`.
- **Filter shape rewrite at `lib/db/clients.ts`.** `ClientsListFilters` switches from single-value to `string[]` arrays. DB-side via PostgREST `.in()` for `status` / `csm_standing` / `nps_standing` / `trustpilot_status`. JS-side filter for `primary_csm_ids` — matched against the active primary CSM derived from the `client_team_assignments` join (can't be expressed as a server-side `.in()` because the value lives in a nested select). Drops dead `has_open_action_items` / `show_archived` / `journey_stage` / `needs_review_only` branches; `needs_review` preserved under its new boolean shape with the same `tags @> ['needs_review']` predicate.
- **`EditableField.options` widened to `ReadonlyArray<...>`.** Supporting refactor so the vocab module's `as const` exports flow into the existing inline-edit dropdowns (lifecycle-section's CSM standing selector, adoption-section's Trustpilot selector) without manual narrowing at the call sites.

Deviations from the M5.5 spec:

- **`primary_csm_id` URL param renamed to `primary_csm`** for consistency with the other multi-value params. Deliberate break of any M3-walkthrough bookmarks Scott may have. Drake-confirmed at acclimatization time; Monday's onboarding is a fresh-start state where bookmark cost is negligible against the URL-naming-consistency win.
- **`mode: 'toggle'` prop on MultiSelectDropdown** beyond the spec's API. Needed for the Needs review dropdown — without it the trigger would read "Needs review: Auto-created — needs review" (long option label echoed back). With `mode='toggle'`, the trigger reads "Needs review: on" when checked, "Needs review" muted when unchecked. Single-line addition to the multi-select primitive; no separate component.
- **Trustpilot dropdown labels kept short** ("Yes", "No", "Ask", "Asked") matching the existing `adoption-section.tsx` inline-edit dropdown, not the spec's longer "Yes (review left)" / "No (declined)" form. Pre-baked rule from the spec's "prefer existing source and surface the diff" clause; surfaced at acclimatization, Drake confirmed.
- **`journey_stage` filter dropped** beyond the spec's explicit "drop has_open_action_items / show_archived / needs_review_only" instruction. The appendix's Change 3 `ClientsListFilters` shape doesn't include `journey_stage`; no UI exposes it after the chip removal; dead code removed.
- **`STATUS_DEFAULT_SELECTED` duplicated** between `filter-bar.tsx` (Client Component) and `page.tsx` (Server Component) rather than imported from a shared location. The 'use client' boundary makes a single import path awkward; both copies tested at the smoke checkpoint. Drift risk is small (one constant, two files) but flagged here.

**Migration count: 0.** Pure UI + data-layer change — vocab values come from existing DB CHECK constraints (0019, 0020, 0021).

**Smoke checkpoint passed 2026-05-03.** `next build` clean (0 type errors, 8/8 static pages, `/clients` route bundle 32.1 kB). 7 URL-equivalent SQL count probes against cloud all sensible: default trio = 145 (matches 145 + 52 churned = 197 non-archived from CLAUDE.md exactly); explicit-empty status = 197 (✓ all non-archived); `?needs_review=1` under default status = 24 (matches followups.md's "24 auto-created clients" exactly); `?nps_standing=promoter,neutral` under default = 48 ≈ 49 (CLAUDE.md's 27 promoter + 22 neutral; -1 for one outside default-visible — consistent); `?trustpilot=yes,no` under default = 82 ≤ 90 (-8 for ones in churned/leave — consistent); two-dropdown intersection `?status=active&csm_standing=at_risk` = 16 (subset of 145 default). Risks from the pre-build report: (1) default-state-vs-explicit-empty sentinel implemented per spec, (2) `DropdownMenuCheckboxItem` close-on-click neutralized at probe time — base-ui's default is `closeOnClick: false`, opposite of Radix, no special-case needed, (3) `primary_csm_id` rename shipped per Drake's confirmation. Visual eyeball on the auth-gated dashboard pending Drake's push + browser session.

**Pushed during the smoke greenlight window.** Three commits at `c761207` (vocab module + nps-standing-pill refactor) → `d8febaa` (MultiSelectDropdown) → `4059602` (FilterBar + page + getClientsList). Vercel auto-deploy follows the push. Visual smoke through the auth-gated dashboard UI is the remaining verification step — pending Drake's eyeball.

### M5.6 — Status cascade + Scott Chasing + accountability/NPS toggles (shipped 2026-05-04, hotfix landed same day)

Shipped: DB-level cascade so when a client's `clients.status` moves to a negative value (`ghost` / `paused` / `leave` / `churned`), a coordinated set of derived field changes auto-fire in one transaction:

1. `csm_standing` → `'at_risk'` (history row written, attributed to Gregory Bot)
2. `accountability_enabled` → `false`
3. `nps_enabled` → `false`
4. `primary_csm` reassigned to the **Scott Chasing** sentinel team_member
5. `trustpilot_status` — explicitly NOT touched (Scott was clear)

Implements Scott's Loom 1 + Loom 3 walkthroughs ("safer to default off whenever unsure"). Cascade is **one-directional** — there is no symmetric trigger for `active`. CSMs can manually flip `accountability_enabled` / `nps_enabled` back to `true` via the dashboard; the override is **not sticky** — a future negative-going status transition re-fires the cascade and flips them back to false. The dashboard surfaces an `active+off` amber hint on the toggles so re-activations don't go un-noticed.

Pieces:

- **Migration `0022_status_cascade.sql`.** Schema additions: `clients.accountability_enabled boolean not null default true`, `clients.nps_enabled boolean not null default true`, `team_members.is_csm boolean not null default false`. Sentinel: `Scott Chasing` team_member, UUID `ccea0921-7fc1-4375-bcc7-1ab91733be73`, `role='csm'`, `is_csm=true`, `metadata.sentinel=true`. Triggers: `clients_status_cascade_before` (BEFORE UPDATE — mutates NEW row in-flight) + `clients_status_cascade_after` (AFTER UPDATE — writes history row + reassigns primary_csm). Both gated on `OLD.status IS DISTINCT FROM NEW.status AND NEW.status IN ('ghost','paused','leave','churned')`. The AFTER trigger handles primary_csm reassignment via `INSERT ... ON CONFLICT (client_id, team_member_id, role) DO UPDATE SET unassigned_at = NULL, assigned_at = now()` — the unique-key collision case fires when a client gets cascaded → manually reassigned to a real CSM → cascaded again, leaving the original Scott-Chasing assignment archived but present.
- **Updated `update_client_status_with_history` RPC.** Same signature, same allowlist. Adds `set_config('app.current_user_id', p_changed_by::text, true)` at the top of the function body (when `p_changed_by IS NOT NULL`) so the AFTER trigger can read the human attribution via `current_setting('app.current_user_id', true)`. SET LOCAL via `set_config(_, _, true)` is transaction-scoped; clears on COMMIT/ROLLBACK. Verified at smoke: probe A (RPC with GUC) landed Lou's UUID in the note; probe B (direct UPDATE in a fresh transaction immediately after A) landed `:by:NULL` — no leak.
- **Structured note format on cascade-induced rows.** `cascade:status_to_<status>:by:<uuid_or_NULL>` for transition-fired rows; `cascade:backfill:m5.6` for the migration's data backfill. SQL-side joinable to recover "which human triggered this cascade" — see audit query below.
- **Data backfill for current negative-status clients.** Two passes (history insert before UPDATE so the SELECT reads pre-update state). 82 clients in negative status flipped: 65 got `cascade:backfill:m5.6` history rows; 17 are silent toggles where `csm_standing` was already `'at_risk'` so no history row was written (snapshot at `docs/data/m5_6_silent_toggle_backfill.md`; recovery query in `docs/followups.md`). Primary_csm reassignment intentionally skipped for the backfill — the 32 currently-CSM-owned negative-status clients (Lou 18, Scott Wilson 13, Nabeel 1) keep their assignments. Drake decides manual cleanup post-apply.
- **`is_csm` backfill + dashboard dropdown filter.** `is_csm = true` set on the four real CSMs (Lou Perez, Nico Sandoval, Scott Wilson, Nabeel Junaid) + Scott Chasing sentinel. Both team_members SELECT sites in the dashboard now filter on `is_csm = true`: the M5.5 filter bar's `primaryCsmOptions` query in `app/(authenticated)/clients/page.tsx`, and the swap-CSM dialog's team_members fetch in `lib/db/clients.ts:getClientById`. Post-M5.6 the Primary CSM dropdowns show 5 options (the four CSMs + Scott Chasing); engineering / ops / sales / Gregory Bot are excluded.
- **`BooleanToggleField` in `components/client-detail/adoption-section.tsx`.** Small custom component for the two new toggles. Built rather than extending `EditableField` because the active+off warning hint depends on a sibling field (`client.status`) the generic component doesn't see. Visual treatment: amber border + ⚠ icon + `title` attribute tooltip on the trigger when `client.status === 'active' && client.<toggle> === false`. Same amber palette as the existing `needs_review` pill — reusing rather than introducing a new warning-color convention.
- **`UPDATABLE_FIELDS` + `FIELD_TYPES` extended in `lib/db/clients.ts`.** New `'boolean_toggle'` field type added to the `FieldType` union; Server Action narrowing accepts `true` / `false` / `'true'` / `'false'`, rejects null (the columns are `NOT NULL DEFAULT true`).
- **`lib/supabase/types.ts` hand-edits.** `accountability_enabled` + `nps_enabled` added to clients Row/Insert/Update + the three RPC `Returns` types that mirror clients shape (status / journey_stage / csm_standing). `is_csm` added to team_members Row/Insert/Update. Per CLAUDE.md the Supabase types regen path is broken; the standing followup tracks the manual-edit gap.

Audit-trail SQL query — find cascade-induced standing changes by who triggered them:

```sql
select
  c.full_name,
  csh.changed_at,
  split_part(csh.note, ':', 4) as triggered_by_user_uuid,
  tm.full_name                  as triggered_by_name,
  csh.csm_standing              as cascade_set_to,
  csh.note
from client_standing_history csh
join clients c on c.id = csh.client_id
left join team_members tm on tm.id::text = split_part(csh.note, ':', 4)
where csh.note like 'cascade:status_to_%'
order by csh.changed_at desc;
```

Notes on the query: `split_part(note, ':', 4)` returns the literal string `'NULL'` for cascade rows where no GUC was set (direct UPDATE via Studio, or a calling RPC that didn't set the GUC). The LEFT JOIN handles that — rows with `:by:NULL` show `triggered_by_name = NULL` (no UUID matches the literal string `'NULL'`). Future-proofing if the literal-NULL convention proves annoying: wrap with `nullif(split_part(note, ':', 4), 'NULL')` before the join.

Spec deviations:

- **17 silent-toggle clients accepted with snapshot + recovery query** (Drake call (a)+(d)). Pre-apply count was 17, above the spec's single-digit acceptance threshold. Drake confirmed accept-and-document path: `docs/data/m5_6_silent_toggle_backfill.md` carries the static UUID list; `docs/followups.md` carries the recovery query for re-derivation post-hoc.
- **Scott Chasing sentinel `role='csm'`** (Drake call). Distinct from Gregory Bot's `role='system_bot'` — Scott Chasing functions as a CSM placeholder from the dashboard's perspective (clients get assigned to it like any real CSM). The orthogonal `metadata.sentinel=true` flag remains the "exclude from real-team listings" filter.
- **Primary_csm reassignment skipped for backfill** (per spec). 32 currently-CSM-owned negative-status clients (Lou 18 / Scott Wilson 13 / Nabeel 1) keep their existing primary_csm assignments. Drake decides manual cleanup post-apply via the dashboard's swap-CSM dialog.
- **Custom `BooleanToggleField` over EditableField extension.** The active+off warning hint depends on `client.status`, which the generic EditableField doesn't carry. Adding the warning to EditableField would couple it to the parent client shape. Contained in adoption-section.tsx; ~70 lines.
- **stale `team_members.md` flagged + backfilled.** Doc listed only V1 seed (Scott / Lou / Nico / Drake / Nabeel / Zain) but live cloud has 11 rows including Aman (sales), Ellis (ops), Huzaifa (ops). Doc updated as part of Step 5 to mirror live state + add Scott Chasing to the sentinel table.

**Migration count: 1** (`0022_status_cascade.sql`).

**Smoke checkpoint passed 2026-05-04.** Migration applied to cloud via psycopg2; dual-verified (11/11 schema + ledger checks). Four SQL probes: A — RPC with GUC landed `:by:<lou-uuid>`. B — direct UPDATE in fresh transaction immediately after A landed `:by:NULL` (no GUC leak — the SECURITY DEFINER + SET LOCAL pattern works as designed; this was the highest-priority verification per Drake's pre-apply condition). C — re-fire idempotency on client_a (paused → ghost) wrote a new history row, did not double-swap primary_csm (correctly stayed Scott Chasing). D — both probe clients fully reset to pre-state (history rows preserved per immutability). `next build` clean: 0 type errors, 8/8 static pages, `/clients/[id]` route bundle 10.4 → 10.8 kB.

Risks post-build:

1. **GUC under SECURITY DEFINER + SET LOCAL** — *did not materialize* (probes A + B confirmed no leak).
2. **`UNIQUE` collision on re-cascade** — *not yet exercised in smoke.* Probe C re-fired the cascade on client_a, but client_a's active assignment was already Scott Chasing so the no-op-when-already-Scott-Chasing branch fired. The `ON CONFLICT (client_id, team_member_id, role) DO UPDATE` path will be exercised the first time a CSM manually reassigns a cascaded client back to a real CSM and that client subsequently gets cascaded again. Worth a follow-up live verification once a real cascade-then-reassign-then-recascade pattern surfaces.
3. **Backfill UPDATE accidentally firing the cascade** — *did not materialize.* The backfill UPDATE doesn't touch status; the trigger's `OLD.status IS DISTINCT FROM NEW.status` guard correctly evaluates false. 65 cascade:backfill:m5.6 rows landed via the explicit INSERT path; no surprise extras.
4. **active+off UI hint requires `client.status` in the toggle's data flow** — *resolved at design time* by building a custom `BooleanToggleField` rather than extending `EditableField`. Section reads `client.status` and `client.<toggle>` together at the call site; passes computed `warn` boolean down. EditableField stays unchanged.

**M5.6 commit chain shipped 2026-05-04** (all on origin/main): `fe51fec` (M5.5 carryover docs) → `4f8811f` (migration 0022) → `7251906` (dashboard wiring) → `5e57983` (close-out docs) → hotfix follow-up below.

#### M5.6 hotfix — three regressions surfaced by visual smoke (shipped 2026-05-04)

The expanded visual smoke triggered by the M5.6 deploy surfaced three bugs. Two of them were **pre-existing** issues never tested before; one was the M5.6 cascade exercising a 0014-era code path the migration apply briefly hit and the trigger had already correctly fixed inline. Documenting honestly because the audit trail benefits from "this bug existed for X commits before being caught" being visible — informs future smoke-test scoping.

- **Bug 1 — `clients.status` edit silently failed** (Section 1 of the client detail page). Click registered, dropdown closed, no Server Action fired. Pre-existed M5.6 — root cause introduced in M4 commit `19f4e50` ("feat(client-detail): add EditableField, EditableTagsField, NpsEntryForm") via the `setTimeout(commit, 0)` pattern in EditableField's enum onChange. Affected every enum and three_state_bool dropdown (status, csm_standing, trustpilot, ghl_adoption, sales_group_candidate, dfy_setting). Went untested until M5.6's expanded visual smoke because nobody had previously edited those specific fields through the dashboard end-to-end with a network-tab eye on them.
- **Bug 2 — `clients.csm_standing` edit silently failed** (Section 2). Same root cause as Bug 1, same fix.
- **Bug 3 — `change_primary_csm` RPC errored on swap-back-to-archived-CSM** with a unique-key violation. The 0014 RPC unconditionally INSERTed the new (client, member, primary_csm) row after archiving the active one — but `client_team_assignments` has `UNIQUE (client_id, team_member_id, role)` so a previously-archived row collided. The M5.6 cascade trigger (migration 0022) had hit the same case and used `ON CONFLICT (...) DO UPDATE SET unassigned_at = NULL, assigned_at = now()` to reactivate; the dashboard-facing RPC didn't get the same treatment until 0023 aligned it.

Root cause analysis on Bug 1+2 — the `setTimeout(commit, 0)` in `editable-field.tsx`'s enum onChange queued a macrotask that captured the THIS-render `commit` closure. The closure read `draft` from React state at queue time — **before** the just-fired `setDraft(e.target.value)` had taken effect. By the time the macrotask fired, React had re-rendered with the new draft, but the queued commit was a stale reference. It computed `parsed.value` from the OLD draft, hit `rawEquals(parsed.value, committed) === true`, took the "no change — exit cleanly" branch, and exited without calling `onSave`. The user saw a closed dropdown and assumed the save fired. The text/textarea/integer paths were unaffected because they call `commit()` from `onBlur` — a separate event handler that runs after typing has settled, with a fresh closure.

Pieces:

- **Migration `0023_change_primary_csm_on_conflict.sql`** — single-function `CREATE OR REPLACE` that replaces `change_primary_csm` with the ON CONFLICT variant. Same signature, same `language plpgsql security definer`, same archive-then-insert two-step. Behavior change purely additive (previously-erroring case now succeeds; previously-working first-time-assignment path unchanged). Mirrors the M5.6 status cascade trigger's primary_csm reassignment pattern (0022) so cascade-fired and dashboard-fired paths produce identical row shapes. Explicit `GRANT EXECUTE on ... to service_role` preserved for symmetry with 0018+ RPCs (discoverable via grep without needing the CREATE OR REPLACE preservation rule).
- **EditableField fix in `components/client-detail/editable-field.tsx`** — `commit` accepts an optional `draftOverride: string`; the enum / three_state_bool select onChange passes `e.target.value` directly (the new value is already in hand at that point); `setTimeout` dropped. Text/textarea/input onBlur paths wrap as `() => commit()` so React's FocusEvent doesn't get coerced into the new optional parameter. ~15 LoC net change including a multi-paragraph comment block explaining the failure mode for future readers.

Smoke verification:

- **Bug 3** — SQL probe (no UI needed) on Allison Jayme Boeshans (test client): swap Lou → Nico → Lou via the RPC. Step 2 (Nico → Lou, the previously-erroring case) succeeded with `+1` row delta — the archived Lou row reactivated rather than a duplicate landing.
- **Bug 1+2 + the four enum fields** — visual smoke through the auth-gated dashboard (Drake-driven, 2026-05-04). Status (Section 1), csm_standing (Section 2), trustpilot_status (Section 6), and one three_state_bool (Section 6) all edit + persist correctly. Cascade fires correctly through the dashboard path on negative-status transitions (status edit → cascade history row with `cascade:status_to_<x>:by:NULL` + csm_standing/accountability/nps flipped + primary_csm reassigned to Scott Chasing). Bug 3 swap-back also verified through the dashboard CSM swap dialog.

Untested but probably-affected pre-fix (verified working post-fix since they share the renderEditor branch): `ghl_adoption` (enum), `sales_group_candidate` (three_state_bool), `dfy_setting` (three_state_bool). Single fix covers the entire enum + three_state_bool family.

Hotfix commits on origin/main: `8d27e1e` (migration 0023) → `c2d59f4` (EditableField fix). Vercel auto-deploy followed Drake's manual redeploy.

Future-proofing: visual smoke scope expanded to include "edit-and-persist for every enum-variant field on the client detail page" going forward. The EditableField stale-closure bug existed for ~30+ commits across M4 → M5.6 before being caught; the cost of catching it earlier would have been one focused 5-minute pass after M4 Chunk B2 shipped. Logged as a reminder for future visual-smoke checklists.
