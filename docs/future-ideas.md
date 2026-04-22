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
- **Does double duty for both deferrals.** The webhook payload carries the call summary and the action items alongside the transcript, so the same path that adds real-time ingestion will also populate `call_action_items` and `documents` rows with `document_type='call_summary'` — the two omissions the TXT backlog pipeline leaves empty today. See `docs/ingestion/metadata-conventions.md` §5 Deferrals.
- **Why deferred:** backlog pipeline must prove correct on 389 real calls first. Debugging pipeline logic on a static corpus is dramatically easier than on a live stream — same classifier, same chunker, same DB writes, but with a known input set and time to inspect every output.
- **Revisit trigger:** backlog ingest has been stable for 1+ week AND Ella V1 has been in beta with acceptable retrieval quality for at least several days.
- **Logged:** 2026-04-21.

## LLM-based call summary generation (fallback to Fathom webhook)

- **What:** a Claude call per stored transcript that produces a clean summary, written into `documents` with `document_type='call_summary'` and metadata per conventions §2. Back-fills summaries for the backlog calls the TXT pipeline couldn't populate.
- **Why deferred:** costs ~$5–10 one-time across the backlog, runs in a few minutes, but requires an eval harness for summary quality — and that harness doesn't exist yet. The preferred path is the Fathom webhook above, which gets summaries "free" from Fathom's own post-processing. LLM generation is the fallback if the webhook path stalls.
- **Revisit trigger:** Ella V1 in beta with reviewer bandwidth available to validate summaries, OR Fathom webhook integration stalls for 2+ weeks.
- **Logged:** 2026-04-22.

## LLM-based action item extraction (fallback to Fathom webhook)

- **What:** Claude pass over stored transcripts that extracts action items into `call_action_items`, one row per item with `owner_type`, description, due_date inferred when present. Back-fills the table the TXT pipeline couldn't populate.
- **Why deferred:** Similar cost profile to LLM summaries (~$8–20 to backfill 389 calls) and requires an extraction-quality eval that we don't have. Cross-reference: see the LLM-summary entry above for the same pattern. Preferred path is the Fathom webhook, which delivers action items alongside summaries. LLM extraction is the fallback.
- **Revisit trigger:** Ella V1 in beta + reviewer bandwidth available to validate extractions, OR Fathom webhook integration stalls.
- **Logged:** 2026-04-22.

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

## match_document_chunks: enforce calls retrievability via SQL join

- **What:** migration `0011` extending `match_document_chunks` to join `calls` on `documents.metadata->>'call_id'` and filter on `calls.is_retrievable_by_client_agents` for client-scoped document types. Moves the invariant from the pipeline (where it lives today — `documents.is_active` is set from the computed retrievability at write time) down to the function layer.
- **Why deferred:** today's pipeline fix (option a) already enforces the invariant at write time, which is sufficient for the V1 backlog ingest. The function-side version is more principled (invariants at the lowest layer, same pattern as migration 0010) but adds a join on every retrieval call and requires careful handling of `metadata->>'call_id'` type coercion. Worth doing when we want defense-in-depth or when the write-side enforcement gets a real counter-example.
- **Revisit trigger:** someone manually flips `calls.is_retrievable_by_client_agents` and forgets to sync `documents.is_active` (production bug), OR a planned durability pass after Ella V1 beta validates the retrieval latency budget for the extra join.
- **Logged:** 2026-04-22.

## Atomic per-call ingest via Postgres RPC

- **What:** replace the non-atomic supabase-py writes in `ingestion/fathom/pipeline.py` with a PL/pgSQL `ingest_fathom_call(...)` function taking call fields + participants + chunks (with embeddings) as JSON and doing every insert/update in one `BEGIN/COMMIT`. Python computes embeddings, hands one RPC call the full payload, gets back row counts.
- **Why deferred:** V1 ingest is a batch job; re-runs are cheap; existing upsert shapes already converge to correct state on partial failure. The RPC would add ~150 lines of PL/pgSQL that's harder to test and evolve than Python.
- **Revisit trigger:** first time partial-failure recovery becomes a real operational problem, OR the first non-batch ingest path (Fathom webhook) where re-run isn't free.
- **Logged:** 2026-04-22.

