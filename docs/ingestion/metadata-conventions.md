# Ingestion Metadata Conventions

Pinned reference for what fields land in `documents.metadata`, `document_chunks.metadata`, and `calls.raw_payload` at ingestion time. Every ingestion pipeline must conform to this doc before writing production rows.

## 1. Scope

This doc covers metadata shape only — column values on the core tables (`documents`, `document_chunks`, `calls`) are already defined by the schema. What varies per source is the `jsonb` bag.

The governing principle: **extending metadata later is cheap, changing existing metadata is expensive.** Adding a new key to future rows costs nothing. Renaming or reshaping a key we've already written thousands of times means touching every ingested row and possibly re-running retrieval evals. So we capture broadly up front, accept some fields we don't query yet, and let query patterns evolve against a stable shape.

Corollary: when in doubt, store it. `raw_payload` preserves the full upstream API response for every source that has one, so we can extract new fields later without re-fetching from the source system.

### Validator

`shared.ingestion.validate` is the canonical check. Two public functions:

- `validate_document_metadata(metadata, source, document_type)` — validates `documents.metadata`.
- `validate_chunk_metadata(metadata, source, document_type)` — validates `document_chunks.metadata`.

Behavior:

- **Missing required key →** raises `ValueError` listing every missing key.
- **Unknown key (not required, not optional) →** logs a warning on `shared.logging.logger`, does not raise. Extensibility is the point of jsonb metadata; we just want visibility when new keys appear.
- **Drive source →** raises `NotImplementedError` pointing at this doc's §2 Drive TBD subsection. When Drive ingestion lands, extend the validator with the pinned shape.
- **Source with no spec →** passes but logs a warning. Add the spec to the validator and this doc at the same time.

**Every ingestion pipeline must call both validators before inserting into `documents` or `document_chunks`.** Adding a new source or document_type means updating three places in the same commit: this doc (§2), the validator's specs, and the pipeline that writes the rows.

## 2. Per-Source Conventions

### Fathom call summaries

`documents` rows with `source = 'fathom'`, `document_type = 'call_summary'`.

`documents.metadata` fields:

| Field | Type | Req | Notes |
|-------|------|-----|-------|
| `client_id` | `uuid` (string) | ✓ | The primary client the call is about. Drives client-scoped retrieval in `match_document_chunks` — this is the gate Ella filters on |
| `call_id` | `uuid` (string) | ✓ | Links back to `calls.id`; join key for anything that needs the raw transcript or participant list |
| `call_category` | `text` | ✓ | Denormalized from `calls.call_category` for filter-side speed. Keep in sync on re-classification |
| `call_type` | `text` | | Denormalized from `calls.call_type` |
| `started_at` | `timestamptz` (ISO string) | ✓ | When the call happened. **Distinct from `documents.created_at`**, which is when we wrote the summary doc — can differ by hours or days |
| `duration_seconds` | `integer` | | Denormalized from `calls.duration_seconds` |
| `participant_emails` | `string[]` | | All attendee emails — lets us filter summaries by attendance without a `call_participants` join |
| `speaker_list` | `string[]` | | Display names of speakers as Fathom reports them; good for UI rendering of the summary |
| `source_url` | `text` | | Fathom share link to the recording |
| `classification_confidence` | `float` | | Denormalized from `calls.classification_confidence` |
| `classification_method` | `text` | | Denormalized from `calls.classification_method` |

### Fathom call transcript chunks

`documents` rows with `source = 'fathom'`, `document_type = 'call_transcript_chunk'`.

Same `documents.metadata` fields as call summaries above. Additional per-chunk metadata lands in `document_chunks.metadata` (see §4).

### Drive documents

`documents` rows with `source = 'drive'`.

**TBD before the Drive ingestion pipeline build.** Indicative fields we expect to capture:

- `drive_url`
- `author`
- `last_modified` (timestamptz)
- `module` (e.g. `module_1`, `module_2`)
- `section`
- `folder_path`

Pin this section — turning it from "TBD" into a signed-off list — as the first step of the Drive ingestion work.

### Manual documents

`documents` rows with `source = 'manual'`. Typically FAQs, SOPs authored in-product.

| Field | Type | Notes |
|-------|------|-------|
| `author` | `text` | Who wrote it |
| `last_reviewed_by` | `text` | Who last verified the content is current |
| `last_reviewed_at` | `timestamptz` | When that review happened |

## 3. Chunking Conventions for Fathom Transcripts

These rules apply when the Fathom ingestion pipeline produces `document_type = 'call_transcript_chunk'` rows with embeddings.

- **Target chunk size:** 400–600 words (~500 tokens).
- **Boundary rule:** always start and end on a speaker turn boundary. Never split mid-utterance.
- **Overlap:** ~50 words with the previous chunk, taken from the tail of the previous chunk, to preserve context across the boundary.
- **Filler filter:** drop utterances under 8 words that are pure acknowledgment or filler. The defined filler set is:
  - `yeah`, `100%`, `for sure`, `right`, `mhm`, `okay`, isolated `thanks`
  - and simple variants (case-insensitive; trailing punctuation ignored)
