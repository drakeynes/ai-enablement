# Sales — Surfaces (page map)

Every sales page, what it shows, and what was removed. All routes live under
`app/(authenticated)/sales-dashboard/` (server components, `force-dynamic`).

> **DC-era (2026-08-15): the dashboard is DC-only.** Every page except **DC Ads**
> and **DC Setup** is HIDDEN, not deleted (boss directive): nav entries carry
> `hidden: true` (`components/top-nav.tsx`, `sales-dashboard/sidebar.tsx`) and a
> root `middleware.ts` redirects every other path to `/sales-dashboard/dc-ads`
> (authenticated users without the sales area land on the terminal `/no-access`
> page). All root/login/home redirects point at DC Ads. To restore a page: unhide
> its nav entry + allow its path in `middleware.ts` (or delete that file to
> restore everything). The sections below describe every page as built — hidden
> pages' code and loaders are untouched.

Pre-DC nav was **flat: Advertising Hub · Outbound · DC Ads · Leads · Talent**, with
Roster nested under Talent. Outbound is its own top-level page (no longer nested
under the Advertising Hub).

---

## Advertising Hub — `/funnel` (was "Marketing" / "Funnel" / "Pulse")

> Renamed to **Advertising Hub** 2026-06-24 (sidebar label + page header `SALES · ADVERTISING HUB` /
> "Advertising Hub."). The route stays `/sales-dashboard/funnel`. (Was "Marketing" 2026-06-18.)

The stacked cohort funnel: **Total / Direct / Setter / Reactivation** boxes (opt-ins →
connected → booked → confirmed → showed → closed; `confirmed` only on Direct/Total;
the **Total box hides the Books node** — Confirms is the meaningful one there;
`closed` split HT/DC). Stage nodes are `<Link>`s into the filtered **Leads** roster
(type + stage), so a box's number equals the roster it opens. The page also hosts:

- the **Digital College funnel** block — modeled **Connects → Closed** (connects =
  `lead_cycles.digital_college_at`; closed = `dc_closed_at`, downsells merged; see `data-model.md`),
- the **Cash Collected / ROAS** block,
- the **integrity-guard banner** (flags `books ≥ connected ≥ confirms ≥ shows ≥ closes`
  violations),
- the **Campaign → Ad Set → Ad cascade filter** (three dependent dropdowns; the deepest
  selection scopes the whole funnel — see `data-model.md` § cascade. All three
  levels are named with spend/ROAS, including Ad Set since migration 0089),
- the **last-5-days daily table** at the bottom — a cohort-by-opt-in-day strip
  (`Day · Spend · Leads · Connects · Booked · Showed · Closed · Cash · Sp2L · Dials`),
  a rolling 5 ET calendar days **independent of the date picker** but **scoped to the ad
  cascade**. Each day reuses the funnel's own `getLeadsFunnel` / `getFunnelCash` over a
  single-day window, so the rows can't drift from the boxes above
  (`lib/db/funnel-daily.ts`, `components/sales/daily-funnel-table.tsx`),
- the **inline Ads + Landing-Page summary** under that table — the numbers that used to
  live on the click-through Ads and Landing-Pages pages, now plain labelled lists (no
  sparklines): Meta ad delivery (spend / impressions / unique clicks / CTR / CPM /
  cost-per-click / frequency), LP visits + conversion, Typeform starts / completions /
  qualified, and the VSL + confirmation-video metrics (each divider labelled with the video's
  Wistia name beside it). LP visits + the Typeform counts
  (starts / completions / qualified / non-qualified) each carry a **cost-per bracket**
  (adspend ÷ count). The **ads block scopes to the ad cascade**; the **landing-page block
  scopes to the LP selector + window** (separate
  dimensions) — `lib/db/funnel-summary.ts`, `components/sales/ads-lp-summary.tsx`.
- the **inline leads roster** at the very bottom — the same list + columns (Prospect /
  Opted in / Disposition / Time to call / Connected / Intensity) you'd reach by clicking
  the Total funnel's opt-ins stage, surfaced in-page so there's no click-through. Reuses
  the Leads page's `LeadRoster` over the page's already-loaded cohort `rows`, so it
  **re-scopes with the ad cascade for free** (no extra query — the roster fetch is already
  paid). Rows still link to the per-lead page.

**Landing-page scoping (live 2026-06-27).** The LP dropdown re-scopes the **whole page** —
funnel boxes, daily table, roster, Ads/LP summary, AND the Digital College funnel — via
`lead_cycles.source_form_id` (the form each opt-in came through; migration 0106). "All
landing pages" (no `?lp=`) shows the combined cohort; Main/Training scope to that form. Boxes
go through `sales_funnel_counts(… p_source_form_id)` (0107); roster/daily/DC pass a `formId`;
the Ads/LP Typeform aggregates the matching form(s). See `docs/sales/landing-pages.md`.

The old in-page **navigation links were removed** (2026-06-18): the adspend node no longer
links to the Ads page and the "Landing pages →" header link is gone, now that the data is
inline. The `/funnel/ads` and `/funnel/landing-pages` routes still exist (reachable by URL).