## Partial-unique constraint on client_team_assignments

- **What:** replace `UNIQUE (client_id, team_member_id, role)` on `client_team_assignments` with a partial unique index `WHERE unassigned_at IS NULL`. Matches the pattern from migration `0007_partial_unique_archival.sql`. Today an ended assignment blocks re-assigning the same person to the same client in the same role.
- **Why deferred:** nobody has been reassigned yet, so the latent bug hasn't fired.
- **Revisit trigger:** first reassignment attempt that hits the constraint, OR as a small migration in the next maintenance pass — whichever comes first.
- **Logged:** 2026-04-22.

## RLS policies for browser-direct reads

- **What:** write `CREATE POLICY` statements for tables the Next.js frontend reads directly with `anon` or authenticated user keys. Every table currently has RLS enabled with zero policies, so deny-default takes over and any non-service-role query returns empty.
- **Why deferred:** V1 is service-role-only from the agent layer. The browser reads through the agent API, not directly against Supabase.
- **Revisit trigger:** first browser-direct-to-Supabase read, OR before any Next.js dashboard component reads from the DB without going through a backend agent endpoint.
- **Logged:** 2026-04-22.

## Drop denormalized call_category from documents.metadata

- **What:** remove `call_category` from the metadata blob the Fathom pipeline writes to `documents`. It's denormalized from `calls.call_category` for "filter-side speed" but isn't used as a filter in `match_document_chunks`. Removing it means re-classification on the `calls` table can't drift from the documents copy.
- **Why deferred:** small cleanup, not blocking. The denormalized value is harmless until it drifts.
- **Revisit trigger:** tomorrow or this week; dedicated 30-minute PR.
- **Logged:** 2026-04-22.

## call_action_items CHECK constraint for owner_type / owner_*_id consistency

- **What:** add a CHECK that enforces: `owner_type='client' → owner_client_id is not null AND owner_team_member_id is null`; `owner_type='team_member'` → the mirror case; `owner_type='unknown' → both nullable`. Prevents inconsistent rows at the DB layer.
- **Why deferred:** every row populated by today's pipeline has `owner_type='unknown'` (TXT backlog doesn't carry action items — see conventions §5 Deferrals). The constraint has nothing to catch yet.
- **Revisit trigger:** when `call_action_items` starts getting populated — either via the Fathom webhook or the LLM-extraction fallback path.
- **Logged:** 2026-04-22.

## Status-vocabulary CHECK constraints

- **What:** replace free-text `status` / `category` / `severity` / etc. columns with CHECK constraints enforcing the documented vocabularies. Catches typos at write time. Affects `clients.status`, `clients.journey_stage`, `calls.call_category`, `escalations.status`, `alerts.severity`, and a few others.
- **Why deferred:** vocabularies are still settling. `clients.journey_stage` in particular will evolve once CSM Co-Pilot starts deriving it.
- **Revisit trigger:** vocabularies stable for 2+ weeks of Ella V1 beta usage.
- **Logged:** 2026-04-22.

## Auto-created client review workflow

- **What:** a short runbook + weekly canned query for clients with `tags @> array['needs_review']` AND `metadata->>'auto_created_from_call_ingestion' = 'true'`. Reviewer either confirms (clear the `needs_review` tag) or merges (find duplicate, archive the auto-created row).
- **Why deferred:** zero auto-created clients yet; the workflow only matters once they exist.
- **Revisit trigger:** first auto-create from the Fathom backlog ingest, OR a count of `needs_review` clients that exceeds 5.
- **Logged:** 2026-04-22.
