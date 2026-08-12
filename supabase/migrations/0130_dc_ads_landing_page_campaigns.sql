-- 0130_dc_ads_landing_page_campaigns.sql
--
-- The DC ads funnel grew a SECOND acquisition path and the page never learned
-- about it. Since 2026-07-22 the live Digital College motion is:
--   Meta ad → LANDING PAGE (join.digitalcollege.ai/training, go.digitalcollege.ai)
--   → Typeform → Close → reps dial
-- rather than the original Meta instant form. Landing-page campaigns are
-- OFFSITE_CONVERSIONS/UNDEFINED, so the instant-form discriminator
-- (optimization_goal=LEAD_GENERATION + destination_type=ON_AD) never puts them
-- in meta_leadgen_campaigns — and refresh_dc_ads_facts() gated membership on
-- exactly that set, AND on funnel_name='Digital College'. Both clauses excluded
-- the new traffic, so the page has been reporting a PAUSED campaign only.
--
-- Measured on 2026-08-12 (live):
--   07/25 | Aman TY Vsl | DC funnel   (ACTIVE)  650 close_leads  $10,193 spend
--   08/03 | Luke Direct Form | DC funnel        133 close_leads  $ 1,402 spend
--   07/24 | Aman TY Vsl | DC funnel              18 close_leads  $   626 spend
--   07/08 | ... | LeadForm (legacy, PAUSED)    1,169 close_leads  $ 5,303 spend
-- ⇒ 801 leads and ~$12.2k of DC spend invisible; the only visible campaign dead.
--
-- Close tags the new traffic funnel_name='Aman Funnel' / 'Luke Funnel' (never
-- 'Digital College'), so the funnel_name clause is dropped: campaign membership
-- is the precise signal, and it is what keeps the unrelated ANDROMEDA / Closer
-- Funnel campaigns (~$13.4k, pointing at theaipartner.io) off this page. Do NOT
-- reinstate a blanket OFFSITE_CONVERSIONS rule — it would sweep those in.
--
-- Attribution is 100% complete on close_leads for all four campaigns
-- (campaign_id/adset_id/ad_id), so membership rides Close, not Typeform —
-- Typeform hidden-field attribution is only 81% on the Aman form and 0% on
-- Luke's, so it is enrichment, never the key.
--
-- Facet: dc_ads_lead_facts gains source_kind ('instant_form'|'landing_page'),
-- funnel_label (the Close funnel_name — 'Aman Funnel'/'Luke Funnel'/'Digital
-- College') and typeform_id, so the page can split the paths. The RPCs keep
-- their current signatures here (they simply see more rows); the facet
-- parameters land in 0131 so this migration can go out on its own.

-- ---------------------------------------------------------------- registry --

create table dc_ads_campaigns (
  campaign_id text primary key,
  campaign_name text,
  source_kind text not null check (source_kind in ('instant_form', 'landing_page')),
  funnel_label text,
  destination_url text,
  typeform_id text,
  active boolean not null default true,

  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table dc_ads_campaigns is
  'THE scoping set for the DC ads funnel page — both acquisition paths. source_kind=instant_form rows are maintained from meta_leadgen_campaigns by the adset scan (optimization_goal=LEAD_GENERATION + destination_type=ON_AD); source_kind=landing_page rows are Meta campaigns whose ad creatives point at a Digital College landing page (host digitalcollege.ai). Membership for dc_ads_lead_facts and the ad-spend scope both read this table. Deliberately NOT "every OFFSITE_CONVERSIONS campaign": the account also runs the ANDROMEDA / Closer Funnel motion against theaipartner.io, which must stay off this page. See docs/schema/dc_ads_campaigns.md.';
comment on column dc_ads_campaigns.source_kind is
  'instant_form = Meta instant form (no landing page). landing_page = ad → landing page → Typeform → Close.';
comment on column dc_ads_campaigns.funnel_label is
  'Facet label for the page, matching close_leads.funnel_name for this campaign''s leads (e.g. Digital College, Aman Funnel, Luke Funnel).';
comment on column dc_ads_campaigns.typeform_id is
  'For landing_page campaigns: the Typeform the LP embeds (joins typeform_responses.form_id / typeform_forms.form_id). Null for instant_form.';
comment on column dc_ads_campaigns.active is
  'Set false to retire a campaign from the page WITHOUT deleting it (spend history must stay scoped). Paused-in-Meta campaigns stay active=true — history still counts.';

create trigger dc_ads_campaigns_set_updated_at
  before update on dc_ads_campaigns
  for each row execute function set_updated_at();

alter table dc_ads_campaigns enable row level security;

-- Seed 1: every instant-form campaign the adset scan has ever detected.
insert into dc_ads_campaigns (campaign_id, campaign_name, source_kind, funnel_label, last_seen_at)
select m.campaign_id, m.campaign_name, 'instant_form', 'Digital College', m.last_seen_at
from meta_leadgen_campaigns m
on conflict (campaign_id) do nothing;

-- Seed 2: the landing-page campaigns, verified live against the Meta API on
-- 2026-08-12 (creative destination URLs). The ingestion keeps this current from
-- here on; these rows bootstrap the history.
insert into dc_ads_campaigns
  (campaign_id, campaign_name, source_kind, funnel_label, destination_url, typeform_id, last_seen_at)
values
  ('120250217875250748', '07/25 | Aman TY Vsl | DC funnel',    'landing_page', 'Aman Funnel', 'https://join.digitalcollege.ai/training', 'fEQEMEyR', now()),
  ('120250195655690748', '07/24 | Aman TY Vsl | DC funnel',    'landing_page', 'Aman Funnel', 'https://join.digitalcollege.ai/training', 'fEQEMEyR', now()),
  ('120250444278470748', '08/03 | Luke Direct Form | DC funnel','landing_page', 'Luke Funnel', 'https://go.digitalcollege.ai/',           'mKtmTD1H', now())
on conflict (campaign_id) do nothing;

-- ------------------------------------------------------------ facts columns --

alter table dc_ads_lead_facts
  add column source_kind text,
  add column funnel_label text,
  add column typeform_id text;

comment on column dc_ads_lead_facts.source_kind is
  'instant_form | landing_page — which acquisition path this opt-in came through (from dc_ads_campaigns).';
comment on column dc_ads_lead_facts.funnel_label is
  'The lead''s close_leads.funnel_name, falling back to the campaign''s registry label. The page''s funnel facet.';
comment on column dc_ads_lead_facts.typeform_id is
  'For landing_page leads: the Typeform behind the opt-in, from the campaign registry. Null for instant_form leads (those carry form_id instead).';

create index dc_ads_lead_facts_source_kind_idx on dc_ads_lead_facts (source_kind);
create index dc_ads_lead_facts_funnel_label_idx on dc_ads_lead_facts (funnel_label);

-- ------------------------------------------------------------------ refresh --
-- Same body as 0128 except: membership joins dc_ads_campaigns instead of
-- meta_leadgen_campaigns, the funnel_name='Digital College' clause is gone, and
-- the three new columns are populated.

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
    source_kind, funnel_label, typeform_id, updated_at)
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
      dc.typeform_id
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
  form_match as (
    select distinct on (lp.close_id) lp.close_id, m.form_id
    from lead_phones lp
    join meta_form_leads m
      on right(regexp_replace(m.phone_number, '[^0-9]', '', 'g'), 10) = lp.p10
    order by lp.close_id, m.created_time desc
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
    l.source_kind, l.funnel_label, l.typeform_id,
    now()
  from leads l
  left join form_match fm on fm.close_id=l.close_id
  left join sms sm on sm.close_id=l.close_id
  left join calls ca on ca.close_id=l.close_id
  left join triage tr on tr.close_id=l.close_id
  left join closer cl on cl.close_id=l.close_id
  left join plan_per_lead pp on pp.close_id=l.close_id;

  get diagnostics v_count = row_count;
  return v_count;
end $function$;

comment on function refresh_dc_ads_facts() is
  'Rebuilds dc_ads_lead_facts (delete + insert, one transaction). Membership: close_leads on a campaign in dc_ads_campaigns (active), not excluded — BOTH acquisition paths. 0130 dropped the funnel_name=''Digital College'' clause because landing-page traffic is tagged Aman Funnel / Luke Funnel in Close.';