### `/funnel/ads`
Meta / Cortana ad metrics. **No longer linked** from the funnel (the adspend node's link
was removed); the same window-scoped numbers now render inline on the Advertising Hub page.
Still reachable by URL.

### `/funnel/landing-pages`
Landing-page + Wistia video + Typeform metrics. **No longer linked** (the "Landing pages →"
header link was removed); those numbers now render inline on the Advertising Hub page. Still
reachable by URL.

---

## Outbound — `/outbound` (was `/funnel/revival`, "Revival")

The outbound-SMS funnels — one per campaign pool (**Revival**, **Jacob**, …), the only surfaces that count
those leads. Membership is a Close custom field per campaign: the **Revival** CF (`DC Revival Lead`) is set
by the external Close SMS re-engagement workflow (no tagger of ours); the **Jacob** CF is set by our
roster tagger (`shared/outbound_campaign_tag.py`). Moved out from under the Advertising Hub to its own
top-level page + renamed **Outbound** 2026-06-24 (route `/sales-dashboard/outbound`; internally still
"revival" — the shared components/data keep the `revival` name). See `data-model.md` § Revival.

**Materialized** (2026-06-24, migrations 0093/0094/0095). The page reads one `outbound_funnel(p_campaign_key)`
RPC (funnel + called + timeOfDay) **over the precomputed `outbound_lead_facts` table** — sub-second, no
matter how big the campaign gets. The heavy per-lead aggregation runs OFF the page load:
`refresh_outbound_facts()` (≈15s) is called by the **`outbound_facts_refresh_cron`** every 15 min, and
`outbound_funnel()` just reads the facts. (The original live-aggregation function scanned 66k SMS + 20k
calls every load → 23s → past the 8s API timeout → the page crashed; this is the fix, mirroring
`lead_cycles`.) **Connected = a ≥90s call only.** Parameterized by the **`outbound_campaigns`** registry,
now surfaced as a **campaign dropdown** (`?campaign=`) with an **"All" default** + one option per registry
row (Revival, Jacob, …). "All" passes `p_campaign_key = NULL`, so both funnel RPCs aggregate across every
campaign's leads (a clean union — the pools are mutually exclusive, so no double-counting; migration 0108).
Each pool is a registry row, so adding a campaign is a row + tagging its leads. `refresh_outbound_facts`
runs for **every active campaign**.

**Two campaign models (migration 0115).** The legacy pools (Revival, Jacob) match a Close
`close_cf_id` with 0103 exclusivity. **New-model** campaigns — added via the adder below — match
a custom-field **name + exact value** across **both Close AND GHL** (the name resolves to a Close
cf id and/or a GHL field id; the GHL arm sources responded/called/connected from `ghl_messages`,
closes from Airtable joined on `lead_id = ghl_contacts.id`). New-model campaigns are **independent —
no exclusivity**, so a lead in two campaigns counts in both (deliberate). So "All" no longer assumes
non-overlap; it's the union of every campaign's facts. The per-campaign start date now comes from the
registry (`floor_at`), not hard-coded page constants.
A **date range** (calendar, `?start=&end=`, migration 0102) scopes the funnel by each lead's
**anchor** (campaign entry = `greatest(date_created, floor)`) — a fast filter over the materialized facts,
no re-aggregation. There is **no all-time mode**: when the calendar is untouched the page defaults the
range to **[campaign start → today]** (start dates are hard-quoted per campaign in the page — Revival
Jun 3, Jacob Jun 20), so the funnel and the calendar always agree. A **"Started …"** label shows the
campaign's launch date.

**Pools are mutually exclusive** (migration 0103). The ECJ "Jacob" batch runs through the same Close SMS
reactivation workflow that stamps every lead with the **"DC Revival Lead"** CF, so all Jacob leads also
carry the Revival tag. To honor "counted in exactly one place," `refresh_outbound_facts` assigns each lead
to the **most specific** campaign it carries (highest `outbound_campaigns.sort_order`) and excludes it from
the rest — so Jacob leads/closes are dropped from Revival, never double-counted.

