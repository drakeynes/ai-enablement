-- 0149 — dc_ads_breakdown(): the DC Ads header's "Data breakdown" popover.
--
-- Recurring reconciliation question: a Close pull with the date filter
-- "created OR latest-opt-in on day X" (how ops validates the funnel by hand)
-- reads a few leads higher than the page, and its activity filters (SMS/calls
-- ON day X) read lower than the page's cohort-lifetime stages. The popover
-- pre-answers both. This RPC serves the membership half: the reference count
-- under the Close-style date filter (org-wide, no campaign scoping), the
-- counted cohort, and EVERY gap lead by name with the reason it isn't
-- counted. The time-basis half is static copy in the UI.
--
-- Reasons are derived at read time from the same registry conditions
-- refresh_dc_ads_facts() (0148) uses for membership — no side table, nothing
-- to go stale. If the membership rules change in a future migration, this
-- CASE ladder must change with them (it mirrors the two branches 1:1).
--
-- The reference set partitions exactly: counted (in facts, anchor in window)
-- + moved (in facts, anchor on another day — created in window but re-opted
-- later, so the cohort day moved) + excluded (not in facts, with a reason).
-- 'pending_refresh' covers the freshness skew: a lead that DOES satisfy
-- membership but arrived after the last 15-min facts refresh.

-- date_created has an index since 0043; the OR-of-ranges scan wants its
-- sibling so Postgres can BitmapOr the two.
create index if not exists close_leads_latest_opt_in_idx
  on close_leads (latest_opt_in_date desc);

create or replace function dc_ads_breakdown(p_start timestamptz, p_end timestamptz)
returns jsonb
language sql
stable
as $$
with z as (
  -- The Close-style reference set: created OR re-opted in the window,
  -- across ALL of Close (that is what a hand pull sees — no campaign scope).
  select cl.close_id, cl.display_name, cl.funnel_name, cl.campaign_id,
         cl.marketing_qualified, cl.date_created, cl.latest_opt_in_date,
         cl.excluded_at,
         -- The in-window event the date filter caught (prefer the re-opt).
         case when cl.latest_opt_in_date >= p_start and cl.latest_opt_in_date < p_end
              then cl.latest_opt_in_date else cl.date_created end as caught_at
  from close_leads cl
  where (cl.date_created >= p_start and cl.date_created < p_end)
     or (cl.latest_opt_in_date >= p_start and cl.latest_opt_in_date < p_end)
),
moved as (
  select z.*, f.anchor
  from z join dc_ads_lead_facts f on f.close_id = z.close_id
  where not (f.anchor >= p_start and f.anchor < p_end)
),
missing as (
  select z.*,
    case
      when z.excluded_at is not null then 'manually_excluded'
      when z.campaign_id is not null and exists (
        select 1 from dc_ads_campaigns d
        where d.campaign_id = z.campaign_id and d.active) then 'pending_refresh'
      when z.campaign_id is not null and exists (
        select 1 from dc_ads_campaigns d
        where d.campaign_id = z.campaign_id) then 'inactive_campaign'
      when z.campaign_id is not null then 'stale_campaign'
      -- campaign-less from here: mirror the non-attributed branch's gates
      -- (0148) in order, so the reason is the FIRST gate the lead fails.
      when not exists (
        select 1 from dc_ads_campaigns c2
        where c2.funnel_label = z.funnel_name and c2.active
          and c2.campaign_id <> 'non-attributed') then 'not_ad_lead'
      when z.latest_opt_in_date is null then 'no_optin_stamp'
      when z.date_created < timestamptz '2026-07-01' then 'pre_floor_reopt'
      when not exists (
        select 1 from dc_ads_campaigns g
        where g.campaign_id = 'non-attributed' and g.active) then 'non_attributed_off'
      else 'pending_refresh'
    end as reason
  from z
  where not exists (select 1 from dc_ads_lead_facts f where f.close_id = z.close_id)
)
select jsonb_build_object(
  'reference',   (select count(*) from z),
  'referenceMq', (select count(*) from z where marketing_qualified = 'Yes'),
  -- Counted straight from facts (not via z) so the popover's number can never
  -- drift from the page's opt-in count for the same window.
  'counted',     (select count(*) from dc_ads_lead_facts f
                   where f.anchor >= p_start and f.anchor < p_end),
  'countedMq',   (select count(*) from dc_ads_lead_facts f
                   join close_leads cl on cl.close_id = f.close_id
                   where f.anchor >= p_start and f.anchor < p_end
                     and cl.marketing_qualified = 'Yes'),
  -- Names cap PER REASON (a wide window catches thousands of not_ad_lead
  -- rows — one global cap would starve every other group of names);
  -- excludedByReason carries the true per-group totals for "+N more".
  'excluded', coalesce((
    select jsonb_agg(jsonb_build_object(
        'closeId', ml.close_id,
        'name',    coalesce(nullif(trim(ml.display_name), ''), '(no name)'),
        'reason',  ml.reason,
        'mq',      coalesce(ml.marketing_qualified = 'Yes', false),
        'funnel',  ml.funnel_name,
        'day',     to_char(ml.caught_at at time zone 'America/New_York', 'YYYY-MM-DD')
      ) order by ml.caught_at desc)
    from (
      select *, row_number() over (partition by reason order by caught_at desc) as rn
      from missing) ml
    where ml.rn <= 50), '[]'::jsonb),
  'excludedByReason', coalesce((
    select jsonb_object_agg(g.reason, g.n)
    from (select reason, count(*) as n from missing group by reason) g), '{}'::jsonb),
  'excludedTotal', (select count(*) from missing),
  'moved', coalesce((
    select jsonb_agg(jsonb_build_object(
        'closeId',   mv.close_id,
        'name',      coalesce(nullif(trim(mv.display_name), ''), '(no name)'),
        'mq',        coalesce(mv.marketing_qualified = 'Yes', false),
        'anchorDay', to_char(mv.anchor at time zone 'America/New_York', 'YYYY-MM-DD')
      ) order by mv.anchor desc)
    from (select * from moved order by anchor desc limit 100) mv), '[]'::jsonb),
  'movedTotal', (select count(*) from moved)
)
$$;

comment on function dc_ads_breakdown(timestamptz, timestamptz) is
  'DC Ads page: the header''s Data-breakdown popover. Reference = the Close-style date filter (created OR latest-opt-in in window, org-wide — how ops hand-pulls); counted = the facts cohort (anchor in window); every gap lead returned by name with a reason code mirroring refresh_dc_ads_facts()''s membership gates (0148): manually_excluded / inactive_campaign / stale_campaign / not_ad_lead / no_optin_stamp / pre_floor_reopt / non_attributed_off / pending_refresh, plus moved = counted on another day (re-opt shifted the anchor). Names cap at 50 per reason (excludedByReason carries true group totals); moved caps at 100. No campaign/facet scoping by design.';
