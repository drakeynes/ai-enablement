-- 0155: DC calls intel v4 — Nabeel's feedback round (2026-08-19).
--
-- Three changes, one SQL bundle (the RPC is redefined once):
--
-- 1. rep_gap on setter_call_reviews — WHICH gap lost a rep_execution call.
--    Fixed vocabulary (CHECK, off-vocab coerces to 'other' in the reviewer,
--    same 0150 pattern). Prompt v4 sets it; null on every other outcome.
--    "73% rep execution" gets its own dataset.
--
-- 2. dc_ads_call_reviews():
--    - archetypes go LEAD-level: each lead counted once (newest review in
--      the window names its archetype), closes = the lead's EVENTUAL DC
--      close from dc_ads_lead_facts. The old call-level AI-judged
--      close-on-this-call read "1% closed" while 15% of those leads
--      actually bought (verified 2026-08-19: 6 on-call closes across 492
--      reviewed calls vs 55 eventual closes across 398 leads). The on-call
--      count survives as 'onCallCloses' for the footnote.
--    - per-call payload gains noCloseReason / recoverableNote / repGap —
--      the feed's at-a-glance sub-line (the AI read without a click).
--    - 'repGaps': rep_gap distribution over lost rep_execution calls in
--      the window ('unclassified' = pre-v4 rows the backfill hasn't
--      re-graded yet; the bucket disappears when the queue drains).
--
-- 3. dc_ads_backfill_candidates() repointed at the v4 need: dc_ads
--    reviews lost to rep_execution that lack rep_gap. Re-review with
--    force=True sets rep_gap (or moves why_not_closed) — either way the
--    row leaves the queue, so it provably drains. Driven by the kept
--    api/dc_reviews_backfill_cron.py on a TEMPORARY schedule (remove it
--    from vercel.json when the queue reads 0, same as the 0153 run).

-- 1. the column ------------------------------------------------------------

alter table setter_call_reviews
  add column if not exists rep_gap text
    check (rep_gap in (
      'no_close_attempt', 'gave_up_at_objection', 'no_urgency',
      'weak_discovery', 'offer_not_explained', 'talked_over_lead',
      'deferred_to_followup', 'other'));

comment on column setter_call_reviews.rep_gap is
  '0155 (prompt v4): the rep''s PRIMARY gap when why_not_closed=rep_execution — no_close_attempt | gave_up_at_objection | no_urgency | weak_discovery | offer_not_explained | talked_over_lead | deferred_to_followup | other. null on every other outcome and on pre-v4 rows not yet re-graded.';

-- 2. dc_ads_call_reviews() ---------------------------------------------------

