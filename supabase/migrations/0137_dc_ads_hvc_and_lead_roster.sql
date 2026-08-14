-- 0137_dc_ads_hvc_and_lead_roster.sql
--
-- 1. HVC corrected (Drake 2026-08-14, boss's real definition): a CONNECT that
--    was either marketing-qualified or texted us —
--        hvc = connected AND (tf_qualified OR has_inbound)
--    so HVC can never exceed Connects. (0133 had OR-shaped logic where an
--    unconnected qualified texter counted — mis-relayed definition.)
--    Connected stays call-only (the ≥90s/later-stage roll — SMS never makes a
--    lead "connected").
--
-- 2. dc_ads_lead_roster() — the Leads-page roster scoped to DC ad leads, for
--    the DC Ads page's embedded lead list (search + disposition toggles filter
--    IN PLACE, no navigation). One row per cohort lead with identity (display
--    name / first phone / first email — the search keys), landing page, dial
--    count, and the disposition flags (sms / connected / hvc / closed);
--    the display disposition (Closed > HVC > Connected > SMS > Opt-in) is
--    derived in TS. Same 8-arg window+facet signature as the other page RPCs.

create or replace function dc_ads_funnel(
  p_start timestamptz default null,
  p_end timestamptz default null,
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
  where (p_start is null or anchor >= p_start)
    and (p_end is null or anchor < p_end)
    and (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
    and (p_lp_slug is null or lp_slug = p_lp_slug)
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
    'qualified',    (select count(*) from f where tf_qualified),
    'sms',          (select count(*) from f where has_inbound),
    'smsMql',       (select count(*) from f where has_inbound and tf_qualified),
    'hvc',          (select count(*) from f
                       where (call90 or booked or showed or closed)
                         and (tf_qualified or has_inbound)),
    'units',        (select coalesce(sum(plan_units),0) from f),
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

comment on function dc_ads_funnel(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: the stage row (optIns/qualified/sms/smsMql/connected/hvc/units/closed — NOT monotonic, but hvc ⊆ connected since 0137: hvc = connected AND (qualified OR texted-us)) + speed-to-dial + time-of-day over dc_ads_lead_facts, anchored at the opt-in. Optional facets AND together: cascade entity (deepest only), p_form_id (0128), p_lp_slug (0132). p_funnel_label is a deprecated alias facet.';

create or replace function dc_ads_daily(
  p_end_et date,
  p_days int default 5,
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
)
select coalesce(jsonb_agg(jsonb_build_object(
  'etDate',    d.et_day,
  'optIns',    (select count(*) from f where f.et_day = d.et_day),
  'qualified', (select count(*) filter (where tf_qualified) from f where f.et_day = d.et_day),
  'sms',       (select count(*) filter (where has_inbound) from f where f.et_day = d.et_day),
  'smsMql',    (select count(*) filter (where has_inbound and tf_qualified) from f where f.et_day = d.et_day),
  'hvc',       (select count(*) filter (where (call90 or booked or showed or closed)
                                          and (tf_qualified or has_inbound))
                  from f where f.et_day = d.et_day),
  'units',     (select coalesce(sum(plan_units), 0) from f where f.et_day = d.et_day),
  'called',    (select count(*) filter (where any_call or call90 or booked or showed or closed) from f where f.et_day = d.et_day),
  'connected', (select count(*) filter (where call90 or booked or showed or closed) from f where f.et_day = d.et_day),
  'closed',    (select count(*) filter (where closed) from f where f.et_day = d.et_day),
  'cashUsd',   (select coalesce(sum(plan_units), 0) * 300 from f where f.et_day = d.et_day),
  'dials',     coalesce((select n from dials where dials.et_day = d.et_day), 0)
) order by d.et_day desc), '[]'::jsonb)
from days d
$function$;

comment on function dc_ads_daily(date, int, text, text, text, text, text, text) is
  'DC ads page: the last-N-ET-days cohort table (opt-ins that day + LIFETIME progression + dials received). hvc = connected AND (qualified OR texted-us) since 0137. Optional facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132). p_funnel_label is a deprecated alias facet.';

-- --------------------------------------------------------------- roster -----

create function dc_ads_lead_roster(
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
  where anchor >= p_start and anchor < p_end
    and (p_campaign_id is null or campaign_id = p_campaign_id)
    and (p_adset_id is null or adset_id = p_adset_id)
    and (p_ad_id is null or ad_id = p_ad_id)
    and (p_form_id is null or form_id = p_form_id)
    and (p_funnel_label is null or funnel_label = p_funnel_label)
    and (p_lp_slug is null or lp_slug = p_lp_slug)
)
select coalesce(jsonb_agg(jsonb_build_object(
  'closeId',   f.close_id,
  'name',      coalesce(nullif(trim(cl.display_name), ''), '(no name)'),
  'phone',     cl.contacts->0->'phones'->0->>'phone',
  'email',     cl.contacts->0->'emails'->0->>'email',
  'anchor',    f.anchor,
  'lpSlug',    f.lp_slug,
  'dials',     coalesce(d.n, 0),
  'sms',       f.has_inbound,
  'qualified', coalesce(f.tf_qualified, false),
  'connected', (f.call90 or f.booked or f.showed or f.closed),
  'hvc',       ((f.call90 or f.booked or f.showed or f.closed)
                 and (coalesce(f.tf_qualified, false) or f.has_inbound)),
  'closed',    f.closed
) order by f.anchor desc), '[]'::jsonb)
from f
join close_leads cl on cl.close_id = f.close_id
left join lateral (
  select count(*) as n from close_calls c
  where c.lead_id = f.close_id and c.direction = 'outbound' and c.activity_at >= f.anchor
) d on true
$function$;

comment on function dc_ads_lead_roster(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: the embedded lead roster — one row per cohort lead with identity (display name / first phone / first email), landing page, dials received, and disposition flags (sms=texted us, connected=call roll, hvc=connected AND (qualified OR sms), closed). Newest opt-in first; search/toggle filtering happens client-side. Facets AND together like the sibling RPCs.';
