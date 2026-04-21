# Future Ideas

Lightweight log for ideas we've considered but haven't built. If it resolves into a real architectural commitment, promote it to an ADR under `docs/decisions/`. If it quietly goes away, delete the entry.

**Entry format.** Short. Four lines:

- **What:** one-sentence description.
- **Why deferred:** what made this not-now.
- **Revisit trigger:** the concrete event that should pull it back onto the table.
- **Logged:** date.

---

## Coaching moments / playbook document type

- **What:** a new `document_type = 'coaching_moment'` (or `'playbook'`) for curated cross-client insights distilled from call summaries — high-signal patterns, scripts, objection handlers — promoted to globally retrievable documents so Ella can surface them to any client who asks.
- **Why deferred:** we need meaningful call volume before the mining is worth doing. Raw calls stay client-scoped by design; the value here is deliberate curation on top, not automatic cross-client leakage.
- **Revisit trigger:** week 6–8 of Ella in production, once there's enough call history that a reviewer can spot recurring themes worth promoting.
- **Logged:** 2026-04-20.

## Explicit metadata conventions for documents and chunks

- **What:** a pinned list of the `metadata` jsonb fields we'll capture at ingestion time for each `document.source` — keyed fields (e.g. `drive_url`, `author`, `module`, `section`, `client_id` for call summaries) versus what stays in a general bag. Chunk-level metadata rules too.
- **Why deferred:** doing this on the fly means re-ingesting docs when conventions shift. Doing it once, up front, saves that pain.
- **Revisit trigger:** before the first Drive ingestion run. Must be resolved before any production ingestion touches `documents`.
- **Logged:** 2026-04-20.

## Re-ranking and hybrid search (BM25 / RRF)

- **What:** layer BM25 (or equivalent keyword search) on top of the current pure-vector retrieval in `match_document_chunks`, combined via Reciprocal Rank Fusion. Improves recall when a query's keyword match is obvious but meaning-match misses it (proper nouns, exact module names, rare jargon).
- **Why deferred:** current retrieval is simple, debuggable, and sufficient for V1. Adding BM25 now trades complexity for speculative gains. V1 beta will surface where pure vector actually falls down.
- **Revisit trigger:** Ella V1 beta shows a clear pattern of retrieval misses that keyword match would have caught — review after the first ~50 production queries and the first 10 `agent_feedback` corrections.
- **Logged:** 2026-04-20.

## Internal assistant agent ("Scout" working name)

- **What:** a second agent configuration of the same shared layer that powers Ella, but with team-wide access — internal call recordings, cross-client call history, team-only documents. Runs in team Slack channels, not client channels. Use cases: team-meeting recall, cross-client pattern detection, institutional memory queries ("what did we decide about X in the Monday sync two weeks ago?").
- **Why deferred:** client-facing Ella V1 is the business priority. The shared layer needs to prove out on the lower-risk client surface before we expose it on the higher-risk internal surface. Internal Scout has broader data access; confidently wrong answers have larger blast radius (strategy, personnel, unfinished decisions).
- **Revisit trigger:** Ella V1 has been in client beta for 2+ weeks with acceptable retrieval and escalation metrics. Internal Scout is likely ~1 focused week of work from there — same agent skeleton, different retrieval filters, different Slack surface.
- **Logged:** 2026-04-21.

## Fathom webhook integration (real-time call ingestion)

- **What:** HTTP endpoint that receives Fathom webhooks when a call finishes processing, parses the JSON payload into a `FathomCallRecord`, and runs the existing ingestion pipeline. Replaces manual zip-export backlog re-imports for ongoing calls. Reuses `classifier.py`, `chunker.py`, and `pipeline.py` verbatim — only adds the endpoint, Fathom signature verification, and a thin JSON adapter at `ingestion/fathom/webhook.py`.
- **Why deferred:** backlog pipeline must prove correct on 389 real calls first. Debugging pipeline logic on a static corpus is dramatically easier than on a live stream — same classifier, same chunker, same DB writes, but with a known input set and time to inspect every output.
- **Revisit trigger:** backlog ingest has been stable for 1+ week AND Ella V1 has been in beta with acceptable retrieval quality for at least several days.
- **Logged:** 2026-04-21.

