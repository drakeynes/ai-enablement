-- 0148: the "Non-attributed" pseudo-campaign (boss 2026-08-17).
--
-- ~15% of DC funnel entrants lose their ad tags in transit (unfilled Meta
-- macros, privacy stripping, in-app browsers): the bridge creates their Close
-- lead WITHOUT campaign_id, and campaign_id was the cohort membership key —
-- so real ad leads (118/130 dialed, 11 closed in a recent 30d window) were
-- invisible to the page. The boss confirmed the DC Typeforms exist ONLY on
-- the ad landing pages, so these are ad leads with lost attribution, not
-- organic — he wants them on the page as their own campaign.
--
-- Membership rule (NO identity matching needed — cheap): a campaign-less,
-- non-excluded lead created in the DC LP era whose bridge stamped
-- latest_opt_in_date AND whose funnel_name matches a registered ACTIVE DC
-- campaign's funnel_label ('Aman Funnel' / 'Luke Funnel' / 'Digital College'
-- today — the Zapier stamps funnel_name from its own config, not from URL
-- macros, so it survives tag loss). Non-DC funnels (AI Summer Camp, Closer
-- Funnel) never match. Verified 2026-08-17: 213 such leads since Jul 1, 207
-- on DC funnels.
--
-- They join the cohort under campaign_id 'non-attributed' (pseudo-id, the
-- 'instant-form' pseudo-slug precedent): no adset/ad (they drop out of ad
-- facets + the per-ad table's real rows naturally), source_kind / lp /
-- typeform inherited from the funnel's newest registered campaign. The
-- registry row below puts "Non-attributed" in the campaign dropdown and
-- gives DC Setup a kill switch: deactivate it there and the branch stops
-- matching at the next refresh (leads vanish from the page again).
--
-- If a non-attributed lead later re-opts in through a tagged ad, the bridge
-- stamps the real campaign_id on the SAME Close lead → it moves branches on
-- the next refresh. One row per lead, never double-counted.

insert into dc_ads_campaigns (campaign_id, campaign_name, source_kind, funnel_label, active, last_seen_at)
values ('non-attributed', 'Non-attributed (ad tags lost)', 'landing_page', 'Non-attributed', true, now())
on conflict (campaign_id) do nothing;

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
    source_kind, funnel_label, typeform_id, lp_slug, tf_qualified, tf_answered, updated_at)
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
    union all
    -- Non-attributed branch (0148): bridge-stamped DC leads whose ad tags
    -- were lost — see the header comment for the rule and the kill switch.
    select cl.close_id,
      greatest(cl.date_created, coalesce(cl.latest_opt_in_date, cl.date_created)) as anchor,
      'non-attributed'::text as campaign_id,
      null::text as adset_id,
      null::text as ad_id,
      coalesce(m.source_kind, 'landing_page') as source_kind,
      cl.funnel_name as funnel_label,
      m.typeform_id,
      m.lp_slug as campaign_lp_slug,
      null::text[] as campaign_lp_slugs,
      0 as campaign_lp_count
    from close_leads cl
    left join lateral (
      -- Inherit the funnel's shape from its newest registered campaign.
      select c2.source_kind, c2.typeform_id, c2.lp_slug
      from dc_ads_campaigns c2
      where c2.funnel_label = cl.funnel_name and c2.active
        and c2.campaign_id <> 'non-attributed'
      order by c2.last_seen_at desc nulls last
      limit 1
    ) m on true
    where cl.campaign_id is null
      and cl.excluded_at is null
      and cl.date_created >= timestamptz '2026-07-01'  -- the DC LP era floor
      and cl.latest_opt_in_date is not null            -- the bridge's stamp
      and m.source_kind is not null                    -- funnel must be a registered DC funnel
      and exists (select 1 from dc_ads_campaigns g
                  where g.campaign_id = 'non-attributed' and g.active)
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
  -- qualifying label; answered (0144) = it answered that question at all;
  -- form_id (0138) says WHICH page's form — the split-test attribution key.
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
      ) as qualified,
      exists (
        select 1 from jsonb_array_elements(r.answers) a
        join lp_rules q on q.typeform_id = r.form_id
        where q.qualify_field_ref is not null
          and a->'field'->>'ref' = q.qualify_field_ref
      ) as answered
    from typeform_responses r
    where r.form_id in (select typeform_id from lp_rules)
  ),
  tf_match as (
    select distinct on (m.close_id) m.close_id, m.qualified, m.answered, m.form_id
    from (
      select lp.close_id, r.submitted_at, r.qualified, r.answered, r.form_id
      from lead_phones lp
      join tf_resp r on r.p10 <> '' and r.p10 = lp.p10
      union all
      select le.close_id, r.submitted_at, r.qualified, r.answered, r.form_id
      from lead_emails le
      join tf_resp r on r.em <> '' and r.em = le.em
    ) m
    order by m.close_id, m.submitted_at desc nulls last
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
    tm.answered,
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
  'Rebuilds dc_ads_lead_facts (delete + insert, one transaction). Membership: close_leads on an ACTIVE dc_ads_campaigns row — both acquisition paths — PLUS the non-attributed branch (0148): campaign-less bridge-stamped leads (latest_opt_in_date set, funnel_name = a registered active DC funnel_label, created since the DC LP era) join as campaign_id ''non-attributed'' with no adset/ad; deactivating that registry row in DC Setup switches the branch off. lp_slug: instant_form → ''instant-form''; single-LP campaign → its lp_slug; split-test campaign (>1 lp_slugs) → the LP owning the lead''s matched Typeform, falling back to the primary (0138). tf_qualified: the lead''s own Typeform vs the LP''s qualify rule (0133); tf_answered (0144). 0141: the DC sale form''s Valid QA verdict applies.';

-- Populate immediately (the 15-min cron would get there anyway).
select refresh_dc_ads_facts();
