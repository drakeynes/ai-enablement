-- 0142_dc_ads_daily_speed_units.sql
--
-- Boss item #19 (2026-08-14): the 30-day daily table shows how fast each
-- day's cohort turns into UNITS — d0 (closed the same ET day as the opt-in),
-- d3 (under 3 ET calendar days, cumulative), d7 (under 7, cumulative). The
-- ROAS variants (dN units × $300 ÷ that day's spend) compute in TS where the
-- per-day spend merge lives. Valid-adjusted like everything since 0141; both
-- form sources, each at its own close timestamp. Signature unchanged.

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
  'dials',     coalesce((select n from dials where dials.et_day = d.et_day), 0)
) order by d.et_day desc), '[]'::jsonb)
from days d
$function$;

comment on function dc_ads_daily(date, int, text, text, text, text, text, text) is
  'DC ads page: the last-N-ET-days cohort table (opt-ins that day + LIFETIME progression + dials received). 0142 adds unitsD0/D3/D7 (valid-adjusted units closed within 0/<3/<7 ET calendar days of the opt-in — cumulative; ROAS variants compute in TS with the per-day spend). Facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132); p_funnel_label deprecated alias.';
