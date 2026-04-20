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
