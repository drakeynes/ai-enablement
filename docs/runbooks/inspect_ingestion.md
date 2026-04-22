# Runbook: Inspect Ingestion Results

Canned SQL queries for sanity-checking what the Fathom backlog pipeline landed in Supabase. Run these after every `--apply`, and any time a classifier tweak or pipeline change goes in. Each query has a **good** / **bad** line describing what the output should look like.

All queries are copy-pasteable into Studio's SQL Editor or piped via:

```bash
docker exec -i supabase_db_ai-enablement psql -U postgres -d postgres < <<EOF...EOF
```

Replace the placeholder UUIDs / client ids / query vectors with real values where the comment says so.

---

## 1. Classification distribution — `call_category × confidence`

```sql
-- Good: roughly the distribution your dry-run predicted. Most calls
--       are in one bucket (`client` high, `internal` high).
-- Bad:  large `unclassified` row, or many `client` rows at medium
--       confidence (every medium-confidence client call is a human
--       review candidate).
select
  call_category,
  case
    when classification_confidence >= 0.9 then 'high'
    when classification_confidence >= 0.6 then 'medium'
    else 'low'
  end as confidence_tier,
  count(*)
from calls
group by call_category, confidence_tier
order by call_category, confidence_tier;
```

---

## 2. Random sample of client calls with their primary client

```sql
-- Good: every row has a full_name in primary_client and a
--       non-null started_at. Titles match the matched client.
-- Bad:  null primary_client_id on rows labeled `client` (shouldn't
--       happen after retrievability floor), or mismatches between
--       the title and the matched client name.
select
  c.external_id,
  c.title,
  c.call_category,
  c.classification_confidence,
  cl.full_name as primary_client,
  c.started_at,
  c.is_retrievable_by_client_agents
from calls c
left join clients cl on cl.id = c.primary_client_id
where c.call_category = 'client'
order by random()
limit 10;
```

---

## 3. Cross-client safety check — no client-scoped content in global retrieval

```sql
-- The same check `match_document_chunks` enforces at runtime, run
-- explicitly to confirm the function's global-mode exclusion list
-- matches what's in the DB.
--
-- Good: zero rows. If the `documents` table has any client-scoped
--       types NOT in the exclusion list, the match function would
--       leak one client's content to another client's query.
-- Bad:  any rows returned — means there's a client-scoped
--       document_type (carrying metadata.client_id) that the
--       `match_document_chunks` global exclusion doesn't cover.
--       Fix: add a migration extending the function's NOT IN list.
select distinct document_type
from documents
where metadata ? 'client_id'
  and document_type not in ('call_summary', 'call_transcript_chunk');
```

---

## 4. All chunks for a specific call

```sql
-- Replace <call-id-uuid> with the calls.id you want to inspect. Use
-- query 2 to find a candidate.
--
-- Good: chunks are sequential (chunk_index 0, 1, 2, ...), each with a
--       speaker_list and timestamp range, with content preserving the
--       `[HH:MM:SS] Speaker:` formatting.
-- Bad:  gaps in chunk_index (bad re-ingest), missing embeddings,
--       metadata keys missing speaker_list or speaker_turn_count.
select
  ch.chunk_index,
  ch.metadata->>'chunk_start_ts' as start_ts,
  ch.metadata->>'chunk_end_ts' as end_ts,
  ch.metadata->'speaker_list' as speakers,
  ch.metadata->>'speaker_turn_count' as turns,
  length(ch.content) as content_chars,
  (ch.embedding is not null) as has_embedding
from document_chunks ch
join documents d on d.id = ch.document_id
where d.document_type = 'call_transcript_chunk'
  and d.metadata->>'call_id' = '<call-id-uuid>'
order by ch.chunk_index;
```

---

## 5. What would Ella retrieve for client X asking about topic Y

```sql
-- Full chain traversal. Replace <client-id>, <query-embedding> with
-- real values. The query_embedding needs to come from
-- shared.kb_query.embed('your question') — quickest way to get one is:
--
--   python -c "from shared.kb_query import embed; \
--              print(embed('did we discuss pricing?'))"
--
-- Then paste the list into the vector literal below.
--
-- Good: top rows are clearly relevant to the question, all with
--       document_type in ('call_summary', 'call_transcript_chunk',
--       'faq', 'course_lesson'...), similarity > 0.3 at minimum.
-- Bad:  results from the wrong client (metadata.client_id should
--       match the passed client_id for any client-scoped rows), or
--       all rows at similarity < 0.2 (retrieval miss — see if topic
--       chunking or hybrid search would help; future-ideas has both).
select
  m.chunk_id,
  m.document_type,
  m.document_title,
  m.similarity,
  m.metadata->>'client_id' as chunk_client_id,
  substring(m.content from 1 for 120) as preview
from match_document_chunks(
  query_embedding => '[0.1, 0.2, ...]'::vector,  -- replace with real
  match_count => 8,
  client_id => '<client-id>',                     -- replace with real
  include_global => true
) as m
order by m.similarity desc;
```

---

## 6. Low-confidence calls needing human review

```sql
-- Good: small list, manageable (expect ≤20 calls on a clean backlog
--       ingest). The 30mins-with-Scott auto-create path produces
--       medium-confidence client calls with auto_created_from_call
--       _ingestion clients — those are the expected residents here.
-- Bad:  high volume suggests the classifier needs tuning OR the data
--       has unfamiliar title / participant patterns worth encoding.
select
  c.external_id,
  c.title,
  c.call_category,
  c.classification_confidence,
  c.classification_method,
  cl.full_name as primary_client,
  (cl.metadata->>'auto_created_from_call_ingestion')::bool as was_auto_created,
  c.started_at
from calls c
left join clients cl on cl.id = c.primary_client_id
where c.classification_confidence < 0.9
  and c.call_category != 'excluded'
order by c.call_category, c.classification_confidence, c.started_at desc;
```

