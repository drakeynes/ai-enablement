-- 0151 — AI call intelligence on the DC Ads read layer (Nabeel 2026-08-18).
--
-- Companion to 0150 (the dc_ads review rubric). Four changes:
--
--   dc_ads_daily()        + aiQ / aiQN / aiQQual / aiQQualN — the day's
--                         avg AI lead-quality score (0-10) over cohort
--                         leads with a dc_ads-rubric review, all leads and
--                         qualified-only, with n counts. LEAD-level: the
--                         lead's NEWEST reviewed call wins, so multi-dial
--                         leads don't over-weight the average.
--   dc_ads_ad_table()     the same four, grouped by ad.
--   dc_ads_funnel_by_rep() + aiRepScore / aiRepN — the rep's avg AI
--                         execution score over their window calls
--                         (CALL-level: execution is per call).
--   dc_ads_call_reviews() NEW — the ONE call-level read behind the
--                         Connected Calls feed + intel blocks: per-call
--                         review rows (capped 500, newest first, with true
--                         totals), derived missed-sale / great-save flags
--                         (SQL thresholds, tunable here without
--                         re-reviewing), the why-not-closed distribution,
--                         archetype × closes, VoC quotes, and window
--                         averages. ACTIVITY-scoped (calls that happened
--                         in-window), unlike the cohort tables.
--
-- Everything reads call_type='dc_ads' rows ONLY — pre-0150 DC-cohort
-- reviews were graded on the wrong (book) rubric and never surface on the
-- dashboard (forward-only decision, Drake 2026-08-18).
--
-- The three re-created functions are the live definitions (pg_get_functiondef,
-- 2026-08-18 = 0142/0147/0143 bodies) with ONLY the AI additions spliced in.

