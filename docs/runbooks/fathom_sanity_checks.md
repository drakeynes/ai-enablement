# Fathom ingest sanity checks

Run these against cloud Supabase (project `sjjovsjcfffrftnraocu`) when you want confidence that Fathom ingest is healthy. Useful before building on top of the data, or as a periodic spot-check.

Run them in the Supabase SQL editor or via psql. They're read-only.

## Q1 — Headline counts

Confirm the system isn't losing data.

```sql
select
  (select count(*) from calls where source = 'fathom') as fathom_calls,
  (select count(*) from call_participants) as participants,
  (select count(*) from call_action_items) as action_items,
  (select count(*) from documents where document_type = 'call_summary') as summary_docs,
  (select count(*) from documents where document_type = 'call_transcript_chunk') as transcript_docs,
  (select count(*) from document_chunks) as total_chunks,
  (select count(*) from webhook_deliveries where source = 'fathom_cron') as cron_deliveries,
  (select count(*) from webhook_deliveries where source = 'fathom_webhook') as webhook_deliveries;
```

**What to look for:** counts should equal or exceed the most recent baseline (daily cron grows them over time). **Red flag:** any number *below* baseline — means data was deleted or rolled back.

## Q2 — Classifier output distribution

See how Fathom calls are split across categories. Surfaces the F1.5 bug and Aman-style misclassifications.

```sql
select
  call_category,
  count(*) as call_count,
  count(*) filter (where primary_client_id is not null) as with_client,
  count(*) filter (where primary_client_id is null) as no_client
from calls
where source = 'fathom'
group by call_category
order by call_count desc;
```

**What to look for:** sane split. The known F1.5 bug is 9 `client`-category calls with NULL `primary_client_id` — that count should still be 9. **Red flag:** if `client` no_client > 9, the bug grew.

## Q3 — Orphan call_participants and call_action_items

Referential integrity. Every participant and action item should point to a real call.

```sql
select
  'orphan_participants' as check_name,
  count(*) as orphan_count
from call_participants cp
left join calls c on c.id = cp.call_id
where c.id is null
union all
select
  'orphan_action_items',
  count(*)
from call_action_items cai
left join calls c on c.id = cai.call_id
where c.id is null;
```

**What to look for:** both should be 0. **Red flag:** anything > 0 means inserts happened in wrong order or a delete cascaded incompletely.

## Q4 — Documents without chunks, orphan chunks, missing embeddings

Every `documents` row of an indexable type should have at least one `document_chunks` row, every chunk should point to a valid document, and every chunk should have an embedding.

```sql
select
  'docs_without_chunks' as check_name,
  count(*) as count
from documents d
where document_type in ('call_summary', 'call_transcript_chunk')
  and not exists (select 1 from document_chunks dc where dc.document_id = d.id)
union all
select
  'orphan_chunks',
  count(*)
from document_chunks dc
left join documents d on d.id = dc.document_id
where d.id is null
union all
select
  'chunks_missing_embedding',
  count(*)
from document_chunks
where embedding is null;
```

**What to look for:** all three should be 0. **Red flag:** `docs_without_chunks > 0` means embedding step failed silently. `chunks_missing_embedding > 0` means OpenAI embedding call failed and was swallowed.

## Q5 — Calls without transcript or summary documents

Every Fathom call in an indexable category should produce a transcript chunk; only cron-ingested calls should produce summary documents (backlog `.txt` exports don't carry summaries).

```sql
select
  'fathom_calls_no_transcript_doc' as check_name,
  count(*) as count
from calls c
where c.source = 'fathom'
  and not exists (
    select 1 from documents d
    where d.document_type = 'call_transcript_chunk'
      and d.metadata->>'call_id' = c.id::text
  )
union all
select
  'fathom_calls_no_summary_doc',
  count(*)
from calls c
where c.source = 'fathom'
  and not exists (
    select 1 from documents d
    where d.document_type = 'call_summary'
      and d.metadata->>'call_id' = c.id::text
  );
```

**What to look for:** `no_transcript_doc` count should equal the count of non-`client` category calls (per `_INDEXABLE_CATEGORIES = {"client"}` in `ingestion/fathom/pipeline.py`, only `client` calls get indexed). `no_summary_doc` will be high — only cron-ingested calls have summaries; backlog calls don't. **Red flag:** `client`-category calls in the missing-transcripts list (use Q5b to break this down).

## Q5b — Missing-transcripts breakdown by category

Distinguishes "expected behavior" from "silent failure" for Q5.

```sql
select
  c.call_category,
  count(*) as call_count
from calls c
where c.source = 'fathom'
  and not exists (
    select 1 from documents d
    where d.document_type = 'call_transcript_chunk'
      and d.metadata->>'call_id' = c.id::text
  )
group by c.call_category
order by call_count desc;
```

**What to look for:** breakdown should be entirely non-`client` categories (`internal`, `external`, `unclassified`, `excluded`). **Red flag:** any meaningful number of `client`-category calls in this list — that's silent ingest failure.

## Q6 — F1.5 bug confirmation

Explicit check that the known orphan count hasn't grown.

```sql
select count(*) as f15_orphan_count
from calls
where call_category = 'client'
  and primary_client_id is null;
```

**What to look for:** exactly 9. **Red flag:** anything > 9 means the bug has new instances; the deferred fix becomes more urgent.

## Q7 — Webhook deliveries health

Confirm the cron path is healthy and the webhook path is reachable but quiet.

```sql
select
  source,
  processing_status,
  count(*) as delivery_count,
  max(received_at) as most_recent
from webhook_deliveries
group by source, processing_status
order by source, processing_status;
```

**What to look for:** `fathom_cron / processed` count growing daily, `most_recent` within ~24h of now (cron runs 08:00 UTC daily). A small number of `failed` rows from the documented race condition is expected. `fathom_webhook` rows still 0 is fine for now. **Red flag:** `fathom_cron / processed` hasn't grown in multiple days, or new `failed` / `malformed` rows appearing.

## Q8 — Most recent ingest sanity

Prove the system is actively ingesting, not just sitting on backlog data.

```sql
select
  max(c.started_at) as latest_call_started_at,
  max(c.ingested_at) as latest_call_ingested_at,
  max(cai.extracted_at) as latest_action_item_ingested_at,
  max(d.created_at) filter (where d.document_type = 'call_summary') as latest_summary_ingested_at
from calls c
left join call_action_items cai on cai.call_id = c.id
left join documents d on d.metadata->>'call_id' = c.id::text;
```

**What to look for:** `latest_call_ingested_at` within the last day or so. `latest_summary_ingested_at` from the most recent cron run. **Red flag:** ingestion timestamps stale by multiple days — cron may be silently broken.

## What this exercise doesn't catch

These queries verify structural and quantitative health. They don't catch:

- **Embedding quality** — chunks could have populated embeddings that are semantically wrong (zeros, wrong dimensions, wrong text embedded). Needs vector similarity spot-check or manual retrieval test.
- **Transcript content correctness** — chunks could be present but contain garbage (truncation mid-word, wrong call's transcript, encoding issues). Needs eyeballing actual document content.
- **Action item attribution** — `call_action_items` could exist but be assigned to the wrong person or call. Counts won't show this.
- **Idempotency under re-run** — these queries are point-in-time. They don't prove that re-running ingestion wouldn't create duplicates.
- **Pre-fix data** — if a fix to ingestion was deployed and not retroactively backfilled, old rows may be in a different state than new rows. Counts won't surface this.

For deeper inspection, the Gregory dashboard (V1) will provide a UI for spot-checking individual calls, summaries, and classifications.
