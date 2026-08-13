-- 0134_dc_ads_daily_stages.sql
--
-- The DC Ads daily cohort table grows the stage-row metrics (0133) and the
-- page stretches it from 5 to 30 days (a scrollable box). Per boss 2026-08-13:
-- Spend · Opt-ins · Qualified · SMS · SMS+MQL · Connects · HVC · Units ·
-- Closed, one row per ET opt-in day.
--
-- Cohort semantics unchanged and load-bearing: each row is the leads that
-- OPTED IN that day. Spend and opt-ins freeze once the day ends; every
-- downstream column is the cohort's LIFETIME progression, so yesterday's SMS /
-- Connects / Units keep climbing on later visits as those leads text back,
-- connect, and close.
--
-- Signature unchanged (8 args, 0132) — body-only replace; the new fields ride
-- alongside the existing ones (called/cashUsd/dials stay in the payload).

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
  'hvc',       (select count(*) filter (where (has_inbound and tf_qualified)
                                           or call90 or booked or showed or closed)
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
  'DC ads page: the last-N-ET-days cohort table (opt-ins that day + LIFETIME progression — downstream columns keep climbing as the cohort progresses — + dials received). 0134 added the stage-row fields (qualified/sms/smsMql/hvc/units). Optional facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132). p_funnel_label is a deprecated alias facet.';
