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

## Pages

### Clients page — list view

Sortable table, one row per client. Default sort: by health score ascending (worst first) once Gregory exists; by `last_call_date` descending for V1.

Columns:

| Column | Source | Notes |
|--------|--------|-------|
| Full name | `clients.full_name` | Click → detail view |
| Status | `clients.status` | Color pill (active / paused / ghost / churned) |
| Journey stage | `clients.journey_stage` | onboarding / active / churning / churned / alumni |
| Primary CSM | `client_team_assignments` where role='primary_csm' | Latest active assignment |
| Health score | `client_health_scores` (latest) | Numeric + tier pill; empty for V1 |
| Last call | `max(calls.started_at)` where `primary_client_id = client.id` | Days-ago format with color coding |
| Open action items | count of `call_action_items` where `owner_client_id = client.id` and `status='open'` | "3 open (1 overdue)" if any past due_date |
| Tags | `clients.tags` | Chip display |

Search: filter on name + email. Filter chips: status, journey stage, primary CSM, "has open action items".

### Clients page — detail view

Vertical layout, sectioned. Inline-save-on-blur for all fields except Primary CSM (which has its own commit semantics — see below).

**Section 1 — Identity (editable):** full_name, email, phone, timezone. slack_user_id read-only.

**Section 2 — Status (editable):** status (dropdown), journey_stage (dropdown), program_type, start_date, tags (chip input).

**Section 3 — Primary CSM (editable):** Single dropdown of team_members. Changing the value does NOT update-in-place — it sets the existing assignment's `unassigned_at = now()` and inserts a new `client_team_assignments` row with `role = 'primary_csm'` and the new team member. Preserves history. Schema flexibility for multi-CSM preserved for V1.1.

**Section 4 — Indicators (Gregory's surface):**

Four indicators rendered top-to-bottom:

1. **Health score** — numeric 0-100 + tier pill (green/yellow/red). "Last computed" timestamp. Click → expandable "why" panel rendering `client_health_scores.factors`. V1 empty state: "No score yet — Gregory will populate this in V1.1."

2. **Call cadence** — "Last call: N days ago" with color coding (green <14 days, yellow 14-30, red >30). V1 live; pure SQL.

3. **Concerns** — bulleted list of qualitative watchpoints from `client_health_scores.factors.concerns[]`. Each concern has text, severity (low/medium/high color-coded), and source_call_ids that link to the calls. V1 empty state: "No concerns surfaced — Gregory will populate this in V1.1."

4. **NPS** — most recent `nps_submissions.score` + days ago. V1 empty state: "No NPS data yet."

**Section 5 — Recent calls (read-only):** Last 5 calls with date, title, category, duration. Click → Calls detail page.

**Section 6 — Open action items (read-only for V1):** List from `call_action_items` where `owner_client_id = client.id` and `status='open'`. Owner, description, due_date, source call. *Note:* this section is the canonical action-items view; it is not duplicated as a top-of-page indicator.

**Section 7 — Notes (editable):** Free-text markdown field. Persists to new column `clients.notes` (migration 0012).

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

- **TypeScript-native via Postgres function, not a Vercel Python function.** The deferred spec called for `api/merge_clients.py` wrapping the existing `scripts/merge_client_duplicates.py`. Replaced with: (a) plpgsql function `merge_clients` in migration 0015 carrying the full merge body atomically, (b) TypeScript Server Action calling the RPC. Reasoning: the Python wrapper would have introduced an HTTP hop with no per-request transactionality (the script's 5 steps are sequential `UPDATE`s, partial-failure recovery is difficult), while the plpgsql function is single-transaction and matches the existing `change_primary_csm` pattern from M2.3b. The Python script stays untouched as historical record of the four pilot pairs already merged.
- **Pulled forward in session ordering.** Originally slotted as M2.3c, deferred until after M3.3 Calls. M3.2 swapped this in (after the M3.1 smoke test) to clear the `needs_review` queue before Calls work begins.
- **No recovery runbook written.** The non-transactional-merge concern that motivated a runbook in option (a) is moot because the function is single-transaction by construction — partial failures roll back.
- **No SQL tests added.** The repo has no plpgsql test pattern today (Python tests live alongside Python code; the dashboard layer has no tests yet). Verification path: end-to-end test against a real source/target pair from the cloud `needs_review` queue, picked by Drake before deploy. The existing Python tests for `scripts/merge_client_duplicates.py` stay as-is — they test the reference implementation, which is unchanged.
