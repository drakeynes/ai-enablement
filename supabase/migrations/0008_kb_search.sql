-- 0008_kb_search.sql
-- Postgres function match_document_chunks — the retrieval primitive every
-- client-facing agent (Ella first) uses via shared/kb_query.py.
--
-- Pushes filtering + ordering into Postgres so HNSW can do its job on a
-- pre-filtered set. Alternative (pull top-N unfiltered, filter in Python)
-- wastes embedding-ranked rows to client-side filtering.
--
-- Safety-relevant behavior baked in:
--   1. call_summary documents are ALWAYS excluded in global mode (when
--      client_id is null), regardless of the document_types argument.
--   2. In client mode, call_summary rows are gated to documents whose
--      metadata->>'client_id' matches the passed client_id.
--   3. Inactive documents (is_active = false) never appear.

create or replace function match_document_chunks(
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
  similarity           float,
  metadata             jsonb
)
language sql
stable parallel safe
as $$
  select
    ch.id                                                              as chunk_id,
    d.id                                                               as document_id,
    d.document_type,
    d.title                                                            as document_title,
    d.created_at                                                       as document_created_at,
    ch.content,
    ch.chunk_index,
    (1 - (ch.embedding <=> match_document_chunks.query_embedding))::float as similarity,
    coalesce(ch.metadata, '{}'::jsonb) || coalesce(d.metadata, '{}'::jsonb) as metadata
  from document_chunks ch
  join documents d on d.id = ch.document_id
  where d.is_active = true
    and ch.embedding is not null
    and (
      -- Global mode: no client; call_summary excluded.
      (match_document_chunks.client_id is null
        and d.document_type <> 'call_summary')
      or
      -- Client mode: call_summary scoped to this client, optionally plus global docs.
      (match_document_chunks.client_id is not null and (
        (d.document_type = 'call_summary'
           and d.metadata->>'client_id' = match_document_chunks.client_id)
        or (match_document_chunks.include_global
              and d.document_type <> 'call_summary')
      ))
    )
    and (match_document_chunks.document_types is null
         or d.document_type = any(match_document_chunks.document_types))
    and (match_document_chunks.tags is null
         or d.tags && match_document_chunks.tags)
    and (1 - (ch.embedding <=> match_document_chunks.query_embedding))
          >= match_document_chunks.min_similarity
  order by ch.embedding <=> match_document_chunks.query_embedding
  limit match_document_chunks.match_count;
$$;

comment on function match_document_chunks(
  vector, int, text[], text[], float, text, bool
) is
  'Retrieval primitive for document_chunks. See docs/schema/document_chunks.md for the full contract. '
  'Always excludes call_summary in global mode and scopes call_summary to a single client in client mode.';
