-- 0157: per-rep close-rate inputs on dc_ads_funnel_by_rep() (Drake 2026-08-22).
--
-- The close-rate trio (close rate / qualified / non-qualified) moves to the
-- DC ads BY REP table — its intended home; 907b7ea had put it on the daily +
-- per-ad tables by mistake (reverted client-side). Rates are closes ÷ leads
-- CONNECTED — lead counts, not connection counts: the existing `connections`
-- field counts per CALL (a lead reached twice counts twice), so the rep rows
-- gain DISTINCT-lead connection counts as denominators:
--
--   leadsConnected        — distinct leads the rep had a ≥90s call with
--                           in-window (same call rule as `connections`:
--                           both directions, inbound pickups count)
--   qualifiedConnected    — of those, tf-qualified leads
--   unqualifiedConnected  — the rest: answered-but-missed AND partial-survey
--                           leads (user 2026-08-22: partial counts as
--                           non-qualified here, unlike the lead roster's
--                           three-state qualState)
--
-- and the numerator splits of the rep's existing `closes`:
--
--   qualifiedClosed / unqualifiedClosed — the rep's distinct closed leads
--                           split the same way
--
-- Qualified + non-qualified cover every lead, so the Q and NonQ fractions
-- sum to the global one (closes ÷ leadsConnected). Closes credit via the
-- closer forms while connects come from close_calls — a rep can close a
-- lead they never "connected" with, so a rate can exceed 100% on tiny
-- numbers; the table shows the fraction beside the percent.

CREATE OR REPLACE FUNCTION public.dc_ads_funnel_by_rep(p_start timestamp with time zone, p_end timestamp with time zone, p_campaign_id text DEFAULT NULL::text, p_adset_id text DEFAULT NULL::text, p_ad_id text DEFAULT NULL::text, p_form_id text DEFAULT NULL::text, p_funnel_label text DEFAULT NULL::text, p_lp_slug text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
AS $function$
with leads as (
  -- tf_q = the roster RPC's qualState 'qualified' (0144: hit the LP's
  -- qualify answer); tf_nq = everyone else — answered-but-missed AND
  -- partial-survey leads both count as non-qualified here (user 2026-08-22),
  -- so the two splits partition the cohort.
  select close_id,
    coalesce(tf_qualified, false) as tf_q,
    (not coalesce(tf_qualified, false)) as tf_nq
  from dc_ads_lead_facts
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
-- Per-rep DISTINCT-lead connection counts + qual splits (0157) — the
-- close-rate denominators. Unlike `connections` (per CALL), each lead
-- counts once per rep however many ≥90s calls it took.
lead_conn as (
  select cc.user_id,
    count(distinct cc.lead_id)                        as leads_connected,
    count(distinct cc.lead_id) filter (where l.tf_q)  as q_connected,
    count(distinct cc.lead_id) filter (where l.tf_nq) as nq_connected
  from close_calls cc
  join leads l on l.close_id = cc.lead_id
  where cc.activity_at >= p_start and cc.activity_at < p_end
    and cc.user_id is not null
    and cc.duration >= 90
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
         coalesce(sum(ar.ai_n), 0)::int as ai_n,
         coalesce(sum(lc.leads_connected), 0)::int as leads_connected,
         coalesce(sum(lc.q_connected), 0)::int     as q_connected,
         coalesce(sum(lc.nq_connected), 0)::int    as nq_connected
  from calls ca
  left join ai_rep ar on ar.user_id = ca.user_id
  left join lead_conn lc on lc.user_id = ca.user_id
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
         count(distinct cr.lead_id) filter (where l.tf_q)::int  as q_closes,
         count(distinct cr.lead_id) filter (where l.tf_nq)::int as nq_closes,
         (coalesce(sum(cr.units), 0) * 300)::int as cash
  from closes_raw cr
  join leads l on l.close_id = cr.lead_id
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
    coalesce(cl.leads_connected, 0) as leads_connected,
    coalesce(cl.q_connected, 0)     as q_connected,
    coalesce(cl.nq_connected, 0)    as nq_connected,
    coalesce(sh.shows, 0)       as shows,
    coalesce(co.closes, 0)      as closes,
    coalesce(co.q_closes, 0)    as q_closes,
    coalesce(co.nq_closes, 0)   as nq_closes,
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
        'leadsConnected', leads_connected,
        'qualifiedConnected', q_connected,
        'unqualifiedConnected', nq_connected,
        'shows', shows,
        'closes', closes, 'units', units,
        'qualifiedClosed', q_closes,
        'unqualifiedClosed', nq_closes,
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
  'DC ads page: per-rep talent detail (dials/connections/talkSeconds/shows/closes/units/plan splits/cash + teamMemberId), ACTIVITY-scoped to [p_start, p_end) over the DC ad cohort. talkSeconds = sum of close_calls.duration (0143). 0151 aiRepScore/aiRepN — avg AI execution score over the rep''s window dc_ads-rubric-reviewed calls (call-level). 0157 close-rate inputs for the By rep table: leadsConnected = DISTINCT leads the rep connected with (≥90s call, lead count not call count); qualifiedConnected/unqualifiedConnected + qualifiedClosed/unqualifiedClosed split connects and the rep''s closes by tf_qualified — partial-survey leads count as NON-qualified (the splits partition the cohort, so Q + NonQ fractions sum to the global). Shows use the facts refresh''s is_showed semantics; Valid=''No'' forms excluded (0141); multi-closer forms credit every closer while totals count deals once. Facets AND together; p_funnel_label deprecated alias.';
