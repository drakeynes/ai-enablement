# Future Ideas

Lightweight log for ideas we've considered but haven't built. If it resolves into a real architectural commitment, promote it to an ADR under `docs/decisions/`. If it quietly goes away, delete the entry.

**Entry format.** Short. Four lines:

- **What:** one-sentence description.
- **Why deferred:** what made this not-now.
- **Revisit trigger:** the concrete event that should pull it back onto the table.
- **Logged:** date.

---

## Path 2 outbound writeback architecture

- **What:** Gregory writes back to upstream sources (Airtable, future master-sheet replacement) when CSM-driven dashboard edits should propagate. Today's M5.4 Path 1 is one-way (Airtable → Gregory). Path 2 is the inverse: dashboard edits → Make.com webhook → Airtable mutation. Post-M5.6 the columns Path 2 needs to listen on exist: `clients.accountability_enabled` and `clients.nps_enabled` (added in 0022). Both the cascade trigger and CSM manual flips land in the same `UPDATE clients`, so a single Supabase Database Webhook on UPDATE of these columns (or a parallel `clients_path2_writeback_after` trigger that POSTs to Make.com) fires correctly for both code paths — the receiver doesn't need to distinguish "cascade-fired" from "CSM-manual." Architecture narrows from "design the column set + trigger + webhook" to "wire Make.com onto an UPDATE-trigger we can build in ~50 lines."
- **Why deferred:** waiting on Make.com walkthrough with Zain (target Monday 2026-05-04) to scope the Airtable side (which Airtable fields each Gregory column maps to, write semantics, conflict resolution if both sides edit the same field within a window, idempotency token shape — likely a `webhook_deliveries.webhook_id` mirror).
- **Revisit trigger:** Make.com walkthrough complete + scope decision on which fields are write-back-eligible. Initial scope likely the M5.6 toggles; status / csm_standing / trustpilot follow if Scott wants the Airtable side to mirror Gregory beyond the toggles.
- **Logged:** 2026-05-03. Updated 2026-05-04 (M5.6 narrowed the architecture — columns exist, listen-on-UPDATE pattern unchanged).

## Filter framework extensibility for Scott Chasing column

- **What:** the M5.5 filtering UI shipped 2026-05-03 with 5 active multi-select dropdowns + 1 single-value toggle + 3 disabled placeholders (Accountability, NPS toggle, Country). When the M5 status cascade chunk adds a "Scott Chasing" column (or whatever boolean/state field comes out of that work), the framework already exists: `MultiSelectDropdown` (`app/(authenticated)/clients/multi-select-dropdown.tsx`) is reusable, the URL-state pattern (parse → array → `.in()` filter) is established in `lib/db/clients.ts`, and the vocab module (`lib/client-vocab.ts`) is the single source of truth to extend. Adding a new filter is roughly: add a `*_OPTIONS` const to the vocab module; add a field to `ClientsListFilters`; add a `.in()` branch to `getClientsList`; add a `<MultiSelectDropdown>` instance to the filter bar; parse the URL param in `readFilters`. ~30-line vertical slice per new column.
- **Why deferred:** depends on what the status cascade chunk actually defines — column type, vocabulary, default state, whether one of the three disabled placeholders ("Accountability") collapses into the Scott Chasing role.
- **Revisit trigger:** M5 status cascade chunk lands AND Scott Chasing column has a defined shape. The "Accountability" placeholder may absorb this filter outright depending on how the cascade scopes ownership of the boolean.
- **Logged:** 2026-05-03 (deferred). Updated 2026-05-03 (M5.5 — framework now real, revisit trigger unchanged but cost-to-extend shrank from "design and build" to "wire up").

## Auto-derive eligibility rule revisit (master-sheet-seed treatment)