create or replace function dc_ads_call_reviews(
  p_start timestamptz,
  p_end timestamptz,
  p_campaign_id text default null,
  p_adset_id text default null,
  p_ad_id text default null,
  p_form_id text default null,
  p_funnel_label text default null,
  p_lp_slug text default null
)
returns jsonb
language sql
stable
as $function$
with f as (
  select * from dc_ads_lead_facts
  where (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
    and (p_lp_slug is null or lp_slug = p_lp_slug)
),
-- Reviewed dc_ads-rubric calls whose activity fell IN the window. The feed
-- is activity-scoped (what calls happened these days), unlike the cohort
-- tables — a call today to a last-week opt-in belongs to today's feed.
rc as (
  select c.close_id as call_id, c.activity_at, c.duration, c.user_id,
    coalesce(nullif(c.raw_payload ->> 'user_name', ''), c.user_id) as user_name,
    f.close_id as lead_id, f.tf_qualified, f.campaign_id, f.adset_id,
    f.ad_id, f.lp_slug,
    f.closed as lead_closed,
    r.lead_score, r.intent, r.offer_understanding, r.rep_score,
    r.main_objection, r.why_not_closed, r.rep_gap, r.recoverable,
    r.recoverable_note, r.no_close_reason, r.archetype,
    r.voc_quotes, r.closed, r.should_be_dqd
  from f
  join close_calls c on c.lead_id = f.close_id and c.activity_at >= f.anchor
  join setter_call_reviews r on r.close_call_id = c.close_id
    and r.call_type = 'dc_ads'
  where c.activity_at >= p_start and c.activity_at < p_end
),
named as (
  select rc.*,
    coalesce(tm.full_name, rc.user_name)                     as rep_name,
    coalesce(nullif(trim(cl.display_name), ''), '(no name)') as lead_name
  from rc
  left join team_members tm on tm.close_user_id = rc.user_id
  left join close_leads cl on cl.close_id = rc.lead_id
),
-- Derived management flags — SQL-side BY DESIGN (0150: the model never
-- self-asserts these; thresholds are tunable here without re-reviewing).
-- Missed sale = a good lead with real intent that a low-execution call
-- failed to close. Great save = a weak/low-intent lead closed anyway.
flagged as (
  select named.*,
    (not closed and lead_score >= 7 and intent >= 7 and rep_score <= 5) as is_missed,
    (closed and (lead_score <= 4 or intent <= 4))                       as is_save
  from named
),
call_row as (
  select flagged.*, jsonb_build_object(
    'callId', call_id, 'at', activity_at, 'durationS', duration,
    'leadId', lead_id, 'leadName', lead_name, 'repName', rep_name,
    'tfQualified', tf_qualified, 'campaignId', campaign_id, 'adId', ad_id,
    'leadScore', lead_score, 'intent', intent,
    'offerUnderstanding', offer_understanding, 'repScore', rep_score,
    'closed', closed, 'whyNotClosed', why_not_closed,
    'repGap', rep_gap,
    'mainObjection', main_objection, 'recoverable', recoverable,
    'recoverableNote', recoverable_note, 'noCloseReason', no_close_reason,
    'archetype', archetype, 'dq', should_be_dqd,
    'missed', is_missed, 'save', is_save
  ) as j
  from flagged
)
select jsonb_build_object(
  'calls', coalesce((select jsonb_agg(t.j order by t.activity_at desc) from (
    select j, activity_at from call_row
    order by activity_at desc limit 500) t), '[]'::jsonb),
  'callsTotal', (select count(*) from call_row),
  'missed', coalesce((select jsonb_agg(t.j order by t.activity_at desc) from (
    select j, activity_at from call_row where is_missed
    order by activity_at desc limit 50) t), '[]'::jsonb),
  'missedTotal', (select count(*) from flagged where is_missed),
  'saves', coalesce((select jsonb_agg(t.j order by t.activity_at desc) from (
    select j, activity_at from call_row where is_save
    order by activity_at desc limit 50) t), '[]'::jsonb),
  'savesTotal', (select count(*) from flagged where is_save),
  'whyNotClosed', coalesce((select jsonb_object_agg(g.reason, g.n) from (
    select why_not_closed as reason, count(*) as n from flagged
    where not closed and why_not_closed is not null group by 1) g), '{}'::jsonb),
  'lostTotal', (select count(*) from flagged where not closed),
  -- rep_execution sub-dataset (0155): which gap, over the window's lost
  -- rep_execution calls. 'unclassified' = pre-v4 reviews awaiting backfill.
  'repGaps', coalesce((select jsonb_object_agg(g.gap, g.n) from (
    select coalesce(rep_gap, 'unclassified') as gap, count(*) as n
    from flagged where not closed and why_not_closed = 'rep_execution'
    group by 1) g), '{}'::jsonb),
  -- LEAD-level archetypes (0155): each lead once (newest review names it),
  -- closes = the lead's EVENTUAL DC close from the facts — the number the
  -- rest of the dashboard means by "closed".
  'archetypes', coalesce((select jsonb_agg(jsonb_build_object(
      'archetype', g.archetype, 'n', g.n, 'closes', g.closes) order by g.n desc)
    from (
      select pl.archetype, count(*) as n,
             count(*) filter (where pl.lead_closed) as closes
      from (
        select distinct on (lead_id) lead_id, archetype, lead_closed
        from flagged where archetype is not null
        order by lead_id, activity_at desc
      ) pl group by 1) g), '[]'::jsonb),
  'onCallCloses', (select count(*) from flagged where closed),
  'voc', coalesce((select jsonb_agg(jsonb_build_object(
      'quote', t.q ->> 'quote', 'topic', t.q ->> 'topic',
      'leadName', t.lead_name, 'callId', t.call_id) order by t.activity_at desc)
    from (
      select fl.lead_name, fl.call_id, fl.activity_at, q
      from flagged fl
      cross join lateral jsonb_array_elements(fl.voc_quotes) q
      order by fl.activity_at desc limit 100) t), '[]'::jsonb),
  'avg', (select jsonb_build_object(
    'leadScore', round(avg(lead_score)::numeric, 1),
    'intent', round(avg(intent)::numeric, 1),
    'offerUnderstanding', round(avg(offer_understanding)::numeric, 1),
    'repScore', round(avg(rep_score)::numeric, 1),
    'n', count(*)) from flagged)
)
$function$;

comment on function dc_ads_call_reviews(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: the ONE call-level AI-review read (0151, reshaped 0155) — per-call dc_ads-rubric rows (capped 500 newest, callsTotal alongside; noCloseReason/recoverableNote/repGap ride along for the feed''s at-a-glance sub-line), derived missed-sale (not closed & lead>=7 & intent>=7 & rep<=5) and great-save (closed & (lead<=4 or intent<=4)) flags with capped lists + true totals, the why-not-closed distribution over lost calls, repGaps (the rep_execution sub-dataset; unclassified = pre-v4 rows), LEAD-level archetypes (each lead once via its newest review; closes = the lead''s eventual facts close — on-call closes survive as onCallCloses), VoC quotes (newest 100), and window averages. ACTIVITY-scoped; facets AND together like the sibling RPCs. call_type=dc_ads only.';

-- 3. the backfill queue, repointed at v4 -------------------------------------

create or replace function dc_ads_backfill_candidates(p_limit int default 20)
returns setof text
language sql
stable
as $function$
  select r.close_call_id
  from setter_call_reviews r
  join close_calls c on c.close_id = r.close_call_id
  join setter_call_transcripts t on t.close_call_id = r.close_call_id
  where r.call_type = 'dc_ads'
    and r.why_not_closed = 'rep_execution'
    and r.rep_gap is null
  order by c.activity_at desc
  limit p_limit
$function$;

comment on function dc_ads_backfill_candidates(int) is
  'Work queue for review-rubric backfills, repointed 0155 at the v4 rep_gap need: dc_ads reviews lost to rep_execution that lack rep_gap. A force re-review under prompt v4 sets rep_gap (or moves why_not_closed) — either way the row leaves the queue, so it provably drains. Read by api/dc_reviews_backfill_cron.py on a TEMPORARY vercel.json schedule; safe to keep after the drain (returns 0 rows when done).';
