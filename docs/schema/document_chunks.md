# document_chunks

Documents split into retrievable chunks with vector embeddings.

## Purpose

The retrieval surface. `shared/kb_query.py` runs approximate nearest-neighbor searches here, then joins back to `documents` for metadata filtering (type, tags, `client_id` for call summaries).

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK |
| `document_id` | `uuid` | FK → `documents.id`, not null, cascade delete |
| `chunk_index` | `integer` | Zero-based position within the parent document |
| `content` | `text` | Not null. The chunk text |
| `embedding` | `vector(1536)` | Nullable — chunks may exist briefly before embedding completes |
| `token_count` | `integer` | |
| `metadata` | `jsonb` | Per-chunk. May redundantly carry `document_type` / `tags` for retrieval-side filtering |
| `created_at` | `timestamptz` | |

`UNIQUE (document_id, chunk_index)` keeps re-chunking idempotent.

## Embedding Model

Dimension `1536` matches OpenAI `text-embedding-3-small`. Model choice is an ADR; changing models means re-embedding existing rows, not a schema change.

## Indexes

- `hnsw (embedding vector_cosine_ops)` — approximate nearest-neighbor with cosine distance. HNSW defaults are fine for V1 scale; tune `m` / `ef_construction` if recall is lacking later.
- B-tree on `document_id` for chunk-by-document lookups.

## Relationships

- FK to `documents` (cascade delete)

## Populated By

- Document ingestion pipeline: on new or updated documents, chunk the content, embed each chunk, upsert rows

## Read By

- `shared/kb_query.py` — the only place retrieval should happen. Agents never query this table directly.

## Search Function

`match_document_chunks` is the Postgres function that powers all retrieval. `shared/kb_query.py` wraps it via Supabase RPC; no agent should bypass this wrapper. Defined in migration `0008_kb_search.sql`.

### Signature

```sql
match_document_chunks(
  query_embedding  vector(1536),
  match_count      int     default 8,
  document_types   text[]  default null,
  tags             text[]  default null,
  min_similarity   float   default 0.0,
  client_id        text    default null,
  include_global   bool    default true
)
returns table (
  chunk_id             uuid,
  document_id          uuid,
  document_type        text,
  document_title       text,
  document_created_at  timestamptz,
  content              text,
  chunk_index          int,
  similarity           float,   -- 1 - cosine_distance, higher is closer
  metadata             jsonb    -- chunk metadata merged with document metadata; document wins on key collision
)
```

### Behavior

**Global mode** (when `client_id is null`):
- Returns chunks from `is_active = true` documents.
- **Always excludes `document_type = 'call_summary'`**, even if the caller passes `call_summary` in `document_types`. This is the hard safety gate: no call summary ever leaks into a global query.

**Client mode** (when `client_id is not null`):
- Always includes `call_summary` chunks where `documents.metadata->>'client_id'` matches the passed `client_id`.
- If `include_global = true` (default), also returns chunks from non-`call_summary` active documents in the same ranked list, single `match_count` cap.
- If `include_global = false`, returns only that client's call summaries.

**Filters applied in all modes:**
- `document_types` (optional) — narrow to given types. Subject to the global `call_summary` exclusion in global mode.
- `tags` (optional) — match documents with any overlapping tag.
- `min_similarity` (default 0.0) — drop rows below this cosine similarity.
- `match_count` (default 8) — LIMIT on the final ranked list.

**Similarity metric:** `1 - (embedding <=> query_embedding)`, i.e. cosine similarity for normalized vectors. Higher = closer. Range is theoretically `[-1, 1]`; in practice positive for non-adversarial matches.

**Metadata merge:** returned `metadata` is `chunk.metadata || document.metadata`. Document keys override chunk keys on collision so document-level tags (e.g. `client_id` on call summaries) are authoritative.

### Example

```sql
-- Global FAQ/course match, top 5.
select chunk_id, document_type, similarity
from match_document_chunks(
  query_embedding => '[0.1, 0.2, ...]'::vector,
  match_count => 5,
  document_types => array['faq', 'course_lesson']
);

-- Client-scoped match mixing call summaries with global docs.
select chunk_id, document_type, similarity
from match_document_chunks(
  query_embedding => '[0.1, 0.2, ...]'::vector,
  match_count => 8,
  client_id => '<uuid>',
  include_global => true
);
```

## Example Queries

Top-k nearest chunks to a query embedding, filtered to a document type:

```sql
select ch.id, ch.content, ch.document_id,
       ch.embedding <=> $1 as distance
from document_chunks ch
join documents d on d.id = ch.document_id
where d.document_type = $2
  and d.is_active = true
order by ch.embedding <=> $1
limit 10;
```

Client-scoped retrieval for call summaries:

```sql
select ch.id, ch.content, d.title
from document_chunks ch
join documents d on d.id = ch.document_id
where d.document_type = 'call_summary'
  and d.metadata->>'client_id' = $2
  and d.is_active = true
order by ch.embedding <=> $1
limit 10;
```