> **2026-06-26 incident:** `refresh_outbound_facts` ran ~3s/campaign on micro but minutes on nano under
> load, and the `*/15` cron **stacked** overlapping runs → DB saturation. Fixed: nano→micro **and** the
> cron is guarded — per-refresh `statement_timeout` (kills runaways) + `pg_try_advisory_lock` (a tick
> skips if one's still running, never stacks) + per-campaign isolation.

**Jacob (ECJ Reactivation)** — the 2nd pool (migration 0099). Membership = the **"Jacob Lead"** Close
custom field (`cf_m0ooi…`), set on `close_leads` matching the ECJ CSV roster (`outbound_campaign_roster`,
by email **or** phone). Future leads auto-tag via the close webhook (`shared/outbound_campaign_tag.py`,
hooked in `api/close_events.py`): any new lead matching the roster gets the field set in Close. Floor =
2026-06-20 (the batch load start).

The funnel displays **leads → responded → called → connected → closed** — the **Booked and Showed
stages are hidden** (the SQL still computes them, so un-hiding is a display-only change).
The Called (speed-to-dial) + time-of-day sections are unchanged.

**By-rep block** (migrations 0104 + 0105, `outbound_funnel_by_rep` RPC → `OutboundByRepSection`). Under the
funnel, a per-rep table: **Dials · Connections · Closes · Cash**. Its header summarizes the window's
**total closes + unit mix sold** (Base/Wix × Monthly/Yearly chips, same classification as the funnel's
`closedPlans`) — the daily-activity counterpart to the cohort funnel's plan chips. The RPC returns
`{ reps, totals }`. Unlike the funnel it is **activity-scoped** — it
counts what each rep *did* in the calendar window (calls by `activity_at`, closes by form date), not the
entry cohort. One combined row per rep bridges Close calls (`close_calls.user_id` → `team_members.close_user_id`)
and Airtable closer reports (`closer_record_ids` → `team_members.airtable_user_id`); reps absent from
`team_members` fall back to their raw name. **Only reps who actually closed are shown.** Dials = outbound
calls; Connections = ≥90s calls; Closes = DC-closed-with-plan distinct deals; Cash = $300/plan unit.
Caveat: `airtable_user_id` has no auto-sync yet (Sierra Anderson's was backfilled in 0104) — new closers
need their `airtable_user_id` set to merge their closes with their dials.

---

## DC Ads — `/dc-ads` (added 2026-07-10)

The **Digital College paid-ads funnel** — since the full-program suspension (July 2026) the only
acquisition motion, across **two paths** (0130):

- `instant_form` — Meta ad → **instant lead form** (name + phone, no landing page) → the Meta→Close
  bridge creates the Close lead in seconds (`funnel_name='Digital College'`). The original motion;
  its campaign has been paused since the landing-page path went live 2026-07-22.
- `landing_page` — Meta ad → **landing page** on `digitalcollege.ai` → its **Typeform** → Close
  (`funnel_name='Aman Funnel'` / `'Luke Funnel'`). The live motion.

Both are scoped by the `dc_ads_campaigns` registry (never "all `OFFSITE_CONVERSIONS` campaigns" —
the same ad account runs the unrelated Closer Funnel motion against `theaipartner.io`; see
`docs/schema/dc_ads_campaigns.md`). The Outbound page's shape with **ad spend leading the funnel**:

- **Stage row** (reshaped 2026-08-13, migration 0133 — was the Adspend→Called→Connected→Closed
  funnel) — the boss's nine numbers:
  `Adspend > Opt-ins > Qualified > SMS > SMS+MQL > Connects > HVC > Units > Closed`, plus the
  cash & **ROAS** row. Deliberately **not a strict funnel** — stages overlap rather than nest; the arrows carry
  STEP RATIOS (next ÷ prev, $/opt-in on the adspend junction — boss 2026-08-14), to be read as
  ratios between adjacent stages, not drop-off. Definitions: Qualified = the lead's own Typeform hit
  the LP's qualify answer (`dc_landing_pages.qualify_field_ref`/`qualify_answers` — ⚠ the DC
  forms have NO "$2,000+" budget question; the shared discriminator is the affordability
  question "Yes I can pay for the AI tools"; matched to the lead by phone/email, newest response
  wins → `dc_ads_lead_facts.tf_qualified`); SMS = inbound SMS after the opt-in (`has_inbound`);
  SMS+MQL = qualified AND texted back; Connects = **a call ≥90s ONLY** (0140, Nabeel — the
  filed-form fallback was removed to cut human error; Shows can therefore exceed Connects when a
  pitch happened without a 90s call landing in Close; SMS never connects a lead); HVC =
  **connected AND (qualified OR texted-us)** (0137 shape, 0140 call-only base) — guaranteed ⊆
  Connects; Units = `plan_units` sum (cash = units × $300). The lead-roster toggles and the
  speed-box connected rate use the same call-only Connected; Called/Booked/Showed/Closed keep
  their form evidence.
  Called/Booked/Showed are still computed for the page's other sections.
  Adspend = `cortana_campaign_daily` summed over ONLY
  the registered DC campaigns (`dc_ads_campaigns` — instant-form campaigns detected by the adset
  discriminator `optimization_goal=LEAD_GENERATION` + `destination_type=ON_AD`, landing-page
  campaigns by creative destination host `digitalcollege.ai`; both re-scanned every 15 min).
  **Shows/closes come from the DC SALE FORM** (`airtable_digital_college_sales` — where reps
  actually file these dial-up pitches; the Full Closer Report went quiet with the program
  suspension) unioned with the closer report (0127): a filed form = showed, `Closed?=Yes` with ≥1
  plan = a close, `Closed?=Yes` with no plan = show + the marked-no-plan counter.
- **By rep** (talent detail 2026-08-13, migration 0136) — Dials / Connections / **Shows / Closes /
  Units / B44·Mo / B44·Yr / Wix·Mo / Wix·Yr** / Cash, same Close-calls + Airtable-forms bridge as
  Outbound's table (closes also from the DC sale form since 0127), but **every rep with activity is
  listed** (not closers-only — this pool is dial-heavy). Shows = filed pitches (the facts refresh's
  is_showed semantics); a two-closer deal credits both while the header totals count deals once.
  Connections are counted **per call** (a lead reached twice counts twice; inbound ≥90s pickups
  count), so the column sum runs higher than the funnel's lead-level Connected — footnoted on the
  page. Only CONFIRMED team members render (Drake 2026-08-14): active members are the main rows,
  deactivated members collapse into the "Former reps" group, and activity from identities with no
  `team_members` row is not shown at all — adding someone to the Airtable roster + verifying in DC
  Setup makes their history appear retroactively.
- **Roster** (added 2026-08-13) — the Talent Roster's card grid **scoped to the DC ad cohort**: one
  card per team member (managed in DC Setup; active-first, "Show inactive" toggle, zero-activity
  actives included so a new hire is visible before their first dial) with Dials / Connects / Shows /
  Closes / Units / Cash from the by-rep RPC; confirmed members only — unlinked activity is not
  rendered.
- **Leads roster** (added 2026-08-14, migration 0137) — the Leads page's list scoped to DC ad
  leads, embedded right under the speed-to-lead boxes: one row per cohort lead (name / phone /
  email / opt-in day / landing page / dials / qualified / disposition), all inside a fixed-height
  scrollable box. **Search + stage toggles (SMS · Connected · HVC · Closed) filter fully
  client-side — they never navigate.** Toggles are CUMULATIVE (Nabeel 2026-08-14): each shows
  every lead that reached that stage, so toggle counts equal the stage row's numbers; the badge
  on each row is still the lead's furthest stage (Closed > HVC > Connected > SMS > Opt-in). Backed by `dc_ads_lead_roster()` (identity from
  `close_leads.display_name` + first contact phone/email — the search keys); follows the cascade +
  LP dropdown + window like every other section.
