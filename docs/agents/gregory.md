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

`dashboard/` at repo root.

```
ai-enablement/
├── api/                     # existing Python serverless functions
├── ingestion/               # existing
├── shared/                  # existing
├── supabase/                # existing
├── dashboard/               # NEW
│   ├── package.json
│   ├── next.config.js
│   ├── app/                 # Next.js 14 app router
│   ├── components/
│   └── lib/
├── pyproject.toml           # existing
├── vercel.json              # MODIFIED — see below
└── CLAUDE.md
```

### Vercel config gotcha

Current `vercel.json` declares Python serverless functions. Adding Next.js means Vercel needs to know which framework owns which path.

Approach: scope existing Python functions explicitly to `/api/*` paths in `vercel.json`. Let Next.js claim everything else. Single Vercel project; same deploy.

This is a hard-stop checkpoint in the M2.3 build prompt — Code must not modify `vercel.json` without showing the diff first.

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
- All Supabase access goes through a thin data layer (`dashboard/lib/db/`) so swapping Supabase for another backend is contained.
- Page components are thin clients on the data layer; no business logic in pages.
