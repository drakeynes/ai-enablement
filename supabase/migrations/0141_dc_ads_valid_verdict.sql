-- 0141_dc_ads_valid_verdict.sql
--
-- The DC sale form's "Valid" QA verdict becomes the sales truth on the DC Ads
-- page (boss 2026-08-14 via Drake): the team marks each Commission-table
-- submission Yes / No / "Has Wix, Missing Base" / "Has Base, Missing Wix" (or
-- leaves it blank), and the numbers obey:
--   blank / Yes            -> count fully (backfill = this rule: history
--                             stays counted until someone marks it)
--   No                     -> the submission doesn't count at all — but the
--                             Airtable record survives as the log
--   Has Wix, Missing Base  -> keep only the Wix unit(s)
--   Has Base, Missing Wix  -> keep only the Base unit(s)
-- A close whose kept units hit 0 degrades to show + marked_no_plan. The RAW
-- data keeps flowing unchanged (plans column untouched; reverting = removing
-- the filter). Live diff at build time: units 159->140 (-11.9%), cash
-- $47,700->$42,000, closes 92->88 — inside the boss's 10-15% estimate.
--
-- The mirror gains the `valid` column (ingestion parser now maps the field,
-- and the DC sale table joined FULL_RESCAN_TABLES — the created-time sync
-- window never re-pulled edited records, so verdicts on old rows would never
-- have arrived). The page also gains a QA audit line (qaInvalidForms /
-- qaExcludedUnits on dc_ads_funnel).

alter table airtable_digital_college_sales
  add column valid text;

comment on column airtable_digital_college_sales.valid is
  'The team''s QA verdict on this submission (Airtable "Valid" single-select): Yes / No / "Has Wix, Missing Base" / "Has Base, Missing Wix" / null. Null counts fully; dc_valid_plans() applies the rest. Synced every tick (full-rescan table).';

-- The one place the verdict semantics live. IMMUTABLE so it inlines cleanly.
create function dc_valid_plans(plans text[], valid text)
returns text[]
language sql
immutable
as $function$
select case
  when valid = 'No' then '{}'::text[]
  when valid = 'Has Wix, Missing Base' then
    coalesce((select array_agg(p) from unnest(coalesce(plans, '{}'::text[])) p
              where trim(p) <> '' and lower(p) not like '%base%'), '{}'::text[])
  when valid = 'Has Base, Missing Wix' then
    coalesce((select array_agg(p) from unnest(coalesce(plans, '{}'::text[])) p
              where trim(p) <> '' and lower(p) not like '%wix%'), '{}'::text[])
  else
    coalesce((select array_agg(p) from unnest(coalesce(plans, '{}'::text[])) p
              where trim(p) <> ''), '{}'::text[])
end
$function$;

comment on function dc_valid_plans(text[], text) is
  'The DC sale form''s Valid verdict -> which plan units count (0141). Blank/Yes = all non-blank plans; No = none; partial verdicts drop the named-missing plan type. Used by refresh_dc_ads_facts + dc_ads_funnel_by_rep + the funnel''s QA audit counts.';

create or replace function refresh_dc_ads_facts()
returns integer
language plpgsql
as $function$
declare
  v_count int;
