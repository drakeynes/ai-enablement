# dc_ads_lead_facts

Per-lead funnel facts for the **DC ads funnel page**
(`/sales-dashboard/dc-ads`) — Digital College Meta-form opt-ins mirrored into
Close, with their downstream stage flags. Sibling of `outbound_lead_facts`
(same stage semantics, different membership + anchor). Migrations 0123–0129.

## Purpose

The page's funnel/speed/time-of-day/by-rep numbers must not aggregate
thousands of activity rows per page load. `refresh_dc_ads_facts()` rebuilds
this small table (delete + insert, one transaction) and the page reads it via
`dc_ads_funnel(p_start, p_end)` / `dc_ads_funnel_by_rep(p_start, p_end)` —
sub-second.

**Membership (changed in 0130):** `close_leads` whose `campaign_id` is in
`dc_ads_campaigns` (active), and not excluded — **both acquisition paths**
(instant form *and* landing page → Typeform). The old rule also required
`funnel_name='Digital College'` AND `campaign_id in meta_leadgen_campaigns`;
both clauses excluded the live landing-page motion, which Close tags
`Aman Funnel` / `Luke Funnel`. Campaign membership is now the sole signal — it
is what keeps the unrelated ANDROMEDA / Closer Funnel campaigns off this page
(see `docs/schema/dc_ads_campaigns.md` for why you must not widen it).
**Anchor:** `greatest(date_created, latest_opt_in_date)` — the
Meta→Close bridge matches returning phone numbers to their existing Close
lead and re-stamps `latest_opt_in_date`, so a re-opted April lead anchors at
its July form submit, not its original creation.

**Deliberate differences from outbound** (inbound ad opt-ins, not cold
outbound): `first_dial` = first outbound call after the opt-in (no
"replied first" precondition); speed-to-dial = opt-in → dial; no "responded"
funnel stage (`has_inbound` kept for reference); `optin_bucket` replaces
`reply_bucket`.

**Shows/closes come from TWO form sources** (0127): the Full Closer Report
AND the **DC sale form** (`airtable_digital_college_sales`) — where reps
actually file these dial-up pitches (the closer report went quiet with the
program suspension). DC sale form rules, mirroring `lib/db/leads.ts`: a filed
non-blank form = showed; `Closed?=Yes` with ≥1 plan = closed; `Closed?=Yes`
with no plan = show + `marked_no_plan`; form timestamp =
`coalesce(date_time_of_call, airtable_created_at)` and must be ≥ the anchor.

## Columns

Same stage set as `outbound_lead_facts` (see that machinery in migrations
0093–0119): `close_id` (PK), `anchor`, `first_reply`, `has_inbound`,
`any_call`, `call90`, `first_dial`, `booked`/`booked_dc`/`booked_ht` (setter
triage), `showed`/`closed` (closer report), `plan_units` +
`base44_monthly/yearly` + `wix_monthly/yearly` (cash = plan_units × $300),
`marked_no_plan`, `optin_bucket`/`dial_bucket`/`conn_bucket` (2-hour ET
buckets 0–11), `updated_at` — plus (0126) the lead's Meta attribution
`campaign_id`/`adset_id`/`ad_id` (from `close_leads`), which power the page's
ad-cascade filters on `dc_ads_funnel()` / `dc_ads_funnel_by_rep()` /
`dc_ads_daily()` / `dc_ads_speed_cohort()` (all take optional
`p_campaign_id`/`p_adset_id`/`p_ad_id`/`p_form_id`, plus `p_lp_slug` — the
page's landing-page dropdown, 0132 — and `p_funnel_label`, 0131's facet kept
as a deprecated rollout-compat alias;
`dc_ads_daily(p_end_et, p_days, …)` returns the last-N-days cohort strip;
`dc_ads_speed_cohort()` (0129) returns per-lead anchor/first-dial/dial-count
rows for the page's speed-to-lead boxes) — and (0128) `form_id`, the Meta
instant form behind the opt-in. The bridge doesn't stamp form ids on
`close_leads`, so the refresh derives it: match the lead's contact phone
(last 10 digits) to `meta_form_leads.phone_number` and take the NEWEST
submission's form (parity with the re-anchor-at-newest-opt-in rule).

**0130** adds `source_kind` (`instant_form` | `landing_page`), `funnel_label`
(the lead's `close_leads.funnel_name`, falling back to the campaign registry
label) and `typeform_id` (landing-page leads only, from
`dc_ads_campaigns.typeform_id`). `form_id` stays the **Meta instant form** and is
null for landing-page leads; `typeform_id` is its landing-page counterpart and is
null for instant-form leads.

**0132** adds `lp_slug` — the lead's landing page (`dc_landing_pages.slug`,
via the campaign registry's `lp_slug` at refresh; `'instant-form'` pseudo-slug
for instant-form leads). The landing-page dropdown's filter key (`p_lp_slug`);
`funnel_label` stays as display metadata for the Paths strip.

