-- 0145: smsOut + units on the DC Ads lead roster (boss batch 2026-08-15,
-- item 4 — the speed boxes follow the lead-list toggles).
--
-- The page now computes EVERY speed-to-lead number from the roster's per-lead
-- rows (filtered client-side by the stacked toggles), so the roster needs the
-- two fields the retired-from-this-page dc_ads_speed_cohort() had that it
-- didn't: smsOut (any outbound SMS after the opt-in — the SMS-engagement
-- denominator, copied verbatim from 0140's speed cohort) and units
-- (plan_units, Valid-adjusted — the CPU denominator). Body-only CREATE OR
-- REPLACE; signature unchanged.

create or replace function dc_ads_lead_roster(
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
  'firstDial', f.first_dial,
  'sms',       f.has_inbound,
  'smsOut',    exists (
                 select 1 from close_sms s
                 where s.lead_id = f.close_id
                   and s.direction = 'outbound'
                   and s.activity_at >= f.anchor
               ),
  'qualified', coalesce(f.tf_qualified, false),
  'qualState', case
                 when coalesce(f.tf_qualified, false) then 'qualified'
                 when coalesce(f.tf_answered, false)  then 'unqualified'
                 else 'partial'
               end,
  'connected', f.call90,
  'hvc',       (f.call90 and (coalesce(f.tf_qualified, false) or f.has_inbound)),
  'closed',    f.closed,
  'units',     f.plan_units
) order by f.anchor desc), '[]'::jsonb)
from f
join close_leads cl on cl.close_id = f.close_id
left join lateral (
  select count(*) as n from close_calls c
  where c.lead_id = f.close_id and c.direction = 'outbound' and c.activity_at >= f.anchor
) d on true
$function$;

comment on function dc_ads_lead_roster(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: the embedded lead roster — identity + landing page + dials + firstDial (0144) + smsOut/units (0145) + stage flags per cohort lead. Since 0145 this is the ONE per-lead read behind the page''s speed boxes AND lead list (the toggles filter both client-side); dc_ads_speed_cohort() is no longer called by the page. qualState (0144): qualified / unqualified / partial. Since 0140 connected = call ≥90s only; hvc = call90 AND (qualified OR sms). Newest opt-in first. Facets AND together like the sibling RPCs.';
