-- 0010_kb_search_exclude_transcript_chunks.sql
-- Extend match_document_chunks's global-mode exclusion to cover
-- `call_transcript_chunk` alongside `call_summary`.
--
-- Why: call_transcript_chunk documents carry metadata.client_id
-- (they're derived from a specific client's call). Before this
-- migration, global-mode search excluded only call_summary — which
-- meant a future caller doing a global query could surface one
-- client's transcript content to another client. The fix is to
-- treat both document types as "client-scoped" in the function.
--
-- Safety invariant going forward: **no client-scoped call content
-- appears in global results, ever**. The types covered are
-- `call_summary` and `call_transcript_chunk`. When a new
-- client-scoped type is introduced, add it here.

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
      -- Global mode: no client; client-scoped types excluded.
      (match_document_chunks.client_id is null
        and d.document_type not in ('call_summary', 'call_transcript_chunk'))
      or
      -- Client mode: client-scoped types gated to this client, optionally plus
      -- globally-retrievable (non-client-scoped) types.
      (match_document_chunks.client_id is not null and (
        (d.document_type in ('call_summary', 'call_transcript_chunk')
           and d.metadata->>'client_id' = match_document_chunks.client_id)
        or (match_document_chunks.include_global
              and d.document_type not in ('call_summary', 'call_transcript_chunk'))
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
  'Safety invariant: client-scoped types (call_summary, call_transcript_chunk) are excluded in global '
  'mode and scoped to a single client in client mode.';
