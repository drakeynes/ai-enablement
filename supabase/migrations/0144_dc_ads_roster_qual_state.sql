-- 0144: 3-state qualification + time-to-dial on the DC Ads lead roster
-- (boss batch 2026-08-15, item 5).
--
-- The boss's vocabulary: Qualified ("Yes I can pay for the AI tools") /
-- Unqualified ("No I cannot afford $200...") / Partial (the qualify question
-- was never answered — no completed survey matched, or the matched response
-- skipped the question). "Marketing qualified" = Qualified (his words), not a
-- separate state. tf_qualified alone can't distinguish Unqualified from
-- Partial (false covers both), so:
--
-- 1. dc_ads_lead_facts grows tf_answered: did the lead's matched Typeform
--    response answer the qualify question AT ALL (any label)? Null = no
--    matched response, same convention as tf_qualified.
-- 2. refresh_dc_ads_facts() computes it in tf_resp/tf_match — the ONE home of
--    the response-matching semantics. Also adds NULLS LAST to the
--    newest-response ordering (defensive: today every mirrored response has
--    submitted_at, but if partial responses are ever ingested a null must not
--    beat a real submission).
-- 3. dc_ads_lead_roster() returns firstDial (time-to-dial column) and
--    qualState ('qualified' | 'unqualified' | 'partial') derived from the two
--    flags. Signatures unchanged — CREATE OR REPLACE only.
--
-- Instant-form leads have no Typeform, so they read 'partial' (no completed
-- survey — consistent with the rule); none exist in the current cohort window.

alter table dc_ads_lead_facts add column if not exists tf_answered boolean;

comment on column dc_ads_lead_facts.tf_answered is
  '(0144) The matched Typeform response answered the LP''s qualify question at all (any label). Null = no matched completed response. With tf_qualified: qualified = tf_qualified; unqualified = answered but not qualified; partial = never answered.';

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
  'Rebuilds dc_ads_lead_facts (delete + insert, one transaction). Membership: close_leads on an ACTIVE dc_ads_campaigns row — both acquisition paths. lp_slug: instant_form → ''instant-form''; single-LP campaign → its lp_slug; split-test campaign (>1 lp_slugs) → the LP owning the lead''s matched Typeform, falling back to the primary (0138). tf_qualified: the lead''s own Typeform vs the LP''s qualify rule (0133); tf_answered (0144): that response answered the qualify question at all — with tf_qualified it yields qualified/unqualified/partial. 0141: the DC sale form''s Valid QA verdict applies (No = excluded, partial = kept plan type only).';

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
  'qualified', coalesce(f.tf_qualified, false),
  'qualState', case
                 when coalesce(f.tf_qualified, false) then 'qualified'
                 when coalesce(f.tf_answered, false)  then 'unqualified'
                 else 'partial'
               end,
  'connected', f.call90,
  'hvc',       (f.call90 and (coalesce(f.tf_qualified, false) or f.has_inbound)),
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
  'DC ads page: the embedded lead roster — identity + landing page + dials + firstDial (0144) + stage flags per cohort lead. qualState (0144): qualified = hit the LP''s qualify answer; unqualified = answered the question, missed; partial = never answered it (no completed survey matched, or skipped the question; instant-form leads read partial). Since 0140 connected = call ≥90s only; hvc = call90 AND (qualified OR sms). Newest opt-in first; filtering is client-side. Facets AND together like the sibling RPCs.';

-- Populate tf_answered now (the 15-min cron would get there anyway).
select refresh_dc_ads_facts();