## scripts/churn_client.py atomic churn helper

- **What:** a small CLI — `python scripts/churn_client.py --email ... --reason ...` — that atomically sets `status = 'churned'` AND `archived_at = now()` on a `clients` row, cascades `slack_channels.is_archived = true` and `client_team_assignments.unassigned_at = now()`, and writes the supplied `reason` into `clients.metadata.churn_reason` along with `churned_at` and `churned_by`. The canonical "archive a client" action when the churn doesn't flow through a sheet re-export (mid-cycle, one-off).
- **Why deferred:** the Active++ re-export workflow handles bulk churn correctly today — the owner removes a client from their working view, the next `seed_clients.py --apply` detects the absence and archives them via the cascade. A dedicated CLI becomes worth building when a human needs to archive a client between exports and wants a single atomic action instead of editing the sheet or composing Studio SQL by hand (easy to forget one of the two fields and leave the DB in an inconsistent state).
- **Revisit trigger:** first time someone wants to churn a client without touching the sheet, OR a single inconsistent-state bug lands because someone forgot to update `archived_at` when updating `status`.
- **Logged:** 2026-04-21.

## scripts/add_client.py one-off client CLI

- **What:** a small CLI — `python scripts/add_client.py --email ... --name ... --start-date ... [--owner ... --slack-channel-id ...]` — for adding a single client between Financial Master Sheet re-exports. Upserts a `clients` row and optionally the matching `slack_channels` + `client_team_assignments` rows, using the same transforms `seed_clients.py` uses so behavior stays consistent.
- **Why deferred:** the current workflow (team adds the client to the Master Sheet, someone re-runs `seed_clients.py`) works and keeps the sheet as the source of truth. A dedicated CLI is convenience, not correctness. Worth the build once the sheet-as-source-of-truth assumption breaks.
- **Revisit trigger:** sheet re-exports start happening more than ~once a week, OR the team wants to add clients faster than a sheet round-trip allows, OR the sheet stops being the canonical list and is replaced by something real-time.
- **Logged:** 2026-04-21.

## Automated cloud seed application

- **What:** a small wrapper (likely `scripts/apply_seeds_to_cloud.py`) that reads every file in `supabase/seed/*.sql` and pushes it against a linked cloud Postgres via the standard connection string — so seeding cloud stops meaning "paste into Studio SQL editor." `supabase db push` covers migrations only; this gap is a Supabase CLI limitation, not ours.
- **Why deferred:** cloud applies are rare (~one per major seed change), the seed file set is small today (`team_members.sql`, soon `clients.sql`), and Supabase may fix the CLI gap upstream. Writing a wrapper now risks throwaway work.
- **Revisit trigger:** ≥5 seed files, OR seeding cloud becomes more than a once-a-month task, OR Supabase CLI still doesn't support seed-to-cloud by the time we spin up a second B2B deployment.
- **Logged:** 2026-04-21.

## Topic-based chunking for call transcripts

- **What:** chunk transcripts on semantic topic boundaries (detected via a small LLM call per transcript) instead of fixed word windows. More expensive per ingest, potentially better retrieval relevance because chunks align to "what the call was about at this moment" rather than to arbitrary word counts.
- **Why deferred:** requires an extra LLM call per call during ingestion. The current word-window-with-speaker-boundary approach (see `docs/ingestion/metadata-conventions.md` §3) is sufficient for V1 and lets us see real retrieval failures before spending the complexity.
- **Revisit trigger:** Ella V1 beta shows retrieval misses that a topic-aligned chunk would have caught — e.g. a query lands on a half-chunk mid-topic because the word boundary cut through a discussion.
- **Logged:** 2026-04-21.
