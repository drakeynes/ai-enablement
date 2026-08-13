-- 0131_dc_ads_funnel_facet.sql
--
-- The facet parameters promised in 0130: the four DC-ads read RPCs gain
-- p_funnel_label so the page's landing-page dropdown FILTERS the funnel,
-- by-rep, daily-strip, and speed-to-lead reads instead of the split being a
-- display-only strip. Values match dc_ads_lead_facts.funnel_label — the Close
-- funnel_name falling back to the campaign registry label ('Aman Funnel',
-- 'Luke Funnel', 'Digital College' for the legacy instant-form path).
--
-- Additive only: p_form_id (0128) keeps working — the forms facet is leaving
-- the page's filter row but is planned to resurface in its own section. Like
-- the form, the funnel label is an independent AND facet (a funnel spans many
-- ads), so it composes with the cascade instead of competing with it.
--
-- Bodies are otherwise identical to the live definitions (0128/0129, rows
-- widened by 0130); each function is dropped first because adding a defaulted
-- parameter would otherwise create an ambiguous overload.

-- ------------------------------------------------------------ dc_ads_funnel --

drop function dc_ads_funnel(timestamptz, timestamptz, text, text, text, text);

create function dc_ads_funnel(
  p_start timestamptz default null,
  p_end timestamptz default null,
  p_campaign_id text default null,
  p_adset_id text default null,
  p_ad_id text default null,
  p_form_id text default null,
  p_funnel_label text default null
)
returns jsonb
language sql
stable
as $function$
with f as (
  select * from dc_ads_lead_facts
  where (p_start is null or anchor >= p_start)
    and (p_end is null or anchor < p_end)
    and (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
),
roll as (
  select
    closed,
    (showed or closed) as showed,
    (booked or showed or closed) as booked,
    (call90 or booked or showed or closed) as connected,
    (any_call or call90 or booked or showed or closed) as called,
    booked_dc, booked_ht
  from f
),
-- Speed-to-dial: opt-in → first outbound dial (outbound measures reply → dial;
-- here the opt-in is the hand-raise).
speed as (
  select extract(epoch from (first_dial - anchor)) / 60.0 as mins, call90 as conn
  from f where first_dial is not null
),
sb as (
  select case when mins<5 then 0 when mins<15 then 1 when mins<30 then 2 when mins<60 then 3
    when mins<120 then 4 when mins<360 then 5 when mins<1440 then 6 else 7 end as idx, conn from speed
),
sb_lbl(idx, label) as (values (0,'<5m'),(1,'5–15m'),(2,'15–30m'),(3,'30–60m'),(4,'1–2h'),(5,'2–6h'),(6,'6–24h'),(7,'>24h'))
select jsonb_build_object(
  'activeFrom', (select min(anchor) from dc_ads_lead_facts),
  'activeTo',   (select max(anchor) from dc_ads_lead_facts),
  'funnel', jsonb_build_object(
    'optIns',       (select count(*) from f),
    'called',       (select count(*) filter (where called) from roll),
    'connected',    (select count(*) filter (where connected) from roll),
    'booked',       (select count(*) filter (where booked) from roll),
    'bookedDc',     (select count(*) filter (where booked_dc) from roll),
    'bookedHt',     (select count(*) filter (where booked_ht) from roll),
    'showed',       (select count(*) filter (where showed) from roll),
    'closed',       (select count(*) filter (where closed) from roll),
    'closedPlans',  (select jsonb_build_object('base44Monthly',coalesce(sum(base44_monthly),0),'base44Yearly',coalesce(sum(base44_yearly),0),'wixMonthly',coalesce(sum(wix_monthly),0),'wixYearly',coalesce(sum(wix_yearly),0)) from f),
    'cashUsd',      (select coalesce(sum(plan_units),0)*300 from f),
    'markedNoPlan', (select coalesce(sum(marked_no_plan),0) from f)
  ),
  'called', jsonb_build_object(
    'optIns',         (select count(*) from f),
    'called',         (select count(*) from f where first_dial is not null),
    'connected',      (select count(*) from f where call90),
    'notCalled',      (select count(*) from f) - (select count(*) from f where first_dial is not null),
    'speedN',         (select count(*) from speed),
    'speedMedianMin', (select round(percentile_cont(0.5) within group (order by mins))::int from speed),
    'buckets',        (select coalesce(jsonb_agg(jsonb_build_object(
                          'label', l.label,
                          'count', (select count(*) from sb where sb.idx = l.idx),
                          'connected', (select count(*) from sb where sb.idx = l.idx and sb.conn)
                        ) order by l.idx), '[]'::jsonb) from sb_lbl l)
  ),
  'timeOfDay', (
    select jsonb_agg(jsonb_build_object(
        'optIns',   (select count(*) from f where optin_bucket = b),
        'dials',    (select count(*) from f where dial_bucket = b),
        'connects', (select count(*) from f where conn_bucket = b)
      ) order by b)
    from generate_series(0, 11) b
  )
)
$function$;

comment on function dc_ads_funnel(timestamptz, timestamptz, text, text, text, text, text) is
  'DC ads page: cohort funnel + speed-to-dial + time-of-day over dc_ads_lead_facts, anchored at the opt-in. Optional facets AND together: cascade entity (campaign/adset/ad — caller sends deepest only), p_form_id (Meta instant form, 0128), p_funnel_label (acquisition path, 0131).';

-- ----------------------------------------------------- dc_ads_funnel_by_rep --

drop function dc_ads_funnel_by_rep(timestamptz, timestamptz, text, text, text, text);

create function dc_ads_funnel_by_rep(
  p_start timestamptz,
  p_end timestamptz,
  p_campaign_id text default null,
  p_adset_id text default null,
  p_ad_id text default null,
  p_form_id text default null,
  p_funnel_label text default null
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
),
calls as (
  select cc.user_id,
    max(cc.raw_payload ->> 'user_name') as user_name,
    count(*) filter (where cc.direction = 'outbound') as dials,
    count(*) filter (where cc.duration >= 90)         as connections
  from close_calls cc
  join leads l on l.close_id = cc.lead_id
  where cc.activity_at >= p_start and cc.activity_at < p_end
    and cc.user_id is not null
  group by cc.user_id
),
calls_rep as (
  select coalesce(tm.id::text, ca.user_id)                        as rep_key,
         coalesce(tm.full_name, ca.user_name, ca.user_id)         as rep_name,
         sum(ca.dials)::int as dials, sum(ca.connections)::int as connections
  from calls ca
  left join team_members tm on tm.close_user_id = ca.user_id
  group by 1, 2
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
  select s.lead_id, s.closer_record_ids, s.closer_names, s.plans
  from airtable_digital_college_sales s
  join leads l on l.close_id = s.lead_id
  where lower(coalesce(s.closed,'')) = 'yes' and s.excluded_at is null
    and coalesce(s.date_time_of_call, s.airtable_created_at) >= p_start
    and coalesce(s.date_time_of_call, s.airtable_created_at) < p_end
    and (select count(*) from unnest(coalesce(s.plans,'{}'::text[])) p where trim(p) <> '') > 0
),
closes_raw as (
  select t.rid, t.nm, f.lead_id,
    (select count(*) from unnest(coalesce(f.plans,'{}'::text[])) p where trim(p) <> '') as units
  from dc_forms f
  cross join lateral unnest(f.closer_record_ids, f.closer_names) as t(rid, nm)
),
closes_rep as (
  select coalesce(tm.id::text, cr.rid, cr.nm)  as rep_key,
         coalesce(tm.full_name, cr.nm)         as rep_name,
         count(distinct cr.lead_id)::int       as closes,
         (coalesce(sum(cr.units), 0) * 300)::int as cash
  from closes_raw cr
  left join team_members tm on tm.airtable_user_id = cr.rid
  group by 1, 2
),
merged as (
  select
    coalesce(cl.rep_key, co.rep_key)   as rep_key,
    coalesce(cl.rep_name, co.rep_name) as rep_name,
    coalesce(cl.dials, 0)       as dials,
    coalesce(cl.connections, 0) as connections,
    coalesce(co.closes, 0)      as closes,
    coalesce(co.cash, 0)        as cash
  from calls_rep cl
  full outer join closes_rep co on cl.rep_key = co.rep_key
),
plan_units as (
  select p from dc_forms f cross join lateral unnest(coalesce(f.plans,'{}'::text[])) p where trim(p) <> ''
)
select jsonb_build_object(
  'reps', (
    select coalesce(jsonb_agg(jsonb_build_object(
        'rep', rep_name, 'dials', dials, 'connections', connections,
        'closes', closes, 'cash', cash
      ) order by closes desc, cash desc, connections desc, dials desc), '[]'::jsonb)
    from merged where dials > 0 or connections > 0 or closes > 0
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

comment on function dc_ads_funnel_by_rep(timestamptz, timestamptz, text, text, text, text, text) is
  'DC ads page: per-rep dials/connections/closes/cash, ACTIVITY-scoped to [p_start, p_end). Optional facets AND together: cascade entity, p_form_id (0128), p_funnel_label (0131).';

-- ------------------------------------------------------------- dc_ads_daily --

drop function dc_ads_daily(date, int, text, text, text, text);

create function dc_ads_daily(
  p_end_et date,
  p_days int default 5,
  p_campaign_id text default null,
  p_adset_id text default null,
  p_ad_id text default null,
  p_form_id text default null,
  p_funnel_label text default null
)
returns jsonb
language sql
stable
as $function$
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
),
dials as (
  select f.et_day, count(*) as n
  from f join close_calls c on c.lead_id = f.close_id
    and c.activity_at >= f.anchor and c.direction = 'outbound'
  group by f.et_day
)
select coalesce(jsonb_agg(jsonb_build_object(
  'etDate',    d.et_day,
  'optIns',    (select count(*) from f where f.et_day = d.et_day),
  'called',    (select count(*) filter (where any_call or call90 or booked or showed or closed) from f where f.et_day = d.et_day),
  'connected', (select count(*) filter (where call90 or booked or showed or closed) from f where f.et_day = d.et_day),
  'closed',    (select count(*) filter (where closed) from f where f.et_day = d.et_day),
  'cashUsd',   (select coalesce(sum(plan_units), 0) * 300 from f where f.et_day = d.et_day),
  'dials',     coalesce((select n from dials where dials.et_day = d.et_day), 0)
) order by d.et_day desc), '[]'::jsonb)
from days d
$function$;

comment on function dc_ads_daily(date, int, text, text, text, text, text) is
  'DC ads page: the last-N-ET-days cohort strip (opt-ins that day + lifetime progression + dials received). Optional facets AND together: cascade entity, p_form_id (0128), p_funnel_label (0131).';

-- ------------------------------------------------------ dc_ads_speed_cohort --

drop function dc_ads_speed_cohort(timestamptz, timestamptz, text, text, text, text);

create function dc_ads_speed_cohort(
  p_start timestamptz,
  p_end timestamptz,
  p_campaign_id text default null,
  p_adset_id text default null,
  p_ad_id text default null,
  p_form_id text default null,
  p_funnel_label text default null
)
returns jsonb
language sql
stable
as $function$
with f as (
  select * from dc_ads_lead_facts
  where anchor >= p_start and anchor < p_end
    and (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
)
select coalesce(jsonb_agg(jsonb_build_object(
  'anchor',    f.anchor,
  'firstDial', f.first_dial,
  'dials',     coalesce(d.n, 0),
  'connected', (f.call90 or f.booked or f.showed or f.closed)
)), '[]'::jsonb)
from f
left join lateral (
  select count(*) as n from close_calls c
  where c.lead_id = f.close_id and c.direction = 'outbound' and c.activity_at >= f.anchor
) d on true
$function$;

comment on function dc_ads_speed_cohort(timestamptz, timestamptz, text, text, text, text, text) is
  'DC ads page: per-lead timing/effort facts for the speed-to-lead boxes (business-hours math runs in TS). Optional facets AND together: cascade entity, p_form_id (0128), p_funnel_label (0131).';
