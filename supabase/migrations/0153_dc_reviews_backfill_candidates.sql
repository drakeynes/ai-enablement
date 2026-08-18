-- 0153 — dc_ads_backfill_candidates(): the rubric-backfill work queue.
--
-- Nabeel verified the v3 dc_ads review output (2026-08-18) and approved the
-- backfill: the ~460 DC-cohort calls reviewed before 0150 were graded on the
-- outbound BOOK rubric (wrong motion) and are invisible to the dashboard
-- (which reads call_type='dc_ads' only). Backfill = re-review each with
-- force=True — transcripts are already stored, so this is a Sonnet-only
-- re-grade (~$0.02/call, ~$9 total).
--
-- This function is the per-tick work queue for api/dc_reviews_backfill_cron.py
-- (temporary cron schedule; removed once the queue reads empty). A call is a
-- candidate when:
--   - it already HAS a review whose call_type <> 'dc_ads' (the wrong-rubric
--     rows — never-reviewed calls are the sweep/webhook's job, not ours),
--   - its lead is in dc_ads_lead_facts (the DC ads cohort),
--   - its lead does NOT carry the "DC Revival Lead" CF — those calls are
--     CORRECTLY graded revival, and since the reviewer would re-grade them
--     revival again they would otherwise sit in this queue forever, burning
--     a Sonnet call per tick (keep the CF id in sync with
--     agents/setter_call_reviewer/reviewer.py REVIVAL_CF),
--   - its transcript still exists (belt-and-braces; the 0054 cascade FK
--     already guarantees it).
--
-- Newest first, so the most decision-relevant calls fill in first. A
-- successful re-grade flips call_type to 'dc_ads' and the row drops out of
-- the queue; a failed one is retried next tick (the cron caps per-tick work,
-- and the schedule is removed after the queue drains, so a pathological
-- transcript can't burn indefinitely).

create or replace function dc_ads_backfill_candidates(p_limit int default 20)
returns setof text
language sql
stable
as $function$
  select r.close_call_id
  from setter_call_reviews r
  join close_calls c on c.close_id = r.close_call_id
  join dc_ads_lead_facts f on f.close_id = c.lead_id
  join setter_call_transcripts t on t.close_call_id = r.close_call_id
  join close_leads cl on cl.close_id = c.lead_id
  where r.call_type <> 'dc_ads'
    and coalesce(cl.custom_fields_raw ->> 'cf_QivXkWBvr34UIDkUBKXNCQo6woarc62wEbIacWWbN7P', '') = ''
  order by c.activity_at desc
  limit p_limit
$function$;

comment on function dc_ads_backfill_candidates(int) is
  'Work queue for the 0150-rubric review backfill (Nabeel-approved 2026-08-18): DC-cohort calls whose existing review used the wrong (book) rubric — excludes revival-CF leads (correctly graded) so the queue provably drains. Read by api/dc_reviews_backfill_cron.py; safe to keep after the backfill (returns 0 rows when done).';