begin
  delete from dc_ads_lead_facts where true;

  insert into dc_ads_lead_facts (
    close_id, anchor, first_reply, has_inbound, any_call, call90, first_dial,
    booked, booked_dc, booked_ht, showed, closed,
    plan_units, base44_monthly, base44_yearly, wix_monthly, wix_yearly, marked_no_plan,
    optin_bucket, dial_bucket, conn_bucket, campaign_id, adset_id, ad_id, form_id,
    source_kind, funnel_label, typeform_id, lp_slug, tf_qualified, updated_at)
  with leads_base as (
    select cl.close_id,
      -- Anchor at the DC-campaign opt-in: the Meta→Close bridge matches
      -- returning phone numbers to their EXISTING Close lead and re-stamps
      -- latest_opt_in_date — date_created alone would anchor those leads at
      -- their original (pre-campaign) creation. greatest() also covers new
      -- leads, whose latest_opt_in_date is minute-truncated slightly BEFORE
      -- date_created.
      greatest(cl.date_created, coalesce(cl.latest_opt_in_date, cl.date_created)) as anchor,
      cl.campaign_id, cl.adset_id, cl.ad_id,
      dc.source_kind,
      coalesce(cl.funnel_name, dc.funnel_label) as funnel_label,
      dc.typeform_id,
      dc.lp_slug as campaign_lp_slug,
      dc.lp_slugs as campaign_lp_slugs,
      coalesce(cardinality(dc.lp_slugs), 0) as campaign_lp_count
    from close_leads cl
    join dc_ads_campaigns dc
      on dc.campaign_id = cl.campaign_id and dc.active
    where cl.excluded_at is null
  ),
  -- Which Meta form each lead came through, by phone identity (0128). Only
  -- instant_form leads can match — landing_page leads never submit a Meta form.
  lead_phones as (
    select l.close_id,
      right(regexp_replace(ph->>'phone', '[^0-9]', '', 'g'), 10) as p10
    from leads_base l
    join close_leads cl on cl.close_id = l.close_id
    cross join lateral jsonb_array_elements(coalesce(cl.contacts, '[]'::jsonb)) c
    cross join lateral jsonb_array_elements(coalesce(c->'phones', '[]'::jsonb)) ph
    where coalesce(ph->>'phone', '') <> ''
  ),
  lead_emails as (
    select l.close_id, lower(trim(em->>'email')) as em
    from leads_base l
    join close_leads cl on cl.close_id = l.close_id
    cross join lateral jsonb_array_elements(coalesce(cl.contacts, '[]'::jsonb)) c
    cross join lateral jsonb_array_elements(coalesce(c->'emails', '[]'::jsonb)) em
    where coalesce(em->>'email', '') <> ''
  ),
  form_match as (
    select distinct on (lp.close_id) lp.close_id, m.form_id
    from lead_phones lp
    join meta_form_leads m
      on right(regexp_replace(m.phone_number, '[^0-9]', '', 'g'), 10) = lp.p10
    order by lp.close_id, m.created_time desc
  ),
  -- The lead's own DC Typeform submission (0133): responses on the registered
  -- DC forms, identity from the answers (Aman) falling back to hidden fields
  -- (Luke). qualified = the response answered the LP's qualify question with a
  -- qualifying label; form_id (0138) says WHICH page's form — the split-test
  -- attribution key.
  lp_rules as (
    select typeform_id, qualify_field_ref, qualify_answers
    from dc_landing_pages
    where typeform_id is not null
  ),
  tf_resp as (
    select r.form_id, r.submitted_at,
      right(regexp_replace(coalesce(
        (select a->>'phone_number' from jsonb_array_elements(r.answers) a
          where a->>'type' = 'phone_number' limit 1),
        r.hidden->>'phone', ''), '[^0-9]', '', 'g'), 10) as p10,
      lower(trim(coalesce(
        (select a->>'email' from jsonb_array_elements(r.answers) a
          where a->>'type' = 'email' limit 1),
        r.hidden->>'email', ''))) as em,
      exists (
        select 1 from jsonb_array_elements(r.answers) a
        join lp_rules q on q.typeform_id = r.form_id
        where a->>'type' = 'choice'
          and q.qualify_field_ref is not null
          and a->'field'->>'ref' = q.qualify_field_ref
          and a->'choice'->>'label' = any(q.qualify_answers)
      ) as qualified
    from typeform_responses r
    where r.form_id in (select typeform_id from lp_rules)
  ),
  tf_match as (
    select distinct on (m.close_id) m.close_id, m.qualified, m.form_id
    from (
      select lp.close_id, r.submitted_at, r.qualified, r.form_id
      from lead_phones lp
      join tf_resp r on r.p10 <> '' and r.p10 = lp.p10
      union all
      select le.close_id, r.submitted_at, r.qualified, r.form_id
      from lead_emails le
      join tf_resp r on r.em <> '' and r.em = le.em
    ) m
    order by m.close_id, m.submitted_at desc
  ),
  leads as (
    select lb.*,
      case
        when lb.source_kind = 'instant_form' then 'instant-form'
        when lb.campaign_lp_count <= 1 then lb.campaign_lp_slug
        else coalesce(
          (select dlp.slug from dc_landing_pages dlp
             where dlp.typeform_id = tm.form_id
               and dlp.slug = any(lb.campaign_lp_slugs)
             limit 1),
          lb.campaign_lp_slug)
      end as lp_slug
    from leads_base lb
    left join tf_match tm on tm.close_id = lb.close_id
  ),
  sms as (
    select l.close_id,
      min(s.activity_at) filter (where s.direction='inbound') as first_reply,
      bool_or(s.direction='inbound') as has_inbound
    from leads l join close_sms s on s.lead_id=l.close_id and s.activity_at >= l.anchor
    group by l.close_id
  ),
  calls as (
    select l.close_id, true as any_call, bool_or(c.duration>=90) as call90,
      min(c.activity_at) as earliest_call,
      min(c.activity_at) filter (where c.duration>=90) as earliest_call90,
      -- Ad opt-in IS the hand-raise: first outbound dial after the opt-in,
      -- no replied-first precondition (unlike outbound).
      min(c.activity_at) filter (where c.direction='outbound') as first_dial
    from leads l join close_calls c on c.lead_id=l.close_id and c.activity_at >= l.anchor
    group by l.close_id
  ),
  triage as (
    select l.close_id,
      bool_or(lower(t.call_status) like '%booking%') as booked,
      bool_or(lower(t.call_status) like '%digital college booking%') as booked_dc,
      bool_or(lower(t.call_status) like '%high ticket booking%') as booked_ht
    from leads l join airtable_setter_triage_calls t on t.lead_id=l.close_id
      and t.excluded_at is null and t.airtable_created_at >= l.anchor
    group by l.close_id
  ),
  cforms as (
    select l.close_id, f.dc_plans as plans,
      case when f.form_type='New'
        then (select count(*) from unnest(coalesce(f.dc_plans,'{}'::text[])) p where trim(p)<>'') > 0
        else lower(coalesce(f.closed,''))='yes' and lower(coalesce(f.payment_plan_type,'')) ~ 'base|wix|digital college'
      end as is_close,
      case when f.form_type='New'
        then coalesce(f.call_outcome,'')<>'' and lower(f.call_outcome) !~ 'ghost|no show|reschedul|cancel'
        else lower(coalesce(f.showed,''))='yes'
      end as is_showed,
      (f.form_type='New'
        and (select count(*) from unnest(coalesce(f.dc_plans,'{}'::text[])) p where trim(p)<>'') = 0
        and lower(coalesce(f.call_outcome,'')) like '%digital college%') as marked_no_plan
    from leads l join airtable_full_closer_report f on f.lead_id=l.close_id and f.airtable_created_at >= l.anchor
  ),
  -- The DC sale form: one row per pitch on these dial-up leads. A filed form
  -- = showed; Closed?=Yes needs >=1 plan to be a close (no-plan Yes = show +
  -- marked_no_plan). Blank rows are Airtable artifacts, not pitches.
  -- Valid QA verdict (0141): 'No' forms are excluded entirely; partial
  -- verdicts keep only the verified plan type (dc_valid_plans). A close whose
  -- kept plans hit 0 degrades to show + marked_no_plan.
  dcsale as (
    select l.close_id, dc_valid_plans(s.plans, s.valid) as plans,
      (lower(coalesce(s.closed,''))='yes'
        and cardinality(dc_valid_plans(s.plans, s.valid)) > 0) as is_close,
      true as is_showed,
      (lower(coalesce(s.closed,''))='yes'
        and cardinality(dc_valid_plans(s.plans, s.valid)) = 0) as marked_no_plan
    from leads l join airtable_digital_college_sales s
      on s.lead_id = l.close_id and s.excluded_at is null
      and coalesce(s.valid,'') <> 'No'
      and coalesce(s.date_time_of_call, s.airtable_created_at) >= l.anchor
    where coalesce(s.closed,'') <> ''
       or coalesce(s.prospect_name,'') <> ''
       or (select count(*) from unnest(coalesce(s.plans,'{}'::text[])) p where trim(p)<>'') > 0
  ),
  allforms as (
    select close_id, plans, is_close, is_showed, marked_no_plan from cforms
    union all
    select close_id, plans, is_close, is_showed, marked_no_plan from dcsale
  ),
  closer as (
    select close_id, bool_or(is_showed) as showed, bool_or(is_close) as closed,
      count(*) filter (where marked_no_plan) as marked_no_plan
    from allforms group by close_id
  ),
  plan_per_lead as (
    select af.close_id,
      sum((lower(p) like '%base%' and lower(p) like '%month%')::int) as b44m,
      sum((lower(p) like '%base%' and (lower(p) like '%year%' or lower(p) like '%annual%'))::int) as b44y,
      sum((lower(p) like '%wix%'  and lower(p) like '%month%')::int) as wixm,
      sum((lower(p) like '%wix%'  and (lower(p) like '%year%' or lower(p) like '%annual%'))::int) as wixy
    from allforms af cross join lateral unnest(coalesce(af.plans,'{}'::text[])) p
    where af.is_close group by af.close_id
  )
  select l.close_id, l.anchor,
    sm.first_reply, coalesce(sm.has_inbound,false),
    coalesce(ca.any_call,false), coalesce(ca.call90,false), ca.first_dial,
    coalesce(tr.booked,false), coalesce(tr.booked_dc,false), coalesce(tr.booked_ht,false),
    coalesce(cl.showed,false), coalesce(cl.closed,false),
    coalesce(pp.b44m,0)+coalesce(pp.b44y,0)+coalesce(pp.wixm,0)+coalesce(pp.wixy,0),
    coalesce(pp.b44m,0), coalesce(pp.b44y,0), coalesce(pp.wixm,0), coalesce(pp.wixy,0),
    coalesce(cl.marked_no_plan,0),
    floor(extract(hour from (l.anchor at time zone 'America/New_York'))/2)::smallint,
    case when ca.first_dial is not null then floor(extract(hour from (ca.first_dial at time zone 'America/New_York'))/2)::smallint end,
    case when coalesce(ca.call90,false) then floor(extract(hour from (coalesce(ca.earliest_call90, ca.earliest_call) at time zone 'America/New_York'))/2)::smallint end,
    l.campaign_id, l.adset_id, l.ad_id, fm.form_id,
    l.source_kind, l.funnel_label, l.typeform_id, l.lp_slug,
    tm.qualified,
    now()
  from leads l
  left join form_match fm on fm.close_id=l.close_id
  left join tf_match tm on tm.close_id=l.close_id
  left join sms sm on sm.close_id=l.close_id
  left join calls ca on ca.close_id=l.close_id
  left join triage tr on tr.close_id=l.close_id
  left join closer cl on cl.close_id=l.close_id
  left join plan_per_lead pp on pp.close_id=l.close_id;

  get diagnostics v_count = row_count;
  return v_count;