- **What:** the M5.4 override-sticky rule treats master-sheet-seeded `csm_standing` rows (`changed_by=NULL` from M4 Chunk C) as ineligible for auto-derive. Concrete impact: 137 active clients' csm_standing is sticky against Airtable NPS segment changes. If Scott wants NPS-driven updates to flow through, the rule needs amending — either retroactively reattributing master-sheet-seed history rows to Gregory Bot, OR loosening the rule to "changed_by IS NULL OR Gregory Bot UUID."
- **Why deferred:** product/CSM decision, not a code question. Scott's Monday onboarding will surface whether he wants the seed locked or eligible.
- **Revisit trigger:** Monday onboarding answers the question. Either (a) one-shot script to update existing history rows + amend the RPC; (b) document the seed-locked semantics explicitly in gregory.md.
- **Logged:** 2026-05-03 (M5.4 surfaced the structural implication; see paired followup entry).

## NPS score piping (V1.5)

- **What:** ingest the NPS score (0-10) alongside the segment classification. Path 1 receiver only handles segment; the score field on `nps_submissions` stays empty for clients who submit through Airtable (the manual NpsEntryForm in Section 2 is the only score-write path today). Score piping would extend the receiver's payload contract to include `score`, validate, write to `nps_submissions` via `insert_nps_submission` RPC alongside the `update_client_from_nps_segment` call.
- **Why deferred:** Path 1 segment-only is sufficient for Scott's Monday onboarding. Score adds complexity (two writes per webhook, idempotency on duplicate score submissions, Airtable Score field shape questions).
- **Revisit trigger:** Path 1 stable for 2+ weeks AND Scott asks for score-driven views (e.g. "show me clients whose NPS score dropped this month") OR a reporting need surfaces the gap.
- **Logged:** 2026-05-03.

## Inactivity flag (end-of-week-2 monthly meeting count)

- **What:** automated flag on `clients` (or computed in a view) for clients who haven't met with their CSM in N days, where N is configurable per Scott's expectations. Likely tied to Scott's Loom 2 walkthrough of his weekly monitoring habits. Implementation could be a derived column, a scheduled cron, or a dashboard filter computed at query time — depends on whether the flag needs to drive notifications or just display.
- **Why deferred:** scope unclear until Scott's Loom 2 lands. The "monthly meeting count at end-of-week-2" framing suggests a specific cadence rule that needs clarification.
- **Revisit trigger:** Scott's Loom 2 walkthrough OR first time CSM asks "show me clients who haven't met in N days."
- **Logged:** 2026-05-03.

## CSM-edit lockdown (per Scott's Loom 1)

- **What:** restrict who can edit certain client fields. Likely some fields (e.g. financials, contract terms) shouldn't be CSM-editable; others (NPS standing, csm_standing) are CSM territory. Implementation could be RLS policies, application-layer field allowlists per role, or both.
- **Why deferred:** CSM team is currently 4 people who all have full edit access, and no visible incident from over-permissive editing. Scott's Loom 1 walkthrough will define the boundaries.
- **Revisit trigger:** CSM team grows past current 4 OR a non-CSM team member modifies a client incorrectly OR Scott explicitly defines boundaries in Loom 1.
- **Logged:** 2026-05-03.

## Trustpilot auto-correct on standing change (per Scott's Loom 2)

- **What:** when `csm_standing` transitions in certain directions (e.g. happy → at_risk), auto-flip `trustpilot_status` to a corresponding state (e.g. clear `'asked'` back to `'ask'` because asking again would be premature on an at-risk client). Concrete rule pending Scott's Loom 2.
- **Why deferred:** rule definition pending; needs Loom 2 to define which transitions trigger which trustpilot_status changes.
- **Revisit trigger:** M5 status cascade chunk lands (which provides the infrastructure for cross-field reactive updates) AND Scott's Loom 2 defines the rule.
- **Logged:** 2026-05-03.

## Australia / US country tagging

- **What:** the master sheet importer captured country (`USA` / `AUS`) into `clients.country` and `clients.metadata.country`, but it's underused in V1 — no filter, no display segmentation. As Scott or Lou starts working specific markets differently, country becomes a meaningful filter dimension.
- **Why deferred:** column exists, value is populated, but no current consumer surfaces it.
- **Revisit trigger:** filter requires country segmentation (likely after M5.5 lands and Scott uses it daily) OR Aus market expansion materializes (separate cohort, separate workflows).
- **Logged:** 2026-05-03.

