-- 0004_documents.sql
-- Knowledge content: documents and document_chunks with pgvector embeddings.
-- Enables the vector extension (pgvector) needed for semantic retrieval.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------------
create table documents (
  id              uuid primary key default gen_random_uuid(),
  source          text not null,
  external_id     text,
  title           text not null,
  content         text not null,
  document_type   text not null,
  tags            text[] not null default '{}'::text[],
  metadata        jsonb not null default '{}'::jsonb,
  is_active       boolean not null default true,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  archived_at     timestamptz,
  unique (source, external_id)
);

comment on table documents is
  'Source of truth for everything Ella and other agents should know: course lessons, FAQs, SOPs, methodology docs, and generated call_summary documents that link back to calls.';
comment on column documents.source is
  'Where the document originated: drive, manual, notion, call_summary (generated), etc.';
comment on column documents.external_id is
  'Source-system id for re-sync. Null for manually authored docs. Unique together with source.';
comment on column documents.document_type is
  'course_lesson, faq, sop, methodology, onboarding, call_summary, etc.';
comment on column documents.tags is
  'Ad-hoc labels (module_1, sales, onboarding, ...). GIN-indexed for filter queries.';
comment on column documents.metadata is
  'Source-specific fields. For call_summary rows: metadata.client_id identifies the client the summary is about — client-facing agents must filter on it.';
comment on column documents.is_active is
  'Soft archive for retrieval. Set to false to hide from Ella without deleting the row.';

create index documents_type_idx on documents (document_type) where is_active = true;
create index documents_tags_idx on documents using gin (tags);
create index documents_metadata_client_id_idx
  on documents ((metadata->>'client_id'))
  where document_type = 'call_summary';

create trigger documents_set_updated_at
  before update on documents
  for each row execute function set_updated_at();

alter table documents enable row level security;

-- ---------------------------------------------------------------------------
-- document_chunks
-- ---------------------------------------------------------------------------
create table document_chunks (
  id              uuid primary key default gen_random_uuid(),
  document_id     uuid not null references documents(id) on delete cascade,
  chunk_index     integer not null,
  content         text not null,
  embedding       vector(1536),
  token_count     integer,
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  unique (document_id, chunk_index)
);

comment on table document_chunks is
  'Chunked, embedded form of documents. Retrieval queries run against this table via shared/kb_query.py.';
comment on column document_chunks.chunk_index is
  'Zero-based position within the parent document. Combined with document_id, unique.';
comment on column document_chunks.embedding is
  'Vector embedding. Dimension 1536 matches OpenAI text-embedding-3-small. Model choice is an ADR; changing models means re-embedding, not schema change.';
comment on column document_chunks.metadata is
  'Per-chunk metadata. May carry document tags redundantly for retrieval-side filtering.';

create index document_chunks_document_id_idx on document_chunks (document_id);

-- HNSW index for approximate nearest-neighbor search with cosine distance.
-- Fine for V1 scale; tune m/ef_construction later if recall becomes an issue.
create index document_chunks_embedding_hnsw_idx
  on document_chunks using hnsw (embedding vector_cosine_ops);

alter table document_chunks enable row level security;
