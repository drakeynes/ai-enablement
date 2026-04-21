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

## Topic-based chunking for call transcripts

- **What:** chunk transcripts on semantic topic boundaries (detected via a small LLM call per transcript) instead of fixed word windows. More expensive per ingest, potentially better retrieval relevance because chunks align to "what the call was about at this moment" rather than to arbitrary word counts.
- **Why deferred:** requires an extra LLM call per call during ingestion. The current word-window-with-speaker-boundary approach (see `docs/ingestion/metadata-conventions.md` §3) is sufficient for V1 and lets us see real retrieval failures before spending the complexity.
- **Revisit trigger:** Ella V1 beta shows retrieval misses that a topic-aligned chunk would have caught — e.g. a query lands on a half-chunk mid-topic because the word boundary cut through a discussion.
- **Logged:** 2026-04-21.