---

## 7. Distinct tag values across documents — content audit surface

```sql
-- Canonical query for finding / archiving old content versions once
-- Drive and other content ingestion land. Fathom pipeline leaves tags
-- empty today, so this returns near-zero rows for now; the query is
-- pre-built so the workflow is ready when content ingestion arrives.
--
-- Good: expected tag vocabulary (module_1, onboarding, sop,
--       methodology, etc. once content is in). Counts match the
--       number of docs you'd expect per tag.
-- Bad:  near-identical tags that differ only in case or whitespace
--       (`module_1` vs `Module_1` vs `module 1`) — indicates a
--       normalization bug in the ingestion pipeline. Stale tags
--       (e.g. `module_3_v1_deprecated` with non-zero count) flag
--       content that should be archived.
select
  tag,
  count(*) as document_count,
  count(*) filter (where is_active = true) as active_count,
  count(*) filter (where is_active = false) as archived_count
from documents, unnest(tags) as tag
group by tag
order by document_count desc;
```

### Tags plan

Tags are currently unused by the Fathom pipeline (transcript chunk documents ship with `tags = '{}'`). They become useful once content ingestion lands:

- **Drive ingestion** (future) will tag each document with module / section / content-category (e.g. `module_1`, `sop`, `methodology`). Query #7 becomes the content audit surface.
- **Archival workflow**: when a module gets a new version, the old version's documents flip to `is_active = false` but keep their tags. Query #7's `archived_count` column is how you spot those.
- **Deprecation sweeps**: periodic runs to find tags starting with `deprecated_` or `v1_` and confirm those documents are inactive.

No action needed today. Re-read this section the next time content ingestion gets touched.

---

## 8. Orphan check — chunks whose parent document is archived

```sql
-- Good: zero rows. match_document_chunks filters on
--       documents.is_active = true, so chunks under an archived
--       document never surface — but leaving them physically present
--       is still sloppy. If the count is non-zero and growing it
--       suggests a missing cleanup step.
-- Bad:  any non-zero count is worth investigating. If it's from a
--       re-classification demote (client → internal, parent doc
--       soft-archived), that's expected residue and fine. If it's
--       from some other path, that's a bug.
select count(*) as orphan_chunks
from document_chunks ch
join documents d on d.id = ch.document_id
where d.is_active = false;
```

---

## Slack backfill — sanity queries

Run after `ingestion.slack.cli --apply` to verify what landed.

### 9. Message counts per channel (last 90 days)

```sql
-- Good: numbers roughly match the dry-run's per-channel reported
--       `messages_in_window`. Small drift is OK (bot may have joined
--       mid-window; 90-day boundary can straddle a message).
-- Bad:  any client channel in the target list with 0 messages (bot
--       membership dropped, or the channel got archived mid-run).
select
  sc.name as channel,
  c.full_name as client,
  count(m.*) as messages_90d
from slack_channels sc
left join clients c on c.id = sc.client_id
left join slack_messages m
  on m.slack_channel_id = sc.slack_channel_id
  and m.sent_at > now() - interval '90 days'
where sc.name in ('Fernando G', 'Javi Pena', 'Musa Elmaghrabi',
                  'Jenny Burnett', 'Dhamen Hothi', 'Trevor Heck',
                  'Art Nuno', 'ella-test')
group by sc.name, c.full_name
order by messages_90d desc;
```

### 10. author_type distribution across ingested Slack messages

```sql
-- Good: majority is client + team_member; `bot` proportional to how
--       chatty the Slack Workflows / integrations are; `workflow`
--       non-zero only if accountability/NPS flows are in use.
-- Bad:  `unknown` > ~5% of total in any client channel suggests we
--       missed a user in the slack_user_id resolver — either a
--       client who isn't in the clients table, or a team member
--       whose slack_user_id hasn't been backfilled yet.
select
  sc.name as channel,
  m.author_type,
  count(*) as n
from slack_messages m
join slack_channels sc on sc.slack_channel_id = m.slack_channel_id
group by sc.name, m.author_type
order by sc.name, n desc;
```

### 11. Unresolved author ids (audit what's missing from resolvers)

```sql
-- Good: small or empty. Any ids here are candidates to backfill into
--       `team_members.slack_user_id` via `users.info`, or flag as
--       clients we don't have rows for (rare, but possible for
--       ex-clients archived before slack ingest ran).
-- Bad:  many distinct ids with high counts — same as above but more
--       urgent. Consider a backfill pass.
select
  m.slack_user_id,
  count(*) as message_count,
  min(m.sent_at) as first_seen,
  max(m.sent_at) as last_seen
from slack_messages m
where m.author_type = 'unknown'
group by m.slack_user_id
order by message_count desc
limit 30;
```

## Recommended run cadence

- **After every `--apply` of the Fathom pipeline.** Queries 1, 2, 6, 8 are the fast smoke check.
- **After any classifier tweak.** Run the whole set; mostly you're looking at shifts in query 1 and new entries in query 6.
- **When a new client-scoped document type is added.** Query 3 is the correctness gate — a non-empty result means the safety gate isn't holding. Stop and fix before continuing.
- **When debugging an Ella retrieval complaint.** Queries 4 and 5 together show "what chunks exist for this call" and "what chunks the matcher actually surfaces for a given query" — fastest way to pinpoint whether the problem is missing content, a bad chunk, or a retrieval-relevance gap.