end $function$;

comment on function refresh_dc_ads_facts() is
  'Rebuilds dc_ads_lead_facts (delete + insert, one transaction). Membership: close_leads on an ACTIVE dc_ads_campaigns row — both acquisition paths. lp_slug: instant_form → ''instant-form''; single-LP campaign → its lp_slug; split-test campaign (>1 lp_slugs) → the LP owning the lead''s matched Typeform, falling back to the primary (0138). tf_qualified: the lead''s own Typeform vs the LP''s qualify rule (0133). 0141: the DC sale form''s Valid QA verdict applies (No = excluded, partial = kept plan type only).';

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
    count(*) filter (where cc.duration >= 90)         as connections
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
         sum(ca.dials)::int as dials, sum(ca.connections)::int as connections
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
        'dials', dials, 'connections', connections, 'shows', shows,
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
  'DC ads page: per-rep talent detail (dials/connections/shows/closes/units/plan splits/cash + teamMemberId), ACTIVITY-scoped to [p_start, p_end) over the DC ad cohort. Shows use the facts refresh''s is_showed semantics; Valid=''No'' forms are excluded and partial verdicts keep only the verified plan type (0141); a multi-closer form credits every closer while the totals count deals once. Facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132); p_funnel_label deprecated alias.';

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
    call90 as connected,  -- calls only (0140) — no form fallback
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
                       where call90 and (tf_qualified or has_inbound)),
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
    'markedNoPlan', (select coalesce(sum(marked_no_plan),0) from f),
    -- The Valid QA audit line (0141): submissions the team marked invalid,
    -- and closed-form units the verdicts excluded — over this cohort's leads.
    'qaInvalidForms', (select count(*)
        from airtable_digital_college_sales s
        join (select distinct close_id from f) fl on fl.close_id = s.lead_id
        where s.excluded_at is null and s.valid = 'No'),
    'qaExcludedUnits', (select coalesce(sum(
          (select count(*) from unnest(coalesce(s.plans,'{}'::text[])) p where trim(p) <> '')
          - cardinality(dc_valid_plans(s.plans, s.valid))), 0)
        from airtable_digital_college_sales s
        join (select distinct close_id from f) fl on fl.close_id = s.lead_id
        where s.excluded_at is null and lower(coalesce(s.closed,'')) = 'yes')
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
  'DC ads page: the stage row + speed-to-dial + time-of-day over dc_ads_lead_facts. Since 0140 connected = call ≥90s ONLY (no form fallback — Nabeel, reduce human error) and hvc = call90 AND (qualified OR texted-us) ⊆ connected. Facets AND together: cascade entity, p_form_id (0128), p_lp_slug (0132); p_funnel_label deprecated alias. 0141: closes/units/cash honor the DC sale form''s Valid QA verdict; qaInvalidForms/qaExcludedUnits feed the page''s audit line.';

-- Re-stamp facts (valid is null until the next sync backfills it — blank
-- counts, so numbers are unchanged until verdicts arrive).
select refresh_dc_ads_facts();