- **Do not drop** short utterances that contain substantive nouns, verbs, numbers, or proper nouns — even if they'd otherwise match a filler pattern. Example: "Okay, $900 then" is kept; bare "okay" is dropped.
- **Speaker labels:** preserve in chunk text. Do not strip — retrieval benefits from knowing who said what.
- **Timestamps:** preserve in chunk text alongside speaker labels.

## 4. Per-Chunk Metadata

`document_chunks.metadata` for transcript chunks:

| Field | Type | Notes |
|-------|------|-------|
| `chunk_start_ts` | `string` | `"HH:MM:SS"` wall-clock position in the call |
| `chunk_end_ts` | `string` | `"HH:MM:SS"` |
| `speaker_list` | `string[]` | Speakers appearing in this chunk specifically (subset of document-level `speaker_list`) |
| `speaker_turn_count` | `integer` | How many distinct speaker turns landed in this chunk |

**Merge semantics.** `match_document_chunks` returns `chunk.metadata || document.metadata` — document keys win on collision. So do not duplicate keys here that are authoritative on the parent document (e.g. don't put `client_id` or `call_id` in chunk metadata — they live on the document and would be shadowed anyway).

## 5. Classification Rules for Fathom Calls

Ingestion runs this cascade to set `calls.call_category`, `calls.call_type`, `calls.classification_confidence`, `calls.classification_method`, and `calls.primary_client_id`. The first step that produces a confident classification wins; later steps only fire if earlier ones didn't decide.

**Step 1 — Parse header.** Pull structured fields out of the Fathom payload: title, participants (name + email), duration, timestamp, any Fathom-provided category hints. Everything downstream works off this parsed view.

**Step 2 — Participant match.**

- **2+ internal team participants AND no external emails** → `internal`, high confidence.
- **At least one external email that matches a `clients` row** → `client`, high confidence. Set `primary_client_id` to the matched client.
- **External emails that match nothing in `clients`** → `external`, medium confidence.

**Step 3 — Title pattern overrides.** Override whatever Step 2 produced if the title matches a known internal pattern. Force `internal`:

- `CSM_Sync`
- `Backend_Team_`
- `Fulf_Sales_Sync`
- `NCF_`

**Step 4 — "30mins_with_Scott" pattern.** Title matches this pattern AND exactly one non-team participant → `client`, **medium** confidence. Scott does not do sales calls, so this pattern is always a client 1:1.

- If the non-team participant email matches a `clients` row → promote to high confidence and set `primary_client_id`.
- If it does not match → auto-create a minimal `clients` row with `metadata.auto_created_from_call_ingestion = true` and `tags = ['needs_review']`. Set `primary_client_id` to the new row. Confidence stays medium until a human confirms the identity.

**Step 5 — Short-file heuristic.** If `duration_seconds < 90` OR the source file is under 3 KB → `excluded`. These are fragments, test calls, or accidental recordings, not content worth indexing.

**Step 6 — Confidence floor for retrievability.** Only flip `calls.is_retrievable_by_client_agents = true` when **all three** hold:

- `call_category = 'client'`, and
- `classification_confidence` is high, and
- `primary_client_id is not null`.

Medium-confidence `client` calls stay `is_retrievable_by_client_agents = false` until a human reviewer promotes them. Same for any `unclassified` holdover.

## 6. Re-Classification Policy

Running classification is **idempotent**. Re-running it updates `call_category`, `classification_confidence`, `classification_method`, and `call_type` on existing `calls` rows — but does not re-embed, re-chunk, or re-create `documents` / `document_chunks` entries that already exist for the call.

This enables the review loop: sample a batch of calls, spot where rules mislabel, adjust the cascade, re-run classification across all calls, observe the effect, iterate.

**`is_retrievable_by_client_agents` is NOT touched by re-classification.** Flipping that flag is a deliberate human action — promoting a call into Ella's retrieval pool is a safety-relevant decision, not an automatic consequence of a rule tweak. Re-classification can *demote* (any time a call leaves the `client`-high-confidence-with-client-id state, retrievability gets turned off automatically), but it never auto-promotes.

## 7. Storage vs. Retrieval

Two principles the pipeline must never violate:

- **Raw transcripts are stored verbatim.** `calls.transcript` holds the full transcript text as received. `calls.raw_payload` holds the full upstream API response. Nothing in the chunking, filtering, or filler-removal pipeline deletes, alters, or overwrites these source fields.
- **Chunks are derived artifacts.** Anything that lands in `documents` / `document_chunks` from a Fathom call is derived — summaries, transcript chunks, filtered content. Re-running ingestion with different chunking or filtering rules is always possible because the source is intact.

If a convention change invalidates existing chunks, the recovery is: update the rules, delete and re-produce the `documents` / `document_chunks` rows for affected calls, re-embed. The `calls` row itself doesn't need touching.