- **Speed to lead boxes** (added 2026-07-15; reclocked + SMS box 2026-08-13, migration 0135) —
  the Leads page's top-line stats computed over the DC-ads cohort, **on the DC dial team's own
  12p–12a ET clock** (boss 2026-08-13 — deliberately NOT comparable with the Leads page's
  10a–10p numbers; the clock is labeled on the box; verified against an independent
  implementation to the second across the full cohort incl. DST days), plus an **SMS engagement
  rate** and (boss item #20, 2026-08-14) a second stat strip — dial-speed spread (% dialed
  <5m/<10m/<30m cumulative · >30m · never dialed — <30m + >30m + never = 100% — and the median
  time to dial, all on the DC clock) plus MQL→Close / HVC→Close / Connect→Close rates and CPU
  (adspend ÷ Valid-adjusted units). The SMS engagement rate: of the leads we texted (any outbound SMS after the opt-in), how many texted back —
  texted, not cohort, as the denominator (never-touched-leads-don't-dilute, Drake 2026-06-18;
  a text-first lead sits in both sides so the rate caps at 100%). Backed by the
  `dc_ads_speed_cohort()` RPC (0129→0135: + `smsIn`/`smsOut`) + the SAME
  `businessHoursElapsedSec` (with DC's open/close hours) + `summarizeCohortRows` math the Leads
  page uses. Same 24h outlier cap.
- **Speed to dial** — form submit → first outbound dial (the opt-in is the hand-raise; no
  reply-first precondition like Outbound's).
- **Time of day** — opt-ins vs dials vs connects, 2-hour ET buckets.
- **Ad cascade chooser** (added 2026-07-10) — the hub's `AdCascadeFilter` component reused as-is
  (`?campaign / ?adset / ?ad`, deepest wins). Scopes EVERYTHING: spend (entity's own `cortana_*`
  table, like the hub's cascade), funnel, by-rep, speed-to-lead, speed-to-dial, time-of-day, and
  the daily strip. Hierarchy comes from `dc_ads_lead_facts` in the window (0130 — building it from
  `meta_form_leads` hid every landing-page campaign, which never submits a Meta form); entity
  names come from the `cortana_*` spend mirrors.
- **Landing-page dropdown** (2026-08-13; replaced the Forms dropdown) — a fourth select beside
  the cascade (`?lp`), the DC counterpart of the hub's landing-page filter. Options come from the
  **`dc_landing_pages` registry** (0132) with URL-derived names ("join/training", "go") plus an
  "Instant form (no LP)" pseudo-entry for the legacy path; counts are window opt-ins. An
  independent AND facet — a page spans many ads — backed by `dc_ads_lead_facts.lp_slug` via the
  RPCs' `p_lp_slug` param (0132; `p_funnel_label` from 0131 remains as a deprecated compat
  alias). Spend under an LP-only selection = the campaigns driving to that page
  (`dc_ads_campaigns.lp_slugs`) summed from `cortana_campaign_daily`; with a cascade entity
  selected too, the entity wins the spend read while the funnel ANDs both. **Corroborated with
  the campaign registry (2026-08-14, 0138):** the options are exactly the pages ACTIVE
  campaigns drive to (+ any page with window opt-ins so data never hides); with a campaign
  selected the dropdown narrows to THAT campaign's page(s); the Ads & LP summary's "All landing
  pages" block aggregates the same linked set. **A new funnel
  self-registers**: creative scan → registry row (URL-named) → dropdown + spend + facts, no
  manual steps (`resolve_dc_landing_pages()`, see `docs/schema/dc_landing_pages.md`). The
  retired Forms facet's plumbing (`form_id` column, `p_form_id` RPC param, form→ads spend
  mapping) is all retained — the forms breakdown is planned to resurface in its own section.
- **Campaign dropdown lists the FULL registry** (2026-08-13) — every active `dc_ads_campaigns`
  row appears, newest launch first (leading M/D in the name), with 0-counts for campaigns that
  have no window opt-ins — so the list matches the boss's Meta-manager view (a just-created or
  never-run campaign is visible immediately).
