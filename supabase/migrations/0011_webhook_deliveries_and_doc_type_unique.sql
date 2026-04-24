-- 0011_webhook_deliveries_and_doc_type_unique.sql
--
-- Two changes bundled because F2.3 needs both and neither is useful without
-- the other:
--
-- 1. Widen the documents unique constraint to include document_type so a
--    single Fathom recording can have both a `call_transcript_chunk` AND a
--    `call_summary` document. The old constraint UNIQUE(source, external_id)
--    is strictly narrower — any data valid under it is valid under the new
--    UNIQUE(source, external_id, document_type) — so the migration is safe
--    even without a data sweep. The backlog pipeline writes only one doc per
--    (source, external_id) today, so no existing rows can collide under the
--    widened constraint.
--
-- 2. Create the webhook_deliveries table. See docs/architecture/fathom_webhook.md
--    §c for the design: primary-key on webhook-id (Standard Webhooks spec
--    convention is that it's stable across retries — defensive design; if
--    Fathom deviates, dedup falls through to (source, call_external_id) at
--    the DB layer via the widened documents unique + existing calls unique).
--    Rows survive beyond successful processing so they act as the audit log
--    + replay source for webhook-driven ingestion.
--
-- Closes the call_summary and call_action_items deferrals from the F1 era
-- (both listed in docs/future-ideas.md) — the widened unique lets summaries
-- coexist with transcripts; call_action_items already has a table from 0003.

begin;

alter table documents drop constraint documents_source_external_id_key;
alter table documents
  add constraint documents_source_external_id_type_key
  unique (source, external_id, document_type);

create table webhook_deliveries (
  webhook_id         text        primary key,
  source             text        not null default 'fathom_webhook',
  received_at        timestamptz not null default now(),
  processed_at       timestamptz,
  processing_status  text        not null default 'received'
                     check (processing_status in
                            ('received','processed','failed','duplicate','malformed')),
  processing_error   text,
  call_external_id   text,
  payload            jsonb,
  headers            jsonb
);

comment on table  webhook_deliveries is
  'Inbound webhook delivery ledger: one row per delivery attempt. Primary dedup via PK on webhook-id plus observability / replay source. See docs/architecture/fathom_webhook.md §c.';
comment on column webhook_deliveries.webhook_id is
  'Value of the webhook-id header (Standard Webhooks spec). Assumed stable across retries; if Fathom mints a fresh id per attempt, dedup falls back to the calls_source_external_id_key unique on downstream inserts.';
comment on column webhook_deliveries.source is
  'Origin of the delivery. Today: fathom_webhook (live path) and fathom_cron (daily backfill from GET /meetings). Kept as free text for future sources.';
comment on column webhook_deliveries.processing_status is
  'received → processed (happy path), failed (ingest raised, Fathom retries eligible), duplicate (PK conflict on retry, early return), malformed (adapter rejected payload, no retry).';
comment on column webhook_deliveries.call_external_id is
  'Populated after the adapter extracts recording_id. Nullable because the row is written BEFORE adapter runs so even bad-signature / malformed deliveries leave an audit trail.';
comment on column webhook_deliveries.payload is
  'Full raw JSON body. Used for replay and forensic re-parse if the adapter evolves. Stored as jsonb for indexed access on failure investigation.';
comment on column webhook_deliveries.headers is
  'Redacted header snapshot — webhook-id, webhook-timestamp, webhook-signature for post-hoc signature analysis. Secrets never logged.';

create index webhook_deliveries_received_at_idx
  on webhook_deliveries (received_at desc);

create index webhook_deliveries_status_idx
  on webhook_deliveries (processing_status)
  where processing_status <> 'processed';

create index webhook_deliveries_external_id_idx
  on webhook_deliveries (source, call_external_id)
  where call_external_id is not null;

alter table webhook_deliveries enable row level security;

commit;