**0133** adds `tf_qualified` — the lead's own DC Typeform submission answered
the LP's qualification question with a qualifying label
(`dc_landing_pages.qualify_field_ref`/`qualify_answers`; the DC forms have no
$2k budget question — the shared discriminator is "Yes I can pay for the AI
tools"). Matched by phone (answers or hidden fields, last-10-digit rule) or
email, newest response wins; null = no matched response (always null for
instant-form leads). Powers the stage row's Qualified / SMS+MQL / HVC counts
in `dc_ads_funnel()` (`qualified`, `sms`, `smsMql`, `hvc`, `units` fields).

**0136** (no facts columns) reshapes `dc_ads_funnel_by_rep()` output: per-rep
`shows` (the refresh's is_showed semantics over window-filed forms), `units` +
plan splits, and `teamMemberId` (the DC Ads roster grid's identity join); adds
`dc_ads_unmapped_callers()` (DC Setup's radar for unlinked dialers).

**0137** (no facts columns) corrects HVC in `dc_ads_funnel()` /
`dc_ads_daily()` to `connected AND (tf_qualified OR has_inbound)` — a subset
of Connected by construction — and adds `dc_ads_lead_roster()`: per-lead rows
(display name + first contact phone/email, `lp_slug`, dials, disposition
flags) for the page's embedded, client-filtered lead list.

**0144** adds `tf_answered` — the lead's matched Typeform response answered
the qualify question AT ALL (any label); null = no matched completed response,
same convention as `tf_qualified`. Together they yield the roster's 3-state
`qualState` (boss vocabulary, 2026-08-15): **qualified** = `tf_qualified`;
**unqualified** = answered but not with a qualifying label; **partial** =
never answered it (no completed survey matched, or skipped the question —
instant-form leads always read partial). True Typeform partial responses are
NOT ingestible (they carry no answers/hidden fields — verified against the
live API 2026-08-15), so "partial" here means "no completed survey", which
covers both never-started and abandoned. `dc_ads_lead_roster()` also returns
`firstDial` since 0144 (the roster's Time-to-dial column, business-clock math
in `lib/db/dc-ads.ts`).

**0145** (no facts columns) extends `dc_ads_lead_roster()` with `smsOut` +
`units` — since then the roster is the ONE per-lead read behind the page's
speed boxes, lead list, and (0147) per-ad speed block; `dc_ads_speed_cohort()`
is no longer called by the page (retire someday with `p_funnel_label`).

**0147** adds the `(ad_id)` index, `adId` on the roster payload, and
`dc_ads_ad_table()` — the daily RPC's stage + D0/D3/D7 semantics grouped by
ad for the per-ad table (`docs/schema/dc_meta_ads.md` holds the ad identity
side).

**0148** REVERSES 0147's untagged exclusion as the **`non-attributed`
pseudo-campaign** (boss 2026-08-17: the DC Typeforms exist only on the ad
landing pages, so untagged arrivals are ad leads with LOST attribution —
privacy stripping / unfilled macros — not organic). Second membership branch
in the refresh: campaign-less, non-excluded leads created since 2026-07-01
with the bridge's `latest_opt_in_date` stamp AND a `funnel_name` matching a
registered ACTIVE DC campaign's `funnel_label` (the Zapier stamps
funnel_name from config, so it survives tag loss — no identity matching
needed, ~150 leads at ship time incl. 11 closes/$5.4k that were invisible).
They get `campaign_id='non-attributed'`, no adset/ad (ad facets + per-ad
rows exclude them naturally; the ad table shows them as one "Non-attributed"
row carrying the pseudo-campaign's identity), source_kind/lp/typeform inherited from the funnel's newest registered
campaign. The registry row `non-attributed` puts them in the campaign
dropdown; **deactivating it in DC Setup is the kill switch**. A retired
funnel's ghosts stay out (the map requires an ACTIVE campaign — the paused
instant-form-era ghosts don't resurface). Re-opt-in through a tagged ad
moves the lead to its real campaign at the next refresh — never
double-counted. Ship-day reconciliation: Aug-14 went from 52/31/25/13/11
(optIns/qual/sms/conn/hvc) to 58/34/28/18/14 vs the boss's 60/34/27/17/12.

**0149** (no facts columns) adds `dc_ads_breakdown(p_start, p_end)` — the
page header's "Data breakdown" popover. Reference = the **Close-style date
filter** (created OR `latest_opt_in_date` in window, across ALL of Close —
how ops validates by hand); counted = the facts cohort (anchor in window);
every gap lead is returned by name with a reason code derived **at read
time** from the same registry conditions the refresh's membership branches
use (no side table, nothing to go stale — but if membership rules change,
the RPC's CASE ladder must change with them): `manually_excluded` /
`inactive_campaign` / `stale_campaign` (tag not in the registry at all) /
`not_ad_lead` / `no_optin_stamp` / `pre_floor_reopt` (campaign-less re-opt
whose lead predates the 2026-07-01 floor) / `non_attributed_off` /
`pending_refresh` (meets membership, arrived after the last 15-min refresh).
`moved` = leads counted under an anchor OUTSIDE the window (a re-opt shifted
their cohort day — a Close date pull double-counts these on both days).
Names cap at 50 per reason; `excludedByReason` carries true group totals.
Ship-day check: Aug-17 reads reference 77 / counted 74 / MQ 46→44 with the
three gap leads reasoned (`not_ad_lead`, `stale_campaign`,
`pre_floor_reopt`) — the exact hand-reconciliation it replaces. Also adds
`close_leads_latest_opt_in_idx` so the OR-of-ranges reference scan can
BitmapOr with the 0043 `date_created` index.

## Populated by / read by

- **Writes:** `refresh_dc_ads_facts()` called by
  `api/outbound_facts_refresh_cron.py` (15-min tick, after Close/Airtable
  syncs) and by `ingestion/meta_ads/leads_pipeline.py` after each lead sync.
- **Reads:** `dc_ads_funnel()` / `dc_ads_funnel_by_rep()` / `dc_ads_daily()` /
  `dc_ads_speed_cohort()` / `dc_ads_breakdown()` RPCs behind `lib/db/dc-ads.ts`.

## Example queries

```sql
select dc_ads_funnel('2026-07-08T04:00:00Z', '2026-07-15T04:00:00Z');
select dc_ads_funnel_by_rep('2026-07-08T04:00:00Z', '2026-07-15T04:00:00Z');
```

Runbook: `docs/runbooks/meta_leads_ingestion.md`.