- **Ads & landing page section** (2026-08-13) — the hub's inline summary shaped to DC, under the
  daily strip (`components/sales/dc-ads-lp-summary.tsx` + `lib/db/dc-ads-summary.ts`). Three
  blocks: **Meta ads** (adspend/impressions/unique clicks/CTR/CPM/$-per-click/frequency from the
  `cortana_*` mirrors over the active selection), **Landing page** (LP visits = Meta unique link
  clicks of the LP scope — follows the LP dropdown, never the cascade, hub semantics — + Typeform
  submissions from `typeform_responses`; starts/completion need Typeform's Insights API, not
  mirrored), **Videos** (the LP's registered videos via the hub's `getVslMetrics` math over
  `wistia_media_daily`; videos auto-attach to LPs by Wistia embed location —
  `attach_dc_lp_videos()`). ⚠ Wistia stats are per-video across all its embeds: the same VSL runs
  on both DC funnels today, so an LP selection scopes which videos show, not where they were
  watched (footnoted on the page).
- **Last 30 days table** (added 2026-07-10 as a 5-day strip; 30 days + stage metrics 2026-08-13,
  migration 0134) — the hub's daily cohort table carrying the stage-row metrics: Day · Spend ·
  Opt-ins · Qualified · SMS · SMS+MQL · Connects · HVC · Units · Closed, rows scrolling inside a
  fixed-height box (header pinned). Each row = that ET day's opt-in cohort: spend + opt-ins
  freeze when the day ends, every downstream column is LIFETIME progression and keeps climbing as
  that cohort texts back / connects / closes — recent days always read lighter. Pinned to the
  rolling window regardless of the date picker; follows the ad chooser + landing-page dropdown.
  **D0/D3/D7 Units + ROAS** (boss item #19, migration 0142): valid-adjusted units closed within
  0/<3/<7 ET calendar days of the opt-in (cumulative) and each × $300 ÷ the day's spend, beside
  overall ROAS — the speed-to-payback read; the 17 columns scroll horizontally inside the box.
  Backed by the `dc_ads_daily()` RPC (0126→0142; still returns called/cash/dials for other
  consumers) + a per-day spend merge in `lib/db/dc-ads.ts`.
- **Bridge-drift warning** — the page compares Meta-side form submissions (`meta_form_leads`)
  against Close-side opt-ins and prints a ⚠ line when they diverge (a growing gap = the Meta→Close
  bridge is dropping leads). Unfiltered view only (the Meta count isn't cascade-scoped).

Scoping is mutually exclusive with Outbound: only registered-DC-campaign leads here (never
outbound pools), and DC ads leads never appear on the Outbound page (separate facts table —
`dc_ads_lead_facts`, migrations 0122–0131 — precisely so Outbound's "All" view stays clean).
Date range: URL `?start/?end`, default **[2026-07-08 (first lead-form campaign) → today]**.
Data layer `lib/db/dc-ads.ts`; ingestion `docs/runbooks/meta_leads_ingestion.md`.

---

## Leads — `/leads`

The lead **roster** + filter bar (type/stage) + speed-to-lead boxes + the
first-meaningful-response (FMR) chart — all window- and filter-scoped to the same cohort.
The roster shows a per-lead booking tag. (The stacked funnel **no longer lives here** — it
moved to `/funnel`.)

The **Connected rate** box is `connected ÷ leads worked`, where *worked* = leads
**dialed OR connected** (not the whole cohort) — a true connection rate that
never-touched leads don't dilute. "Connected" is a **≥90s call
only** (`reachedStage`, back-filled from confirmed/showed/closed) — a triage/confirmation
form no longer counts. A form/text reach with no qualifying call is
**not** connected.

### `/leads/[close_id]` — per-lead page
A facts strip (qualified, opt-in dates, **Stage** chip-funnel, dials, connected
count+duration, reschedules, follow-ups) + a **Notes** section (one free-text
scratchpad per lead — type + save, overwrites; `lead_notes`, migration 0090;
any team member can edit) + a **two-phase Journey** (Direct → Reactivation)
+ a **day-grouped Lifecycle** (full history, newest-first, opt-in dividers) + a Close-
details section. Each Lifecycle **form row carries the rep's free-text notes off that
form** (triage `notes`, closer `call_notes` + `call_notes_lost` merged, DC `call_notes`),
rendered under the disposition — distinct from the per-lead `lead_notes` scratchpad above. Bookings are matched to the lead by email + name + unique utm_term token.
The journey **resets on re-opt-in**. There is a lead search bar (`?q=`) that resolves a
name → this page.

---

## Talent — `/people` (display name "Talent")

Per-rep **Call Activity** (setters and closers), per-closer scheduled tables, the
**BOOKINGS** boxes (Calendly),
**Cash**, and the **Digital College** drilldown (Robby). This is the
rep-performance surface, organized **by call type** (a Triage table + a Confirmation
table, etc.). Being superseded by Roster (below) — kept as the comparison baseline until
Roster is trusted.

### Talent · Roster — `/people/by-rep` (sidebar label "Roster")

The **by-person** re-presentation of Talent — one block per rep instead of stacked
by-call-type tables. A candidate replacement for `/people`. The **click-through detail**
reuses the existing loaders (`getCallActivityMetrics`, `getClosingScheduledList`,
`getDigitalCollegeActivity`) unchanged; the **card's crucial metrics** are computed
**forms-only** (below) via `getCloserFormMetricsByRep` — the one piece of Roster-specific
logic.

- **One card per rep**, keyed by Close `user_id`, merging that person's setter + closer
  rows from Call Activity (dials / connections / bookings) with their **forms-only closer
  metrics** (meetings / closes / cash). A rep who both sets and closes (e.g. Aman)
  collapses into a single block instead of two scattered rows.
- **One canonical role chip** from `team_members.sales_role` (Setter / Closer / DC
  Closer) — the role the rep *is*, not a chip per call-family they happen to have
  activity in. Cross-family activity (a closer's stray triage calls) still surfaces on
  the detail view.
- **Crucial metrics — the SAME eight on every card** (every rep both sets
  and closes a little, so the old role-keyed sets were merged — the role chip still shows the
  dedicated role, only the metric set is unified). Setter-side → closer-side, **strictly from
  the forms** (no booking-platform data), in a 4×2 grid:
  - **Dials · Connections** — the rep's calls (`close_calls`; ≥90s = connected).
  - **Bookings** — the rep's setter "Booked" (HT + DC from the triage table). **Book rate**
    = Bookings ÷ Connections.
  - **Meetings · Closes · Cash · Cash/mtg** — from the rep's closer EOC forms
    (`airtable_full_closer_report`), attributed by `closer_record_ids` → `user_id` across
    **ALL** reps, not just `sales_role='closer'` (`getCloserFormMetricsByRep`; a closer-only
    resolver previously zeroed DC closers + setters who file EOC forms).
    - **Meetings** = forms with a *showed* outcome, **incl. any Digital College disposition**
      (a DC form means a DC meeting was held).
    - **Closes** = a High-Ticket close (`call_outcome = 'High Ticket Closed'`) **OR** a DC
      close = **`dc_plans` filled** (the canonical signal — *not* the `'Digital College
      Closed'` text, which appears with no plan = a fake close, and misses bare `'Digital
      College'` + plan = a real one).
    - **Cash** = `amount_paid` (HT + deposits) **+ $300 per DC plan unit** (`DC_PLAN_PRICE_USD`,
      the same flat-rate logic as `funnel-cash`/`funnel-dc`). **Cash/mtg** = Cash ÷ Meetings.

  Everything else lives on the click-through. (The per-closer scheduled tables on the
  detail also fold DC `$300`/plan into their **Cash** column — though
  their `closedDc` *count* still keys on the outcome text; only the card is fully
  `dc_plans`-consistent on both closes and cash.)
- **Click a card → per-person detail** (`?rep=`): the full existing drilldown tables
  (call activity + per-call drill, scheduled calls, DC) scoped to that one rep, with a
  "← All reps" back link. Collapsing the drill returns to the grid (`?rep` is the page's
  single person selector). Plus a **"Closer forms" table** (`getCloserFormsForRep`) listing
  **every** closer EOC form the rep filed in range — date / prospect / outcome / plan /
  cash / close-badge — attributed across **all** roles, so DC closers + setters who file
  forms (Connor, Bradley, Joshua) finally see their forms here (the scheduled tables only
  show `sales_role='closer'`, so they were invisible before).
- **EODs** — a section at the **very bottom** of the per-person detail, **collapsed by
  default**: that rep's EOD reports (Setter/Closer EOD's from Airtable, mirrored into
  `airtable_rep_eods`) whose date falls in the selected window, newest first. Sparse today
  (only a few reps fill them) — most reps show "No EOD reports filed in this window." Each
  EOD renders its labeled fields straight from the Airtable record (`fields_raw`), so new
  form fields appear with no code change. Read by `lib/db/funnel-eods.ts` `getRepEods`
  (resolves `close_user_id → airtable_user_id`).
- **Active/inactive.** Inactive reps are **hidden by default**; a "Show inactive" toggle
  reveals them (dimmed, with an "Inactive" chip). Active = `team_members.is_active` among
  non-archived sales rows (`is_csm=false`, so it's independent of the CSM surfaces;
  flip one boolean to change the roster — no deploy). The active set is driven by the
  `is_active` toggle (no deploy needed).
- **Cards are equal-height** (grid-auto-rows), active reps sorted first.
- **Click feedback.** Opening a rep is a `?rep=` searchParam nav (same route → no
  `loading.tsx`), so the card navigates through a `useTransition` and the grid swaps for a
  shimmer skeleton ("Loading <name>…") until the detail renders (`roster-grid.tsx`).

The closer card's funnel reads the read-time loaders (`getClosingScheduledList` etc.),
which reconstruct booking→closer-form from **Calendly** at read time (the per-closer
attribution that once motivated the `booking_cycles` spine, now **shelved** — see
[`logic.md`](./logic.md) / this file). Books/Shows/Closes stay
read-time-reconstructed (no persisted spine); Roster can replace `/people` once it's
trusted on the real numbers.

---

## Per-call review — `/calls/[close_id]`

The per-call transcript / review page. Reached **only** from a per-lead Lifecycle row
(back link carries `?lead=`). There is **no Calls list page** — it was removed.

---

## Verify Reps — `/sales-dashboard/reps` (admin)

The admin surface for **onboarding a new sales rep**. When a rep is added to the
Airtable "Sales Team Member" table, they appear here (forward-only: created on/after
`2026-06-27`) as a card to verify. The admin sets the rep's **sales role** (Setter /
Closer / DC Closer), resolves their **Close ID + email** (a Close-user picker that fills
both, or manual entry), and optionally a **Calendly event-type URI** (fully optional — DC
closers can close by phone). Three buttons:

- **Save** — persist a draft, leave the card open (rep not in Close/Calendly yet).
- **Complete** — write the `team_members` row (`role='sales'`, `access_tier='csm'`). The
  rep then **auto-appears on every per-rep surface** (Outbound by-rep, Talent, People,
  Roster) via the existing `team_members` joins on `close_user_id` / `airtable_user_id` —
  no per-page wiring.
- **Delete** — dismiss a test/junk candidate.

Data: Airtable → `sales_rep_candidates` (mirror cron `sales_rep_candidates_sync_cron`,
every 30 min) and Close → `close_users` (the daily close-users cron); draft/final state in
`sales_rep_verifications`. The `/sales-dashboard` segment is **sales-area**-gated (migration
0112); this admin tool additionally re-checks **admin tier** and is hidden from the sidebar
for sales reps (csm). See `docs/schema/sales_rep_candidates.md`, `sales_rep_verifications.md`,
`close_users.md`, and `team_members.md` § Sales identity + § Department areas.

---

## DC Setup (admin) — `/sales-dashboard/dc-setup` (admin, added 2026-08-13)

The ONE page where Zain/Aman run the whole DC Ads operation with no engineer
(Drake 2026-08-13). Operator guide + Loom script:
`docs/runbooks/dc_setup_admin.md`. Three sections:

- **Team** — who appears on the DC Ads by-rep table + roster. (a) The
  **verify queue**: `sales_rep_candidates` (Airtable "Sales Team Member" →
  cron, migration 0109) with a **suggested Close match** pre-selected
  (unambiguous first-name match against `close_users`; the human confirms).
  Verifying delegates to the /sales-dashboard/reps `completeRep` action —
  one write path for `team_members` — linking the Airtable form identity +
  Close identity into one row. (b) **Current team**: edit (name / role /
  email / Close link) + **deactivate / reactivate** (`is_active` — the
  offboarding path; history stays). The DC Ads page renders CONFIRMED
  team members only (Drake 2026-08-14) — membership is controlled here, so the
  Airtable roster table is the single front door for new people.
  (`dc_ads_unmapped_callers()` from 0136 is currently unused.)
- **Landing pages** — the `dc_landing_pages` registry (0132): rename, URL
  (normalized in lockstep with `shared/lp_urls.py` via `lib/lp-urls.ts`),
  extra funnel pages, Typeform (dropdown), **qualification question +
  qualifying answers** (picker over the form's mirrored choice fields —
  drives the page's Qualified stage), videos (Wistia-inventory dropdown),
  retire/restore. No hard delete (facts + campaigns reference the slug).
  Saving marks the row curated (`auto_created=false`); the ingestion resolver
  never overwrites curated fields.
- **Campaigns** — `dc_ads_campaigns` (0130): per-campaign landing-page
  **checkboxes** (`lp_slugs`, 0138 — tick several when split-testing; first
  ticked = primary; facts re-stamp ≤15 min, per-lead attribution via the
  matched Typeform when >1) and **retire/restore** (`active` — retiring
  removes the campaign's spend AND leads from the page; paused-in-Meta
  campaigns stay active so history counts). Whatever is ticked here is
  exactly what the DC Ads page's LP dropdown and Ads & LP summary cover.

- **System health** (2026-08-14, migration 0139) — bottom of the page: one card per data feed
  (Meta leads/spend, Close, Typeform, Airtable, Wistia, the facts refresh) with ✅/⚠/❌ + "last
  sync Xm ago", read from `dc_setup_system_health()` (per-source last PROCESSED
  `webhook_deliveries` tick; the new `(source, received_at)` index makes it ~50ms). Staleness
  thresholds ≈4× each source's cadence.

All actions are admin-gated server-side and `revalidatePath` the DC Ads +
Talent pages. Aman was bumped to `access_tier='admin'` (2026-08-13) so both
he and Zain can operate it.

---

## Landing Pages (admin) — `/sales-dashboard/landing-pages` (admin)

The admin **registry manager** for landing pages (distinct from `/funnel/landing-pages`,
which is the per-LP **stats** page). Add an LP by pasting its link → **Discover** auto-fills
the embedded Wistia VSL(s) + Typeform (best-effort; confirm/pick from dropdowns) → set the
**qualification question + which answers qualify** → **Save**. The LP then appears in the
funnel's landing-page dropdown and new opt-ins through its Typeform attribute to it
automatically (the tagger reads the form set from the DB). **Edit** adds a form (old form's
leads stay counted); **Deactivate** hides it but keeps its cycles; **Delete** is refused if
the LP has leads; **Retag now** backfills pre-registration opt-ins (`api/landing_page_retag.py`).

DB-backed registry: `landing_pages` + `landing_page_forms` (migration 0110). Admin-tier
within the sales area (hidden from reps' sidebar). See `docs/sales/landing-pages.md` and
`docs/schema/landing_pages.md` / `landing_page_forms.md`.

---

## Outbound Campaigns (admin) — `/sales-dashboard/outbound-campaigns` (admin)

The admin **registry manager** for outbound campaigns (migration 0115). Add a campaign with a
**name + custom-field name + exact value + start date**: any lead carrying that field=value — in
**Close or GHL** — is counted in the campaign, from the start date onward. On **Add** it inserts
the `outbound_campaigns` row and refreshes its facts (`api/outbound_campaign_refresh.py`), so it
appears in the Outbound page's campaign dropdown with a populated funnel right away. **Edit + Re-tag**
re-runs the match after a field/value change; **Activate/Deactivate** toggles the switcher;
**Delete** removes a new-model campaign + its facts. The field-name input suggests known custom-field
names across both Close and GHL mirrors.

Campaigns are **independent** — a lead matching two is counted in both (no exclusivity). The two
finished legacy pools (Revival, Jacob) render **read-only / locked** (close_cf_id + 0103 exclusivity,
untouched). Admin-tier within the sales area. See `docs/schema/outbound_campaigns.md`.

**Revival is the Close + GHL catch-all** (migration 0118) — every revival-tagged lead (Close cf or
GHL `source`) sits in revival. **"From CSV"** option (migration 0119): upload a lead-list CSV
(email and/or phone per row) → creates a **roster campaign** matched by email/phone across **both**
CRMs (`outbound_campaign_roster` → `outbound_campaign_members`), which **carves those leads out of
revival** into their own campaign + dropdown entry. Re-tag re-resolves the list (picks up
newly-mirrored leads) and re-carves revival; Delete releases the leads back to revival.

---

## Sales bot — Slack (not a dashboard page)

A read-only **text-to-SQL Slack agent** the team @-mentions in
`SALES_BOT_SLACK_CHANNEL` to ask NL questions about sales data ("opt-ins this
week?", "Connor's connected calls last month?"). It writes guarded read-only SQL
(the `sales_bot_ro` role, migration 0113) and answers in-thread with a
dashboard-verify disclaimer. Not a page — a Slack front door onto the same data.
Code `agents/sales_bot/`; agent doc `docs/agents/sales_bot.md`; ops
`docs/runbooks/sales_bot.md`.

---

## Legacy surfaces (not the current product)

- `/[section]`, `/states`, `/trajectory` — the older v1/v2 **metric-catalog** layer
  (the 9-section / hero+sidebar kanban described in `docs/runbooks/sales_dashboard.md`,
  "~30 of ~140 LIVE"). Not in nav, not part of the funnel/leads/talent product. Treat as
  legacy until explicitly revived or removed.

## Removed — do not reference as live

- The **Calls list** page + its nav tab.
- `funnel/appointment-setting`, `funnel/closed`, `revenue/*` routes.
- The three side-by-side `bookingType` booking boxes (replaced by the stacked
  Total/Direct/Setter/Reactivation model).
- The all/unique view toggle and the Opt-in badge column on Leads.
- The **Status column** on the Leads roster (removed 2026-06-16; the lead-type
  status is still shown on the per-lead page, just not in the list).
</content>
