-- 0143: talk time on the DC Ads per-rep table (boss batch 2026-08-15).
--
-- Adds talkSeconds to dc_ads_funnel_by_rep(): the sum of close_calls.duration
-- (seconds) over the rep's window calls against the DC cohort — ALL calls,
-- both directions, connected or not (a 5s no-answer adds 5s; the noise is
-- negligible and "time on the phone" is the number the boss reads). Same
-- grain as Dials/Connections: the calls CTE already groups the window's
-- close_calls per Close user, so talk time sums with no extra join.
--
-- Body-only change — signature unchanged, so CREATE OR REPLACE (no drop).
-- Everything except the four talk_seconds lines is copied verbatim from 0141.

create or replace function dc_ads_funnel_by_rep(
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
calls_rep as (
  select coalesce(tm.id::text, ca.user_id)                        as rep_key,
         tm.id::text                                              as tm_id,
         coalesce(tm.full_name, ca.user_name, ca.user_id)         as rep_name,
         sum(ca.dials)::int as dials, sum(ca.connections)::int as connections,
         sum(ca.talk_seconds)::bigint as talk_seconds
  from calls ca
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

comment on function dc_ads_funnel_by_rep(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: per-rep talent detail (dials/connections/talkSeconds/shows/closes/units/plan splits/cash + teamMemberId), ACTIVITY-scoped to [p_start, p_end) over the DC ad cohort. talkSeconds = sum of close_calls.duration over the rep''s window calls, all calls both directions (0143). Shows use the facts refresh''s is_showed semantics; Valid=''No'' forms are excluded and partial verdicts keep only the verified plan type (0141); a multi-closer form credits every closer while the totals count deals once. Facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132); p_funnel_label deprecated alias.';
