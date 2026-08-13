-- 0135_dc_ads_speed_sms.sql
--
-- The DC Ads speed-to-lead boxes gain an SMS ENGAGEMENT RATE (boss
-- 2026-08-13): of the cohort leads we actually texted (any outbound SMS after
-- the opt-in), how many texted back. Denominator = texted, not the whole
-- cohort — same never-touched-leads-don't-dilute rule as the connected rate
-- (Drake 2026-06-18). Live 2026-08-13: 561 / 1,914 texted ≈ 29% (2,016
-- cohort — ~95% get the auto-text, so the two denominators sit close).
--
-- dc_ads_speed_cohort() rows gain smsIn (facts.has_inbound — an inbound SMS
-- after the opt-in) and smsOut (any outbound SMS after the opt-in, read live
-- from close_sms like the dial count). Signature unchanged — body-only.

create or replace function dc_ads_speed_cohort(
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
  'anchor',    f.anchor,
  'firstDial', f.first_dial,
  'dials',     coalesce(d.n, 0),
  'connected', (f.call90 or f.booked or f.showed or f.closed),
  'smsIn',     f.has_inbound,
  'smsOut',    exists (
                 select 1 from close_sms s
                 where s.lead_id = f.close_id
                   and s.direction = 'outbound'
                   and s.activity_at >= f.anchor
               )
)), '[]'::jsonb)
from f
left join lateral (
  select count(*) as n from close_calls c
  where c.lead_id = f.close_id and c.direction = 'outbound' and c.activity_at >= f.anchor
) d on true
$function$;

comment on function dc_ads_speed_cohort(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: per-lead timing/effort facts for the speed-to-lead boxes (business-hours math runs in TS — 12p–12a ET clock on this page since 0135) + smsIn/smsOut for the SMS engagement rate. Optional facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132). p_funnel_label is a deprecated alias facet.';
