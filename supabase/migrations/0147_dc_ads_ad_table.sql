-- 0147: the per-ad table (boss batch 2026-08-15, item 10).
--
-- Four pieces:
--   1. dc_ads_lead_facts (ad_id) index — the per-ad group-by + ad facet were
--      the only unindexed access path.
--   2. dc_meta_ads gains campaign_name / adset_name — the ad table's
--      campaign + ad-set dropdowns read them straight from the registry (the
--      /ads scan already fetches campaign{name}; adset{name} joins the field
--      list in the same deploy).
--   3. dc_ads_lead_roster() returns adId — the page groups its per-lead rows
--      by ad to compute each ad's speed-to-lead block in TS (same clock, same
--      math as the daily table's speed columns).
--   4. dc_ads_ad_table(): one row per ad over the window+facets — the daily
--      table's stage + D0/D3/D7 semantics, GROUP BY ad instead of ET day.
--      Spend/impressions/CTR merge in TS from cortana_ad_daily; registry ads
--      with spend but zero leads merge in TS too (they have no facts rows).

create index if not exists dc_ads_lead_facts_ad_idx on dc_ads_lead_facts (ad_id);

alter table dc_meta_ads add column if not exists campaign_name text;
alter table dc_meta_ads add column if not exists adset_name text;

comment on column dc_meta_ads.campaign_name is '(0147) Meta campaign name at last scan — the ad table''s campaign dropdown label.';
comment on column dc_meta_ads.adset_name is '(0147) Meta ad-set name at last scan — the ad table''s ad-set dropdown label.';

-- 3. roster + adId (body-only; signature unchanged — 0140/0144/0145 lineage).
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
  'adId',      f.ad_id,
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
  'DC ads page: the embedded lead roster — identity + landing page + adId (0147) + dials + firstDial (0144) + smsOut/units (0145) + stage flags per cohort lead. The ONE per-lead read behind the page''s speed boxes, lead list, AND the per-ad speed block (grouped by adId in TS). qualState (0144): qualified / unqualified / partial. Since 0140 connected = call ≥90s only. Newest opt-in first. Facets AND together like the sibling RPCs.';

-- 4. per-ad aggregates over the window+facets.
create or replace function dc_ads_ad_table(
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
  'dials',     coalesce((select n from dials d where d.ad_id is not distinct from a.ad_id), 0)
) order by a.opt_ins desc), '[]'::jsonb)
from agg a
$function$;

comment on function dc_ads_ad_table(timestamptz, timestamptz, text, text, text, text, text, text) is
  'DC ads page: one row per AD over the window+facets (0147) — the daily table''s stage + unitsD0/D3/D7 semantics grouped by ad instead of ET day (valid-adjusted, both form sources, each lead''s DN window relative to its own opt-in day). Spend/impressions/CTR and the registry identity (dc_meta_ads) merge in TS; ads with spend but zero leads never appear here (no facts rows) — the TS layer adds them. adId can be null for untagged historical leads (one "(untagged)" bucket row). Facets AND together like the sibling RPCs.';
