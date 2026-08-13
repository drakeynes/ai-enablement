-- 0133_dc_ads_stage_row.sql
--
-- The DC Ads page's stage row becomes the boss's nine numbers (2026-08-13):
--   Adspend > Opt-ins > Qualified > SMS > SMS+MQL > Connects > HVC > Units > Closed
-- NOT a funnel — the stages are not subsets of each other and no monotonic
-- decline is implied; the page just puts the numbers side by side. The cohort
-- itself (dc_ads_lead_facts membership, anchoring, filters) is unchanged —
-- everything here derives from the same per-lead facts.
--
-- New per-lead fact: tf_qualified — did the lead's own Typeform submission
-- qualify? ⚠ The DC forms carry NO "$2,000+" budget question (checked live
-- 2026-08-13 across all 863 + 65 responses — the HT budget question simply
-- isn't on these forms). The only qualifying discriminator both forms share
-- is the affordability question:
--     "Yes I can pay for the AI tools"        → qualified
--     "No I cannot afford $200 right now…"    → not qualified
-- The rule lives on dc_landing_pages (qualify_field_ref + qualify_answers,
-- same convention as the HT landing_page_forms) so changing it is a registry
-- edit, not a migration.
--
-- Response→lead identity: the Aman form carries phone+email as ANSWERS
-- (847/863), Luke's carries them as HIDDEN fields (65/65, passed through
-- from the opt-in page) — the matcher reads both, newest response wins,
-- same last-10-digit phone rule as the 0128 instant-form matcher.
--
-- Stage definitions (all over the filtered facts cohort):
--   qualified  tf_qualified
--   sms        has_inbound (an inbound SMS after the opt-in — 0123)
--   smsMql     has_inbound AND tf_qualified
--   connects   the existing Connected roll (call ≥90s or a later stage)
--   hvc        smsMql OR connects ("high-value connect")
--   units      sum(plan_units) (cash = units × $300)

-- ------------------------------------------------------- qualify rules ------

alter table dc_landing_pages
  add column qualify_field_ref text,
  add column qualify_answers text[] not null default '{}';

comment on column dc_landing_pages.qualify_field_ref is
  'The Typeform field ref of this LP''s qualification question (same convention as landing_page_forms.qualify_field_ref). Null = no qualification rule; leads through this LP count as unqualified.';
comment on column dc_landing_pages.qualify_answers is
  'Choice labels on qualify_field_ref that count as QUALIFIED. The DC forms have no $2k budget question — the shared discriminator is the affordability question (''Yes I can pay for the AI tools'').';

update dc_landing_pages set
  qualify_field_ref = 'c8100c75-dc17-41cb-b81b-7eb4165ced40',
  qualify_answers = array['Yes I can pay for the AI tools']
where slug = 'join-training';

update dc_landing_pages set
  qualify_field_ref = 'fa0c4c34-07aa-4598-91bd-886cbaa5b999',
  qualify_answers = array['Yes I can pay for the AI tools']
where slug = 'go';

-- ------------------------------------------------------------ facts column --

alter table dc_ads_lead_facts
  add column tf_qualified boolean;

comment on column dc_ads_lead_facts.tf_qualified is
  'The lead''s own Typeform submission hit a qualify answer (dc_landing_pages.qualify_field_ref/qualify_answers), matched by phone/email, newest response wins. Null = no matched response (instant-form leads always null). The stage row''s Qualified / SMS+MQL / HVC counts.';

-- ------------------------------------------------------------------ refresh --
-- Same body as 0132 plus lead_emails / tf_resp / tf_match CTEs and the
-- tf_qualified stamp.

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
  with leads as (
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
      case when dc.source_kind = 'instant_form' then 'instant-form' else dc.lp_slug end as lp_slug
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
    from leads l
    join close_leads cl on cl.close_id = l.close_id
    cross join lateral jsonb_array_elements(coalesce(cl.contacts, '[]'::jsonb)) c
    cross join lateral jsonb_array_elements(coalesce(c->'phones', '[]'::jsonb)) ph
    where coalesce(ph->>'phone', '') <> ''
  ),
  lead_emails as (
    select l.close_id, lower(trim(em->>'email')) as em
    from leads l
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
  -- (Luke — the opt-in page passes phone/email through). qualified = the
  -- response answered the LP's qualify question with a qualifying label.
  lp_rules as (
    select typeform_id, qualify_field_ref, qualify_answers
    from dc_landing_pages
    where typeform_id is not null
  ),
  tf_resp as (
    select r.submitted_at,
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
    select distinct on (m.close_id) m.close_id, m.qualified
    from (
      select lp.close_id, r.submitted_at, r.qualified
      from lead_phones lp
      join tf_resp r on r.p10 <> '' and r.p10 = lp.p10
      union all
      select le.close_id, r.submitted_at, r.qualified
      from lead_emails le
      join tf_resp r on r.em <> '' and r.em = le.em
    ) m
    order by m.close_id, m.submitted_at desc
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
  dcsale as (
    select l.close_id, s.plans,
      (lower(coalesce(s.closed,''))='yes'
        and (select count(*) from unnest(coalesce(s.plans,'{}'::text[])) p where trim(p)<>'') > 0) as is_close,
      true as is_showed,
      (lower(coalesce(s.closed,''))='yes'
        and (select count(*) from unnest(coalesce(s.plans,'{}'::text[])) p where trim(p)<>'') = 0) as marked_no_plan
    from leads l join airtable_digital_college_sales s
      on s.lead_id = l.close_id and s.excluded_at is null
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
  'Rebuilds dc_ads_lead_facts (delete + insert, one transaction). Membership: close_leads on a campaign in dc_ads_campaigns (active), not excluded — BOTH acquisition paths. 0132 stamps lp_slug; 0133 stamps tf_qualified (the lead''s own Typeform submission vs the LP''s qualify rule, matched by phone/email).';

-- --------------------------------------------------------------- funnel RPC --
-- Signature unchanged (8 args, 0132) — the funnel object gains the stage-row
-- fields: qualified / sms / smsMql / hvc / units. connected stays the
-- Connects number; called/booked/showed remain for the page's other sections.

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
                       where (has_inbound and tf_qualified)
                          or call90 or booked or showed or closed),
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
  'DC ads page: the stage row (optIns/qualified/sms/smsMql/connected/hvc/units/closed — NOT monotonic) + speed-to-dial + time-of-day over dc_ads_lead_facts, anchored at the opt-in. Optional facets AND together: cascade entity (deepest only), p_form_id (0128), p_lp_slug (0132). p_funnel_label is a deprecated alias facet.';

-- Stamp tf_qualified on the existing facts immediately.
select refresh_dc_ads_facts();