## Ella V2 — conversational behavior

Four upgrades to how Ella handles Slack conversation flow, all surfaced during pilot testing 2026-04-27. None are bugs in V1 scope; all are "she's correct but feels stiff." Grouped here so they get picked up together, since each one's testing surface (the `#ella-test-drakeonly` channel + the pilot 7) is the same — easier to validate as a batch than one at a time.

**Common revisit trigger for all four: after CSM Co-Pilot V1 ships.** CSM Co-Pilot is the next agent build and the higher business priority. Ella's V2 polish waits for that to land so we don't fragment focus.

### V2.1 — Reply outside thread when contextually appropriate

- **What:** today Ella always replies in-thread via `thread_ts` (set in `agents/ella/slack_handler.py` to the original mention's `ts` or thread root). Want her to sometimes reply in the main channel instead — quick acknowledgments ("got it, looking now") in channel; longer / multi-paragraph responses in thread. Today's threading is correct-but-stiff: a "yes" answer in a thread feels weirdly formal.
- **Why deferred:** the rule for in-channel-vs-in-thread isn't crisp. Picking wrong is worse than always-thread. Needs either a heuristic (response length? whether the question itself was threaded?) or a content classification step. Both are V2 territory.
- **Why this matters:** pilot clients are getting tone-perfect content from Ella but the conversational shape feels like a chatbot. Mixing channel + thread replies based on context is what a human teammate does.
- **Revisit trigger:** after CSM Co-Pilot V1 ships.
- **Logged:** 2026-04-27 (M1.3 testing in `#ella-test-drakeonly`).

### V2.2 — Read prior thread context when @-mentioned mid-thread

- **What:** when Ella is @-mentioned inside an existing Slack thread (not at thread root), she only sees the mentioning message — the thread's prior turns are invisible to her. The agent should fetch the full thread history via Slack's `conversations.replies` API, format the turns into the existing `thread_history` plumbing in `agents/ella/prompts.py:_render_context_section` (which already accepts a `thread_history` arg, currently unused), and include it in the system prompt so she has conversational context.
- **Why deferred:** requires a Slack API call (`conversations.replies` with `channel` + `ts`) on every mid-thread mention, plus token-budget management for long threads. Scope-wise it's ~50 lines but it's surface area we don't need for the V1 pilot use case (most pilot mentions are at thread root).
- **Why this matters:** as pilot adoption grows, threaded back-and-forth conversations will become normal. Today, asking Ella "and what about Y?" in a thread where she just answered about X gets a confused response because she doesn't see the X exchange.
- **Revisit trigger:** after CSM Co-Pilot V1 ships, OR a pilot client visibly hits the "Ella forgot the thread" failure mode.
- **Logged:** 2026-04-27 (M1.3 testing).

### V2.3 — Respond to bare @-mentions

- **What:** today, mentioning `@Ella` alone (no follow-up message) produces no reply — the agent extracts an empty string after `_strip_mentions` and presumably the LLM returns nothing useful. Should respond to bare pings with a friendly conversational opener like "Hey, what's up?" or "I'm here — what do you need?" so the interaction doesn't feel dead.
- **Why deferred:** trivial fix (~10 lines: detect empty stripped text in `agents/ella/slack_handler.py`, return a canned warm response without going through the agent). But "trivial" multiplies fast — there's no reason to ship this in isolation when V2.1/V2.2/V2.4 all touch the same module.
- **Why this matters:** a Slack ping with no reply feels broken even when nothing was technically wrong. Pilot clients will mention Ella out of curiosity ("hey @Ella"); a silent response erodes trust.
- **Revisit trigger:** after CSM Co-Pilot V1 ships, batched with the rest of V2.x.
- **Logged:** 2026-04-27 (M1.3 testing).

### V2.4 — Speaker identification beyond the channel's mapped client

- **What:** Ella currently treats every speaker in a pilot channel as the channel's mapped client. In `#ella-test-drakeonly` (mapped to Javi Pena per the test fixture), she addresses Drake as "Javi" because the channel→client resolution defaults to the channel's mapped row. In real client channels with multiple participants (Scott + the client + maybe a partner or assistant), she'd mis-attribute every non-client message as the client. The fix: resolve each Slack message's `user` field to the right `clients` or `team_members` row via `slack_user_id`, and pass that resolved identity into the prompt's "who is asking right now" section.
- **Why deferred:** plumbing change across `slack_handler.py` (asker resolution lookup), `agent.py` (asker context passed through), `prompts.py` (new section for the asker if they're not the channel's mapped client). Not hard but touches multiple files and has prompt-engineering implications (how does Ella address a non-client speaker in a client channel? "Scott, I see Javi is asking..."?). V2 scope.
- **Why this matters:** as soon as a pilot channel has more than one human participant, mis-attribution is visible and weird. Today this doesn't happen because most pilot mentions come from the mapped client themselves. The day Scott jumps into a pilot channel to clarify something and Ella calls him "Javi," credibility takes a hit.
- **Revisit trigger:** after CSM Co-Pilot V1 ships, OR first time a non-mapped-client human messages Ella in a pilot channel and the mis-attribution is visible.
- **Logged:** 2026-04-27 (M1.3 testing — observed Drake being addressed as "Javi").

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

## LLM-based call summary generation — RESOLVED 2026-04-24 via F2.3 (webhook path)

- **Status:** superseded. F2.3 (2026-04-24) implemented `_ensure_summary_document` in `ingestion/fathom/pipeline.py`, which writes a `documents` row with `document_type='call_summary'` + one embedded chunk whenever a `FathomCallRecord` has `summary_text` populated. The webhook adapter in `ingestion/fathom/webhook_adapter.py` extracts that from Fathom's `default_summary` field. No LLM generation needed — Fathom's own post-processing provides the summary, we just ingest it. The migration-0011 widened unique (`source, external_id, document_type`) allows call_summary and call_transcript_chunk to coexist for the same recording.
- **Backlog back-fill** (the original motivation for the LLM-based fallback) is NOT addressed by this — the TXT backlog has no summaries, so the 388 backlog transcripts stay without summary docs until either (a) a future re-export includes summaries, (b) the Fathom API's `GET /recordings/{id}/summary` endpoint is called per backlog call (cheap, ~$0 cost per call, only needs rate-limit awareness), or (c) LLM fallback is actually built. Option (b) is likely cheaper and faster than (c); worth considering as a one-off backfill script if retrieval demands it.
- **Logged:** 2026-04-22 (original deferral); **resolved for new calls:** 2026-04-24 (F2.3). Backlog-backfill subtask remains open; re-log as a new entry if it becomes needed.

## LLM-based action item extraction — RESOLVED 2026-04-24 via F2.3 (webhook path)

- **Status:** superseded. F2.3 implemented `_upsert_action_items` in `ingestion/fathom/pipeline.py` which delete-replaces `call_action_items` rows for a call whenever a `FathomCallRecord` has `action_items` populated. The webhook adapter converts Fathom's `action_items[]` to our `ActionItem` dataclass, and the pipeline resolves each item's assignee via `ClientResolver`/`TeamMemberResolver` for `owner_type` + `owner_client_id` / `owner_team_member_id`. No LLM extraction needed — Fathom's own AI surfaces action items, we ingest them directly.
- **Backlog back-fill** is NOT addressed — same reasoning as the summary deferral above: TXT backlog has no action items, so the 388 backlog transcripts stay with 0 rows in `call_action_items` until a new export includes them, the Fathom API is called per call, or LLM extraction is actually built. Priority for backfill is low — action items are most useful on recent calls for accountability tracking, not historical ones.
- **Logged:** 2026-04-22 (original deferral); **resolved for new calls:** 2026-04-24 (F2.3). Backlog-backfill subtask remains open.

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

## Filler filter — collapse adjacent short utterances by the same speaker

- **What:** extend `ingestion/fathom/chunker.py`'s filler filter to also collapse adjacent short utterances from the same speaker within a 1–2 second window. Current filter catches isolated short fillers but lets orphan fragments through when they're their own utterance. Observed in the backlog: `Owen Nordberg [00:02:06]: And.` immediately before the substantive `"He wants just a way..."`; `Rifat Chowdhury [00:01:59]: But I. / I. / I started it...` — three utterances in the same second that should merge into the next one.
- **Why deferred:** retrieval quality is unaffected — embeddings capture semantic meaning, not orphan conjunctions. The fix is a small chunker change but benefits from real-data tuning (threshold: same-speaker + <N-second gap + short text) which is easier once CSM QA starts surfacing read-quality complaints.
- **Revisit trigger:** first time a CSM in QA says "Ella retrieved the right chunk but the content reads janky," OR a systematic read of ~20 chunks spots the pattern >20% of the time.
- **Logged:** 2026-04-22.

## Chunker overlap calibration

- **What:** tighten the ~50-word overlap spec in `ingestion/fathom/chunker.py` §3. Observed overlap on sampled backlog calls is 70–90 words because the speaker-boundary alignment rolls back to include the full preceding utterance, even when that utterance is long. Not breaking, just more retrieval redundancy than intended.
- **Why deferred:** redundancy helps retrieval hit-rate at chunk boundaries and costs nothing on storage at current scale (3528 chunks total). The spec is an aspirational target, not a hard constraint. Fixing means adding a word-count cap on the overlap reach — easy change, low value right now.
- **Revisit trigger:** Ella's retrieval feels like it's surfacing "the same content twice" across adjacent chunks in sampled results, OR storage cost becomes a real line item (not at V1 scale, maybe at 100K+ chunks).
- **Logged:** 2026-04-22.

## Cool-down-on-correction for Ella

- **What:** when Ella receives a `thumbs_down` or `correction` feedback in a channel within the last 24 hours, lower her confidence threshold in that channel so she escalates more eagerly rather than confidently repeat a just-corrected mistake.
- **Why deferred:** V1 optimizes for shipping speed. Correction feedback volume in the first week of client beta is too low for this logic to matter, and the downside (a CSM correcting a confident answer) is the same with or without cool-down for the first handful of corrections.
- **Revisit trigger:** first week of client beta done, first visible correction patterns in `agent_feedback`, OR a specific channel surfaces 2+ corrections in a day.
- **Logged:** 2026-04-22.

## Golden dataset eval harness for Ella

- **What:** curated set of 20+ Q&A pairs covering the four response categories (in-scope, out-of-scope-escalate, out-of-scope-decline, edge/injection). 90% pass rate as the ship gate for future Ella iterations. Replaces "team feel-test" with a reproducible check.
- **Why deferred:** V1 replaces formal eval with live team testing in `#ella-test` over Thursday/Friday for speed. The harness is real work and gets more valuable once we have real-world examples of things Ella got wrong to seed it with.
- **Revisit trigger:** first non-trivial Ella iteration after V1 (prompt changes, retrieval changes, chunking changes), OR first client correction that suggests regression risk from a future change.
- **Logged:** 2026-04-22.

## Per-channel ella_enabled beta gating

- **What:** use the existing `slack_channels.ella_enabled` boolean as the live gate — Ella responds in channels where it's `true`, skips everything else. Controlled per channel via a manual UPDATE or a small admin CLI, no code deploy needed to add or remove a channel.
- **Why deferred:** V1 hardcodes the pilot channel set (7 clients + `#ella-test`) directly in the agent config for speed. `ella_enabled` is already in the schema but the agent doesn't read it yet.
- **Revisit trigger:** first time we need to add or remove a channel without a code deploy — e.g., expanding to a second client cohort, or pulling a specific pilot channel during an incident.
- **Logged:** 2026-04-22.

## Team-test mode flag

- **What:** when a team member (`author_type=team_member`) @mentions Ella, stamp the `agent_runs` row with `trigger_metadata.is_team_test = true` so real-usage analytics can filter out test traffic. Ella still responds normally — the flag is telemetry-only.
- **Why deferred:** V1 has no real-usage metrics to protect yet. Both pilot-client and team-test interactions land in `agent_runs` equivalently for now.
- **Revisit trigger:** when post-launch metrics are being analyzed for the first time and team-generated test traffic in `#ella-test` starts distorting the view.
- **Logged:** 2026-04-22.

## Thumbs-up/down reaction capture

- **What:** Slack reaction-emoji events on Ella's messages feed into `agent_feedback` as `thumbs_up` / `thumbs_down` entries automatically. Requires the Slack Events API subscription (separately deferred — see "Slack real-time ingestion via Events API" below) and a small reaction handler that maps emoji → feedback type → insert.
- **Why deferred:** V1 team testing gets verbal feedback in the test channel directly to Drake/Nabeel. Formal reaction capture becomes valuable post-launch when clients (not team members) are the ones reacting.
- **Revisit trigger:** client beta running AND team wants a passive feedback signal without CSMs having to report issues manually, OR the Slack real-time ingestion pathway ships first and this becomes a cheap bolt-on.
- **Logged:** 2026-04-22.

## Impersonation mode for Ella testing

- **What:** team member can test how Ella would respond as if a specific client were asking — via slash command (`/ella-as <client-email> <question>`) or a message prefix. Drives Ella's retrieval through the target client's scope (their call summaries, their Slack history) so team-test output matches what the real client would see.
- **Why deferred:** V1 testing uses direct @mentions in `#ella-test` by team members. Less realistic than impersonation (the client's specific retrieval context is missing), but faster to stand up and sufficient for "does she embarrass us" sign-off.
- **Revisit trigger:** team wants to simulate specific client scenarios before rolling out significant Ella changes — e.g., testing how a prompt change would affect a known-tricky client's experience.
- **Logged:** 2026-04-22.

## Post-ship quick-fix template if Monday launch slips

- **What:** a prepared short message the team can post in each pilot client channel if Monday's Ella launch slips. Keeps expectations aligned given Scott's announcement already went out to clients. Draft: *"Quick update — we're still putting some finishing touches on Ella. She'll be live in this channel by [day]. Appreciate the patience."* Posted by the client's primary CSM, not Ella (she's not live yet).
- **Why prepared:** the announcement preceded technical readiness. Slippage risk is non-zero given the tight Thu/Fri test window, and silence after a "coming soon" announcement is worse than a "running a bit late" follow-up.
- **Revisit trigger:** if Ella isn't shippable by Sunday evening, use this template Monday morning. Otherwise delete the entry after Monday launch.
- **Logged:** 2026-04-22.

## Drive-sourced content ingestion pipeline

- **What:** `ingestion/drive/` that pulls HTML / Google Doc content from Google Drive via the Drive API with version-awareness — re-ingest triggered on `modifiedTime` change, old versions auto-archived (tags `v1_content` → `is_active=false`, new row carries `v2_content`). Complements the filesystem-based `ingestion/content/` that ships today. When it lands, inspect_ingestion query #7 (distinct tag counts) becomes the active/archived-content surface.
- **Why deferred:** filesystem copy handles V1 — the course content is relatively stable and Nabeel can trigger re-ingest manually after a content pass by dropping fresh HTML exports into `data/course_content/`. Drive API + version-awareness + auth setup is real work; not worth it until content revamp cadence exceeds "once a quarter."
- **Revisit trigger:** content stabilizes and Nabeel wants edits to propagate without manual re-copy, OR a second content source (Notion SOPs, methodology docs) needs ingesting — both get addressed by the same API-aware pipeline shape.
- **Logged:** 2026-04-22.

## Client-facing rollout announcement template for Ella beta

- **What:** standard message posted in each client channel before Ella gets added. Draft: *"You've been selected to take part in the beta of our new AI assistant, Ella. She's a pilot to help you get what you need faster, trained on nearly a million data points from client interactions over the last 12 months. @mention her in this channel anytime for help with course content, methodology, or resources. Your CSM is still your primary contact for anything else."*
- **Why deferred:** Ella V1 rollout concern — message only matters the moment a channel gets `ella_enabled = true`. Template + tone want review by Scott/Lou alongside the system prompt before going live.
- **Revisit trigger:** Ella V1 is deployable and ready for first pilot-client channel.
- **Logged:** 2026-04-22.

## Test-fixture client for team-only Ella test channels — **ACTIVE (next-session priority #2)**

- **Status:** promoted from "deferred idea" to next-session priority on 2026-04-24 after the first live smoke test ran against Javi Pena's channel/context. The workaround is now actively muddying the team's mental model of what a pilot channel is and what a test channel is; formalizing the fixture is the right next step.
- **What:** dedicated synthetic "Test Client" row in `clients` with Drake (or Scott) as primary advisor, plus team-only test channels (`#ella-test-drakeonly`, and a newly-set-up `#ella-test`) mapped to that client's UUID via `slack_channels.client_id`. Alternative shape: a `slack_channels.team_test_channel` boolean that teaches the handler to run without a client mapping at all — pick one, not both. Replaces the current workaround of pointing `#ella-test-drakeonly` at Javi Pena's UUID.
- **Revisit trigger:** done — triggered. Work plan lives in `CLAUDE.md` § Next Session Priorities.
- **Logged:** 2026-04-23. **Activated:** 2026-04-24.

## Slack real-time ingestion via Events API

- **What:** Vercel serverless function receiving Slack Events API `message` subscriptions. Parses via `ingestion/slack/parser.py`, upserts to `slack_messages`. Reuses the parser verbatim; adds signing-secret verification and `event_id` deduplication. Complements the REST-based backfill, which stays the right tool for historical imports.
- **Why deferred:** the 90-day backfill covers tonight's team testing and the early pilot. Real-time ingestion only moves the needle once Slack history is embedded into retrieval (see "Slack messages as a retrieval surface" below) — stale-but-embedded Slack history is less useful than live-but-embedded, so the two entries are best revisited together.
- **Revisit trigger:** the retrieval-surface entry ships, OR Ella starts getting asked about same-day Slack conversations she can't see, OR a second manual backfill run becomes necessary inside a week.
- **Logged:** 2026-04-23.

## Backfill team_members.slack_user_id from ingested messages

- **What:** a sweep that takes every `slack_user_id` in `slack_messages` with `author_type = 'unknown'`, calls Slack's `users.info`, and when the email ends in `@theaipartner.io`, updates the matching `team_members` row with the resolved `slack_user_id`. Makes subsequent ingest runs classify those same authors as `team_member` rather than `unknown`. Also helps future Slack-bot features (@mentioning a team member).
- **Why deferred:** today's seed left `team_members.slack_user_id` null. Resolution lazily via messages costs a `users.info` call per unknown author; we'd rather batch that and run it once after the first backfill surfaces the unknown set.
- **Revisit trigger:** query #11 in `docs/runbooks/inspect_ingestion.md` shows more than ~20 distinct unresolved authors OR the first time a team @mention in a Slack channel needs to resolve to a `team_members.id`.
- **Logged:** 2026-04-22.

## Slack messages as a retrieval surface (V1.1)

- **What:** chunk + embed `slack_messages` text into `document_chunks` under a new `document_type = 'slack_message_chunk'`, metadata-gated per client the same way transcript chunks are. Maximally useful alongside real-time ingestion (see "Slack real-time ingestion via Events API" above), but the backfilled 90-day window alone would already let Ella reference prior in-channel conversations.
- **Why deferred:** V1 ships with course content plus Fathom call summaries as Ella's retrieval surface. Slack history embedding is additive — more ingest tokens, more noise in the retrieval pool — worth doing once live testing shows a concrete gap Ella can't cover from the two existing surfaces.
- **Revisit trigger:** a team-test or client question surfaces that Slack history would have answered AND course content + Fathom calls didn't, OR strong signal on that immediately after Monday's launch.
- **Logged:** 2026-04-23.

## LLM post-processing for Fathom speaker misattribution

- **What:** a Claude pass per transcript to fix obvious speaker misattributions from Fathom's diarization. Observed in the backlog: quotes attributed to the wrong speaker based on conversational flow (e.g., `"you have a tendency to over-engineer"` attributed to the person being described rather than the person doing the describing). This is a Fathom quality ceiling, not a pipeline bug — the TXT export faithfully records what Fathom produced.
- **Three paths** (not mutually exclusive):
  - **(a) Hedge in Ella's system prompt** — ships for free when Ella's prompt is written. Captured below.
  - **(b) LLM post-processing pass over stored transcripts** — ~$5–10 one-time for the 389-call backlog, rewrite `calls.transcript` + chunk content with corrections; requires an eval because "fix based on conversational flow" is LLM judgment that can itself misattribute.
  - **(c) Improve Fathom upstream** — voice profiles, speaker labels in calendar invites, post-meeting tagging by the host. Reduces future drift; doesn't fix the backlog.
- **Why deferred:** path (a) is cheap and sufficient until we have evidence of real client-facing impact. Paths (b) and (c) add real cost and don't solve the backlog-vs-future-calls problem cleanly on their own.
- **Revisit trigger:** first client complaint of "Ella said I said X but I didn't," OR multiple CSM QA flags on misattributed quotes in retrieved chunks.
- **Logged:** 2026-04-22.

## `duration_ms` instrumentation on agent_runs

- **What:** pass `duration_ms` through to `shared.logging.end_agent_run` from every agent. The column exists on `agent_runs`, the helper accepts the kwarg, but no agent currently times the turn — every row written by Ella today has `duration_ms = NULL`. Minimal fix: capture `time.monotonic()` at the top of `respond_to_mention` and pass the delta to `end_agent_run` on every terminal path (success / escalated / error / skipped).
- **Why deferred:** surfaced during the 2026-04-23 local harness run; decided not to block Ella V1 beta on it. Token counts and cost already land on the row via `shared.claude_client.complete()`, which covers the "is she expensive?" question; latency observability is a nice-to-have for perf tuning, not a safety property. Also: the same gap likely exists in whatever agent ships next, so fixing it once globally (e.g., a context manager in `shared/logging.py` that wraps `start_agent_run` / `end_agent_run`) is worth more than a per-agent patch.
- **Revisit trigger:** (1) first time we need to diagnose a perceived-slow Ella response from a real client thread, OR (2) when the eval harness lands and we want per-run latency as a metric, OR (3) CSM Co-Pilot gets built and would benefit from the same instrumentation — whichever lands first.
- **Logged:** 2026-04-23.

## pg_dump local embeddings to cloud to skip re-embedding on large loads

- **What:** for ingestion runs where the chunks + embeddings already exist in the local Supabase, `pg_dump` the `documents` + `document_chunks` rows from local and restore into cloud, instead of re-running the ingestion pipeline against cloud (which re-chunks and re-pays the OpenAI embedding cost). Narrow scope: just rows whose embeddings are stable — typically `course_lesson` and `call_transcript_chunk` where the source hasn't changed.
- **Why deferred:** for the Fathom backlog at ~389 calls / ~3,528 chunks the re-embed is ~$5–15 and ~10–30 min — not painful enough to justify the dump/restore dance, which brings its own risks (row-id collisions, RLS interactions, accidentally copying stale metadata). The cost/complexity crossover point is somewhere north of 10k chunks or a corpus that'd cost >$50 to re-embed.
- **Revisit trigger:** next corpus load that'd cost >$50 to re-embed OR take >1 hour, whichever lands first. Likely candidates: a Drive-sourced content ingestion once we have the full course library (vs. today's curated subset), or a second pass that re-chunks call transcripts with topic-based chunking (see entry above).
- **Logged:** 2026-04-24.

## Ella profile picture + branding

- **What:** upload a custom app icon for Ella in the Slack app console (api.slack.com/apps → your app → Basic Information → App-Level App Icon) so she stops showing up as the default Slack gear avatar in client channels. Branding direction (warm / on-theme-with-TAP / distinctive) is TBD — needs a design pass or a handful of options to choose from.
- **Why deferred:** purely cosmetic; doesn't block any V1 functionality. Real clients will see her as the default avatar in the pilot, which looks unfinished. Worth landing before wide pilot rollout but not before the core loop is validated.
- **Revisit trigger:** before the expanded beta (beyond the 7 pilot clients), OR the first time a client reacts to Ella's appearance in a way that suggests the avatar's hurting trust.
- **Logged:** 2026-04-24.