CREATE OR REPLACE FUNCTION public.dc_ads_daily(p_end_et date, p_days integer DEFAULT 5, p_campaign_id text DEFAULT NULL::text, p_adset_id text DEFAULT NULL::text, p_ad_id text DEFAULT NULL::text, p_form_id text DEFAULT NULL::text, p_funnel_label text DEFAULT NULL::text, p_lp_slug text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
AS $function$
with days as (
  select (p_end_et - offs)::date as et_day from generate_series(0, p_days - 1) offs
),
f as (
  select *, (anchor at time zone 'America/New_York')::date as et_day
  from dc_ads_lead_facts
  where (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
    and (p_lp_slug is null or lp_slug = p_lp_slug)
),
dials as (
  select f.et_day, count(*) as n
  from f join close_calls c on c.lead_id = f.close_id
    and c.activity_at >= f.anchor and c.direction = 'outbound'
  group by f.et_day
),
-- Per cohort lead: valid-adjusted units with their close DAY (ET), from both
-- form sources — the d0/d3/d7 speed-to-unit read.
close_units as (
  select f.et_day, x.units,
    ((x.form_at at time zone 'America/New_York')::date - f.et_day) as days_to_close
  from f
  join lateral (
    select coalesce(s.date_time_of_call, s.airtable_created_at) as form_at,
      cardinality(dc_valid_plans(s.plans, s.valid)) as units
    from airtable_digital_college_sales s
    where s.lead_id = f.close_id and s.excluded_at is null
      and coalesce(s.valid,'') <> 'No'
      and lower(coalesce(s.closed,'')) = 'yes'
      and coalesce(s.date_time_of_call, s.airtable_created_at) >= f.anchor
    union all
    select fr.airtable_created_at,
      (select count(*) from unnest(coalesce(fr.dc_plans,'{}'::text[])) p where trim(p) <> '')
    from airtable_full_closer_report fr
    where fr.lead_id = f.close_id and fr.form_type = 'New'
      and fr.digital_college_closed = 'Yes'
      and fr.airtable_created_at >= f.anchor
  ) x on true
  where x.units > 0
),
-- Latest dc_ads-rubric AI review per cohort lead (0150/0151) — lead-level,
-- newest reviewed call wins, so multi-dialed leads don't over-weight the
-- averages. Pre-0150 rows (call_type <> 'dc_ads') never surface here —
-- forward-only by decision (Drake 2026-08-18).
ai as (
  select distinct on (f.close_id) f.et_day, f.close_id, f.tf_qualified, r.lead_score
  from f
  join close_calls c on c.lead_id = f.close_id and c.activity_at >= f.anchor
  join setter_call_reviews r on r.close_call_id = c.close_id and r.call_type = 'dc_ads'
  order by f.close_id, c.activity_at desc
)
select coalesce(jsonb_agg(jsonb_build_object(
  'etDate',    d.et_day,
  'optIns',    (select count(*) from f where f.et_day = d.et_day),
  'qualified', (select count(*) filter (where tf_qualified) from f where f.et_day = d.et_day),
  'sms',       (select count(*) filter (where has_inbound) from f where f.et_day = d.et_day),
  'smsMql',    (select count(*) filter (where has_inbound and tf_qualified) from f where f.et_day = d.et_day),
  'hvc',       (select count(*) filter (where call90 and (tf_qualified or has_inbound))
                  from f where f.et_day = d.et_day),
  'units',     (select coalesce(sum(plan_units), 0) from f where f.et_day = d.et_day),
  'unitsD0',   (select coalesce(sum(units), 0) from close_units cu
                  where cu.et_day = d.et_day and cu.days_to_close = 0),
  'unitsD3',   (select coalesce(sum(units), 0) from close_units cu
                  where cu.et_day = d.et_day and cu.days_to_close < 3),
  'unitsD7',   (select coalesce(sum(units), 0) from close_units cu
                  where cu.et_day = d.et_day and cu.days_to_close < 7),
  'called',    (select count(*) filter (where any_call or call90 or booked or showed or closed) from f where f.et_day = d.et_day),
  'connected', (select count(*) filter (where call90) from f where f.et_day = d.et_day),
  'closed',    (select count(*) filter (where closed) from f where f.et_day = d.et_day),
  'cashUsd',   (select coalesce(sum(plan_units), 0) * 300 from f where f.et_day = d.et_day),
  'aiQ',       (select round(avg(lead_score)::numeric, 1) from ai where ai.et_day = d.et_day),
  'aiQN',      (select count(*) from ai where ai.et_day = d.et_day),
  'aiQQual',   (select round(avg(lead_score)::numeric, 1) from ai where ai.et_day = d.et_day and ai.tf_qualified),
  'aiQQualN',  (select count(*) from ai where ai.et_day = d.et_day and ai.tf_qualified),
  'dials',     coalesce((select n from dials where dials.et_day = d.et_day), 0)
) order by d.et_day desc), '[]'::jsonb)
from days d
$function$;

CREATE OR REPLACE FUNCTION public.dc_ads_ad_table(p_start timestamp with time zone, p_end timestamp with time zone, p_campaign_id text DEFAULT NULL::text, p_adset_id text DEFAULT NULL::text, p_ad_id text DEFAULT NULL::text, p_form_id text DEFAULT NULL::text, p_funnel_label text DEFAULT NULL::text, p_lp_slug text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
AS $function$
with f as (
  select *, (anchor at time zone 'America/New_York')::date as et_day
  from dc_ads_lead_facts
  where anchor >= p_start and anchor < p_end
    and (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
    and (p_lp_slug is null or lp_slug = p_lp_slug)
),
dials as (
  select f.ad_id, count(*) as n
  from f join close_calls c on c.lead_id = f.close_id
    and c.activity_at >= f.anchor and c.direction = 'outbound'
  group by f.ad_id
),
-- Per cohort lead: valid-adjusted units with days-to-close relative to the
-- lead's OWN ET opt-in day — dc_ads_daily()'s close_units, grouped by ad.
close_units as (
  select f.ad_id, x.units,
    ((x.form_at at time zone 'America/New_York')::date - f.et_day) as days_to_close
  from f
  join lateral (
    select coalesce(s.date_time_of_call, s.airtable_created_at) as form_at,
      cardinality(dc_valid_plans(s.plans, s.valid)) as units
    from airtable_digital_college_sales s
    where s.lead_id = f.close_id and s.excluded_at is null
      and coalesce(s.valid,'') <> 'No'
      and lower(coalesce(s.closed,'')) = 'yes'
      and coalesce(s.date_time_of_call, s.airtable_created_at) >= f.anchor
    union all
    select fr.airtable_created_at,
      (select count(*) from unnest(coalesce(fr.dc_plans,'{}'::text[])) p where trim(p) <> '')
    from airtable_full_closer_report fr
    where fr.lead_id = f.close_id and fr.form_type = 'New'
      and fr.digital_college_closed = 'Yes'
      and fr.airtable_created_at >= f.anchor
  ) x on true
  where x.units > 0
),
-- Latest dc_ads-rubric AI review per cohort lead (0150/0151), grouped by ad
-- — lead-level like the daily table's; pre-0150 rows never surface.
ai as (
  select distinct on (f.close_id) f.ad_id, f.close_id, f.tf_qualified, r.lead_score
  from f
  join close_calls c on c.lead_id = f.close_id and c.activity_at >= f.anchor
  join setter_call_reviews r on r.close_call_id = c.close_id and r.call_type = 'dc_ads'
  order by f.close_id, c.activity_at desc
),
agg as (
  select ad_id,
    count(*) as opt_ins,
    count(*) filter (where tf_qualified) as qualified,
    count(*) filter (where has_inbound) as sms,
    count(*) filter (where has_inbound and tf_qualified) as sms_mql,
    count(*) filter (where call90) as connected,
    count(*) filter (where call90 and (tf_qualified or has_inbound)) as hvc,
    coalesce(sum(plan_units), 0) as units,
    count(*) filter (where closed) as closed
  from f group by ad_id
)
select coalesce(jsonb_agg(jsonb_build_object(
  'adId',      a.ad_id,
  'optIns',    a.opt_ins,
  'qualified', a.qualified,
  'sms',       a.sms,
  'smsMql',    a.sms_mql,
  'connected', a.connected,
  'hvc',       a.hvc,
  'units',     a.units,
  'unitsD0',   coalesce((select sum(units) from close_units cu where cu.ad_id is not distinct from a.ad_id and cu.days_to_close = 0), 0),
  'unitsD3',   coalesce((select sum(units) from close_units cu where cu.ad_id is not distinct from a.ad_id and cu.days_to_close < 3), 0),
  'unitsD7',   coalesce((select sum(units) from close_units cu where cu.ad_id is not distinct from a.ad_id and cu.days_to_close < 7), 0),
  'closed',    a.closed,
  'cashUsd',   a.units * 300,
  'aiQ',       (select round(avg(lead_score)::numeric, 1) from ai where ai.ad_id is not distinct from a.ad_id),
  'aiQN',      (select count(*) from ai where ai.ad_id is not distinct from a.ad_id),
  'aiQQual',   (select round(avg(lead_score)::numeric, 1) from ai where ai.ad_id is not distinct from a.ad_id and ai.tf_qualified),
  'aiQQualN',  (select count(*) from ai where ai.ad_id is not distinct from a.ad_id and ai.tf_qualified),
  'dials',     coalesce((select n from dials d where d.ad_id is not distinct from a.ad_id), 0)
) order by a.opt_ins desc), '[]'::jsonb)
from agg a
$function$;

CREATE OR REPLACE FUNCTION public.dc_ads_funnel_by_rep(p_start timestamp with time zone, p_end timestamp with time zone, p_campaign_id text DEFAULT NULL::text, p_adset_id text DEFAULT NULL::text, p_ad_id text DEFAULT NULL::text, p_form_id text DEFAULT NULL::text, p_funnel_label text DEFAULT NULL::text, p_lp_slug text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
AS $function$
with leads as (
  select close_id from dc_ads_lead_facts
  where (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
    and (p_lp_slug is null or lp_slug = p_lp_slug)
),
calls as (
  select cc.user_id,
    max(cc.raw_payload ->> 'user_name') as user_name,
    count(*) filter (where cc.direction = 'outbound') as dials,
    count(*) filter (where cc.duration >= 90)         as connections,
    sum(coalesce(cc.duration, 0))                     as talk_seconds
  from close_calls cc
  join leads l on l.close_id = cc.lead_id
  where cc.activity_at >= p_start and cc.activity_at < p_end
    and cc.user_id is not null
  group by cc.user_id
),
-- Per-rep AI rep-score sums over the window's dc_ads-rubric reviews (0151).
-- sum+n (not avg) so calls_rep's re-aggregation by rep_key stays exact.
ai_rep as (
  select cc.user_id,
    sum(r.rep_score)::numeric as ai_score_sum,
    count(*)::int             as ai_n
  from close_calls cc
  join leads l on l.close_id = cc.lead_id
  join setter_call_reviews r on r.close_call_id = cc.close_id
    and r.call_type = 'dc_ads' and r.rep_score is not null
  where cc.activity_at >= p_start and cc.activity_at < p_end
    and cc.user_id is not null
  group by cc.user_id
),
calls_rep as (
  select coalesce(tm.id::text, ca.user_id)                        as rep_key,
         tm.id::text                                              as tm_id,
         coalesce(tm.full_name, ca.user_name, ca.user_id)         as rep_name,
         sum(ca.dials)::int as dials, sum(ca.connections)::int as connections,
         sum(ca.talk_seconds)::bigint as talk_seconds,
         sum(ar.ai_score_sum)         as ai_score_sum,
         coalesce(sum(ar.ai_n), 0)::int as ai_n
  from calls ca
  left join ai_rep ar on ar.user_id = ca.user_id
  left join team_members tm on tm.close_user_id = ca.user_id
  group by 1, 2, 3
),
-- DC closes in window (with a plan; a no-plan form is a show, not a close),
-- from BOTH form sources: the closer report and the DC sale form.
dc_forms as (
  select f.lead_id, f.closer_record_ids, f.closer_names, f.dc_plans as plans
  from airtable_full_closer_report f
  join leads l on l.close_id = f.lead_id
  where f.form_type = 'New' and f.digital_college_closed = 'Yes'
    and f.airtable_created_at >= p_start and f.airtable_created_at < p_end
    and (select count(*) from unnest(coalesce(f.dc_plans,'{}'::text[])) p where trim(p) <> '') > 0
  union all
  select s.lead_id, s.closer_record_ids, s.closer_names,
    dc_valid_plans(s.plans, s.valid) as plans
  from airtable_digital_college_sales s
  join leads l on l.close_id = s.lead_id
  where lower(coalesce(s.closed,'')) = 'yes' and s.excluded_at is null
    and coalesce(s.valid,'') <> 'No'
    and coalesce(s.date_time_of_call, s.airtable_created_at) >= p_start
    and coalesce(s.date_time_of_call, s.airtable_created_at) < p_end
    and cardinality(dc_valid_plans(s.plans, s.valid)) > 0
),
-- Every filed pitch in window (a filed form = a show), the refresh's
-- is_showed semantics — broader than dc_forms (no-plan and not-closed forms
-- still count as shows).
shows_forms as (
  select f.lead_id, f.closer_record_ids, f.closer_names
  from airtable_full_closer_report f
  join leads l on l.close_id = f.lead_id
  where f.airtable_created_at >= p_start and f.airtable_created_at < p_end
    and (case when f.form_type = 'New'
      then coalesce(f.call_outcome,'') <> '' and lower(f.call_outcome) !~ 'ghost|no show|reschedul|cancel'
      else lower(coalesce(f.showed,'')) = 'yes' end)
  union all
  select s.lead_id, s.closer_record_ids, s.closer_names
  from airtable_digital_college_sales s
  join leads l on l.close_id = s.lead_id
  where s.excluded_at is null
    and coalesce(s.valid,'') <> 'No'
    and coalesce(s.date_time_of_call, s.airtable_created_at) >= p_start
    and coalesce(s.date_time_of_call, s.airtable_created_at) < p_end
    and (coalesce(s.closed,'') <> ''
      or coalesce(s.prospect_name,'') <> ''
      or (select count(*) from unnest(coalesce(s.plans,'{}'::text[])) p where trim(p) <> '') > 0)
),
shows_rep as (
  select coalesce(tm.id::text, t.rid, t.nm) as rep_key,
         tm.id::text                        as tm_id,
         coalesce(tm.full_name, t.nm)       as rep_name,
         count(distinct sf.lead_id)::int    as shows
  from shows_forms sf
  cross join lateral unnest(sf.closer_record_ids, sf.closer_names) as t(rid, nm)
  left join team_members tm on tm.airtable_user_id = t.rid
  group by 1, 2, 3
),
closes_raw as (
  select t.rid, t.nm, f.lead_id,
    (select count(*) from unnest(coalesce(f.plans,'{}'::text[])) p where trim(p) <> '') as units
  from dc_forms f
  cross join lateral unnest(f.closer_record_ids, f.closer_names) as t(rid, nm)
),
closes_rep as (
  select coalesce(tm.id::text, cr.rid, cr.nm)  as rep_key,
         tm.id::text                           as tm_id,
         coalesce(tm.full_name, cr.nm)         as rep_name,
         count(distinct cr.lead_id)::int       as closes,
         (coalesce(sum(cr.units), 0) * 300)::int as cash
  from closes_raw cr
  left join team_members tm on tm.airtable_user_id = cr.rid
  group by 1, 2, 3
),
-- Per-rep plan-unit splits from the closing forms (a two-closer form credits
-- both, matching closes_rep).
plan_rep as (
  select coalesce(tm.id::text, t.rid, t.nm) as rep_key,
    count(*)::int as units,
    sum((lower(p) like '%base%' and lower(p) like '%month%')::int)::int as b44m,
    sum((lower(p) like '%base%' and (lower(p) like '%year%' or lower(p) like '%annual%'))::int)::int as b44y,
    sum((lower(p) like '%wix%'  and lower(p) like '%month%')::int)::int as wixm,
    sum((lower(p) like '%wix%'  and (lower(p) like '%year%' or lower(p) like '%annual%'))::int)::int as wixy
  from dc_forms f
  cross join lateral unnest(f.closer_record_ids, f.closer_names) as t(rid, nm)
  cross join lateral unnest(coalesce(f.plans,'{}'::text[])) p
  left join team_members tm on tm.airtable_user_id = t.rid
  where trim(p) <> ''
  group by 1
),
merged as (
  select
    coalesce(cl.rep_key, co.rep_key, sh.rep_key)    as rep_key,
    coalesce(cl.tm_id, co.tm_id, sh.tm_id)          as tm_id,
    coalesce(cl.rep_name, co.rep_name, sh.rep_name) as rep_name,
    coalesce(cl.dials, 0)       as dials,
    coalesce(cl.connections, 0) as connections,
    coalesce(cl.talk_seconds, 0) as talk_seconds,
    cl.ai_score_sum              as ai_score_sum,
    coalesce(cl.ai_n, 0)         as ai_n,
    coalesce(sh.shows, 0)       as shows,
    coalesce(co.closes, 0)      as closes,
    coalesce(pl.units, 0)       as units,
    coalesce(pl.b44m, 0)        as b44m,
    coalesce(pl.b44y, 0)        as b44y,
    coalesce(pl.wixm, 0)        as wixm,
    coalesce(pl.wixy, 0)        as wixy,
    coalesce(co.cash, 0)        as cash
  from calls_rep cl
  full outer join closes_rep co on co.rep_key = cl.rep_key
  full outer join shows_rep sh on sh.rep_key = coalesce(cl.rep_key, co.rep_key)
  left join plan_rep pl on pl.rep_key = coalesce(cl.rep_key, co.rep_key, sh.rep_key)
),
plan_units as (
  select p from dc_forms f cross join lateral unnest(coalesce(f.plans,'{}'::text[])) p where trim(p) <> ''
)
select jsonb_build_object(
  'reps', (
    select coalesce(jsonb_agg(jsonb_build_object(
        'rep', rep_name, 'teamMemberId', tm_id,
        'dials', dials, 'connections', connections, 'talkSeconds', talk_seconds,
        'aiRepScore', case when ai_n > 0 then round(ai_score_sum / ai_n, 1) end,
        'aiRepN', ai_n,
        'shows', shows,
        'closes', closes, 'units', units,
        'base44Monthly', b44m, 'base44Yearly', b44y,
        'wixMonthly', wixm, 'wixYearly', wixy,
        'cash', cash
      ) order by closes desc, cash desc, shows desc, connections desc, dials desc), '[]'::jsonb)
    from merged where dials > 0 or connections > 0 or closes > 0 or shows > 0
  ),
  'totals', jsonb_build_object(
    'closes',        (select count(distinct lead_id) from dc_forms),
    'base44Monthly', (select coalesce(sum((lower(p) like '%base%' and lower(p) like '%month%')::int),0) from plan_units),
    'base44Yearly',  (select coalesce(sum((lower(p) like '%base%' and (lower(p) like '%year%' or lower(p) like '%annual%'))::int),0) from plan_units),
    'wixMonthly',    (select coalesce(sum((lower(p) like '%wix%' and lower(p) like '%month%')::int),0) from plan_units),
    'wixYearly',     (select coalesce(sum((lower(p) like '%wix%' and (lower(p) like '%year%' or lower(p) like '%annual%'))::int),0) from plan_units)
  )
);
$function$;

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
    r.lead_score, r.intent, r.offer_understanding, r.rep_score,
    r.main_objection, r.why_not_closed, r.recoverable, r.archetype,
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
    'mainObjection', main_objection, 'recoverable', recoverable,
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
  'archetypes', coalesce((select jsonb_agg(jsonb_build_object(
      'archetype', g.archetype, 'n', g.n, 'closes', g.closes) order by g.n desc)
    from (
      select archetype, count(*) as n, count(*) filter (where closed) as closes
      from flagged where archetype is not null group by 1) g), '[]'::jsonb),
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

comment on function dc_ads_daily(date, int, text, text, text, text, text, text) is
  'DC ads page: the last-N-ET-days cohort table (opt-ins that day + LIFETIME progression + dials received). 0142 unitsD0/D3/D7; 0151 aiQ/aiQN/aiQQual/aiQQualN — the day''s avg AI lead-quality (0-10) over cohort leads with a dc_ads-rubric review (lead-level, newest reviewed call wins; call_type=dc_ads only, forward-only). Facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132); p_funnel_label deprecated alias.';

comment on function dc_ads_ad_table(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: the per-ad table — the daily RPC''s stage + D0/D3/D7 semantics grouped by ad (0147); 0151 adds aiQ/aiQN/aiQQual/aiQQualN per ad (lead-level dc_ads-rubric AI lead-quality averages). Ad identity/lineage comes from dc_meta_ads client-side.';

comment on function dc_ads_funnel_by_rep(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: per-rep talent detail (dials/connections/talkSeconds/shows/closes/units/plan splits/cash + teamMemberId), ACTIVITY-scoped to [p_start, p_end) over the DC ad cohort. talkSeconds = sum of close_calls.duration (0143). 0151 aiRepScore/aiRepN — avg AI execution score over the rep''s window dc_ads-rubric-reviewed calls (call-level). Shows use the facts refresh''s is_showed semantics; Valid=''No'' forms excluded (0141); multi-closer forms credit every closer while totals count deals once. Facets AND together; p_funnel_label deprecated alias.';

comment on function dc_ads_call_reviews(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: the ONE call-level AI-review read (0151) — per-call dc_ads-rubric rows (capped 500 newest, callsTotal alongside), derived missed-sale (not closed & lead>=7 & intent>=7 & rep<=5) and great-save (closed & (lead<=4 or intent<=4)) flags with capped lists + true totals, the why-not-closed distribution over lost calls, archetype × closes, VoC quotes (newest 100), and window averages. ACTIVITY-scoped; facets AND together like the sibling RPCs. call_type=dc_ads only — pre-0150 book-rubric reviews never surface.';
