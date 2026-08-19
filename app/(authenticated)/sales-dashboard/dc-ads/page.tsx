import { HeaderBand } from '@/components/gregory/header-band'
import { FineNote } from '@/components/sales/fine-note'
import { AdCascadeFilter } from '@/components/sales/ad-cascade-filter'
import { DcAdsCalledSection } from '@/components/sales/dc-ads-called'
import { DcAdsDailyTable } from '@/components/sales/dc-ads-daily-table'
import { DcAdsLpSummarySection } from '@/components/sales/dc-ads-lp-summary'
import { DcAdsFunnelSection } from '@/components/sales/dc-ads-funnel'
import { DcAdsTimeOfDaySection } from '@/components/sales/dc-ads-time-of-day'
import { DcAdsAdTable } from '@/components/sales/dc-ads-ad-table'
import { DcAdsByRepSection } from '@/components/sales/dc-ads-by-rep'
import { DcAdsSpeedLeadsSection } from '@/components/sales/dc-ads-speed-leads'
import { DcAdsRosterSection } from '@/components/sales/dc-ads-roster'
import { DcAdsBreakdownButton } from '@/components/sales/dc-ads-breakdown'
import { DcAdsExecSummaryCard } from '@/components/sales/dc-ads-exec-summary'
import {
  getDcAdsFunnel,
  getDcAdsByRep,
  getDcAdsSpend,
  getDcAdsBreakdown,
  getDcAdsExecSummary,
  getDcAdsMetaOptIns,
  getDcAdsInstantFormOptIns,
  getDcAdsDaily,
  getDcAdsAdTable,
  getDcAdsHierarchy,
  getDcAdsLeadRoster,
  DC_CLOCK_LABEL,
  type DcAdsEntityFilter,
} from '@/lib/db/dc-ads'
import { getDcAdsLpSummary } from '@/lib/db/dc-ads-summary'
import { getDcTeam } from '@/lib/db/dc-setup'
import { getRepEodsByAirtableIds, type RepEod } from '@/lib/db/funnel-eods'
import { dateRangeFromExplicit, todayEtDate } from '@/lib/db/funnel-window'
import { DateRangePicker } from '../funnel/landing-pages/date-range-picker'
import { PersonPill } from '../header-pills'

// YYYY-MM-DD (ET) → "Jul 8".
function monthDay(ymd: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })
    .format(new Date(`${ymd}T12:00:00Z`))
}

// Sales Dashboard — DC Ads (top-level page).
//
// The Digital College paid-ads funnel, since the full-program suspension the
// only acquisition motion. TWO paths (migration 0130):
//   instant_form  Meta ad → instant lead form → Meta→Close bridge → reps dial
//   landing_page  Meta ad → landing page → Typeform → Close → reps dial
// The landing-page path went live 2026-07-22 and is the ACTIVE motion; the
// instant-form campaign has been paused since. Same shape as the Outbound page
// but with AD SPEND leading the funnel and opt-ins instead of outbound leads;
// scoped to dc_ads_campaigns (the registry covering both paths), never outbound
// pools and never the Closer Funnel campaigns that share the ad account.
// See lib/db/dc-ads.ts + docs/sales/surfaces.md § DC Ads.

export const dynamic = 'force-dynamic'
export const maxDuration = 60

// The first lead-form campaign launched 2026-07-08 (the "7/8 - Basic Form"
// era). Default range floor — everything since launch.
const DC_ADS_FLOOR_ET = '2026-07-08'

export default async function DcAdsPage({
  searchParams,
}: {
  searchParams?: {
    start?: string | string[]
    end?: string | string[]
    campaign?: string | string[]
    adset?: string | string[]
    ad?: string | string[]
    lp?: string | string[]
  }
}) {
  const param = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)?.trim() || null

  // Always an explicit range (no all-time mode), same contract as Outbound:
  // calendar untouched → [launch floor → today].
  const todayEt = todayEtDate()
  const startEt = param(searchParams?.start) ?? DC_ADS_FLOOR_ET
  const endEt = param(searchParams?.end) ?? todayEt

  // Ad cascade selection (?campaign / ?adset / ?ad) — same URL contract as the
  // Advertising Hub's chooser — plus the landing-page facet (?lp, an AND
  // filter; the Hub's LandingPageFilter counterpart). Values are
  // dc_landing_pages slugs ('join-training', 'go', or 'instant-form' for the
  // legacy path; 0132). Scopes everything: spend, funnel, by-rep,
  // speed-to-lead, speed-to-dial, time-of-day, and the last-5-days strip.
  const campaign = param(searchParams?.campaign)
  const adset = param(searchParams?.adset)
  const ad = param(searchParams?.ad)
  const lp = param(searchParams?.lp)
  const filter: DcAdsEntityFilter = { campaignId: campaign, adsetId: adset, adId: ad, lpSlug: lp }
  const filterActive = !!(ad || adset || campaign || lp)

  // Stage-count drill (Nabeel 2026-08-18): ?ld= (dispositions) / ?lq= (qual
  // states) preset the lead list's stacked toggles — the daily/ad tables'
  // counts link here with the matching slice lit. Unknown values drop.
  const DISPOSITIONS = ['closed', 'hvc', 'connected', 'sms', 'optin'] as const
  const QUAL_KEYS = ['qualified', 'unqualified', 'partial'] as const
  const parseList = <T extends string>(v: string | null, allowed: readonly T[]): T[] =>
    (v ?? '').split(',').filter((x): x is T => (allowed as readonly string[]).includes(x))
  const initialDispSel = parseList(param((searchParams as Record<string, string | string[]>)?.ld), DISPOSITIONS)
  const initialQualSel = parseList(param((searchParams as Record<string, string | string[]>)?.lq), QUAL_KEYS)

  // The current facet selection as a query-string fragment, so table drills
  // preserve the view they were clicked in.
  const facetQuery = new URLSearchParams(
    Object.entries({ campaign, adset, ad, lp }).filter((e): e is [string, string] => !!e[1]),
  ).toString()

  const range = dateRangeFromExplicit(startEt, endEt)
  const rangeBounds = { startUtcIso: range.startUtcIso, endUtcIso: range.endUtcIso }
  const [
    { funnel, called, timeOfDay },
    byRep,
    spend,
    metaOptIns,
    instantFormOptIns,
    dailyRows,
    hierarchy,
    adsLp,
    team,
    leadRoster,
    breakdown,
    execSummary,
  ] = await Promise.all([
    getDcAdsFunnel(rangeBounds, filter),
    getDcAdsByRep(rangeBounds, filter),
    getDcAdsSpend(startEt, endEt, filter),
    getDcAdsMetaOptIns(rangeBounds),
    getDcAdsInstantFormOptIns(rangeBounds),
    getDcAdsDaily(todayEt, filter, 30),
    getDcAdsHierarchy(rangeBounds),
    getDcAdsLpSummary(range, filter),
    getDcTeam(),
    getDcAdsLeadRoster(rangeBounds, filter),
    // Header popover (0149): always the unfiltered whole-window view — the
    // Close-style reference it reconciles against has no facets.
    getDcAdsBreakdown(rangeBounds),
    // Newest nightly AI exec summary (0152) — window-independent by design
    // (it always covers the last closed ET day); null until the first run.
    getDcAdsExecSummary(),
  ])

  // Second round: fetches that need the first round's results. The ad table
  // reuses the roster rows so its speed block, the boxes, and the lead list
  // all read the same per-lead set; the EOD map needs the team list.
  const [adTableRows, eodsByAirtableId] = await Promise.all([
    getDcAdsAdTable(range, filter, leadRoster),
    getRepEodsByAirtableIds(
      range,
      team.map((t) => t.airtableUserId).filter((v): v is string => !!v),
    ),
  ])
  const eodsByTeamMemberId: Record<string, RepEod[]> = {}
  for (const t of team) {
    if (t.airtableUserId && eodsByAirtableId[t.airtableUserId]) {
      eodsByTeamMemberId[t.id] = eodsByAirtableId[t.airtableUserId]
    }
  }

  return (
    <div>
      <HeaderBand
        eyebrow="SALES · DIGITAL COLLEGE"
        title="DC Ads."
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <DcAdsBreakdownButton data={breakdown} startEtDate={startEt} endEtDate={endEt} />
            <PersonPill label="EST · Nabeel" />
          </div>
        }
      />

      <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <AdCascadeFilter
          hierarchy={hierarchy}
          campaign={campaign}
          adset={adset}
          ad={ad}
          // With a campaign selected, offer only ITS landing pages (0138 —
          // boss: don't show the other pages). The current selection stays
          // listed either way so the dropdown can't strand itself.
          landingPages={hierarchy.landingPages
            .filter(
              (p) =>
                !campaign ||
                (hierarchy.campaignLps[campaign] ?? []).includes(p.slug) ||
                p.slug === lp,
            )
            .map((p) => ({ value: p.slug, label: p.label, count: p.count }))}
          lp={lp}
          startEtDate={startEt}
          endEtDate={endEt}
        />
        <DateRangePicker startEtDate={startEt} endEtDate={endEt} todayEt={todayEt} />
        <span
          className="geg-mono"
          title="When the first lead-form campaign started — independent of the date range"
          style={{ fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}
        >
          Started {monthDay(DC_ADS_FLOOR_ET)}
        </span>
        {/* → the AI call-intelligence subpage (2026-08-18) — carries the
            current window + facets so the two pages navigate as one. */}
        <a
          href={`/sales-dashboard/dc-ads/calls?${new URLSearchParams(
            Object.entries({ start: startEt, end: endEt, campaign, adset, ad, lp }).filter(
              (e): e is [string, string] => !!e[1],
            ),
          ).toString()}`}
          className="geg-mono"
          style={{
            fontSize: 10,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--color-geg-accent)',
            textDecoration: 'none',
            border: '1px solid var(--color-geg-border-strong)',
            borderRadius: 5,
            padding: '4px 10px',
          }}
        >
          Connected calls →
        </a>
      </div>

      {/* Bridge-drift check only reads on the unfiltered view — the Meta-side
          count isn't cascade-scoped, so comparing it under a filter would
          false-alarm. Compared against INSTANT-FORM opt-ins only: landing-page
          leads never submit a Meta form, so measuring them here would report a
          permanent phantom gap. */}
      {!filterActive && metaOptIns !== instantFormOptIns ? (
        <div
          className="geg-mono"
          style={{ marginTop: 8, fontSize: 9.5, letterSpacing: '0.04em', color: 'var(--color-geg-text-3)', lineHeight: 1.6 }}
        >
          ⚠ Meta reports {metaOptIns.toLocaleString('en-US')} ad-attributed instant-form submissions
          in this range vs {instantFormOptIns.toLocaleString('en-US')} mirrored into Close — a growing
          gap means the Meta→Close bridge is dropping leads (see
          docs/runbooks/meta_leads_ingestion.md). Landing-page opt-ins are excluded from this check:
          they never submit a Meta form.
        </div>
      ) : null}

      {/* Acquisition-path breakdown (0130). The landing-page dropdown filters
          (0131); this strip stays as the at-a-glance split — it's also the
          only place the Typeform names + counts surface. Counts are always
          the whole window (like the dropdown's), not the filtered view. */}
      {hierarchy.funnels.length > 0 ? (
        <div
          className="geg-mono"
          style={{
            marginTop: 14,
            display: 'flex',
            gap: 18,
            flexWrap: 'wrap',
            alignItems: 'baseline',
            fontSize: 10,
            letterSpacing: '0.04em',
            color: 'var(--color-geg-text-2)',
          }}
        >
          <span style={{ textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}>Paths</span>
          {hierarchy.funnels.map((f) => (
            <span key={f.label}>
              <b>{f.label}</b> {f.count.toLocaleString('en-US')}
              <span style={{ color: 'var(--color-geg-text-faint)' }}>
                {' '}
                · {f.sourceKind === 'landing_page' ? 'landing page → Typeform' : 'Meta instant form'}
              </span>
            </span>
          ))}
          {hierarchy.typeforms.map((t) => (
            <span key={t.formId} style={{ color: 'var(--color-geg-text-faint)' }}>
              Typeform <b>{t.formName}</b> {t.count.toLocaleString('en-US')}
            </span>
          ))}
        </div>
      ) : null}

      <DcAdsFunnelSection funnel={funnel} spendUsd={spend.spendUsd} />

      <DcAdsExecSummaryCard exec={execSummary} />

      <DcAdsDailyTable rows={dailyRows} todayEt={todayEt} facetQuery={facetQuery} />

      {/* The per-ad table (boss item 10) — every ad with window activity,
          full stage + speed metrics; its dropdowns narrow the list only. */}
      <DcAdsAdTable
        rows={adTableRows}
        lpLabels={Object.fromEntries(hierarchy.landingPages.map((p) => [p.slug, p.label]))}
        startEtDate={startEt}
        endEtDate={endEt}
      />

      {/* Ads + Landing page + Videos — the Hub's summary section shaped to
          the DC funnel; follows the cascade + landing-page dropdown. */}
      <DcAdsLpSummarySection summary={adsLp} />

      <DcAdsByRepSection
        rows={byRep.reps}
        totals={byRep.totals}
        activeTeamMemberIds={team.filter((t) => t.isActive).map((t) => t.id)}
        eodsByTeamMemberId={eodsByTeamMemberId}
      />

      {/* Roster — one card per human on the team (managed in DC Setup),
          DC-cohort activity only. Below the by-rep table per boss item 8. */}
      <DcAdsRosterSection team={team} reps={byRep.reps} />

      {/* Speed-to-lead boxes + the embedded lead roster, one client wrapper
          (boss 2026-08-15): the stacked toggles filter the roster AND
          recompute every speed box over the same subset. All numbers come
          from the per-lead roster rows (12p–12a ET clock, same 24h cap —
          math server-side in lib/db/dc-ads.ts, aggregation client-side). */}
      <DcAdsSpeedLeadsSection
        rows={leadRoster}
        lpLabels={Object.fromEntries(hierarchy.landingPages.map((p) => [p.slug, p.label]))}
        spendUsd={spend.spendUsd}
        clockLabel={DC_CLOCK_LABEL}
        initialDispSel={initialDispSel}
        initialQualSel={initialQualSel}
      />

      <DcAdsCalledSection called={called} />

      <FineNote style={{ marginTop: 14, letterSpacing: '0.06em', lineHeight: 1.8 }} summary="How to read this chart">
        Of the opt-ins we dialed, how fast we got to them and whether the dial connected. <b>Speed to
        dial</b> = form submit → first outbound call (the opt-in is the hand-raise — no reply needed
        first); bars stack connected (purple) over not-connected, with the connect % inside. Small n per
        bucket — read the trend, not single bars.
      </FineNote>

      <DcAdsTimeOfDaySection buckets={timeOfDay.buckets} />

      <FineNote style={{ marginTop: 14, letterSpacing: '0.06em', lineHeight: 1.8 }} summary="How to read this chart">
        When leads <b>opt in</b> vs when we <b>dial</b> vs when we <b>connect</b>, by 2-hour ET window —
        wall-clock, no business-hours adjustment. Opt-in volume that lands outside the dialing window is
        the coverage gap to staff for. Connects are timed by the call (never the form).
      </FineNote>

      <FineNote style={{ marginTop: 16, letterSpacing: '0.06em', lineHeight: 1.8 }} summary="Every definition on this page">
        Opt-ins = Digital College ad leads mirrored into Close — Meta instant form <i>and</i> landing
        page → Typeform (anchored at the form submit; a returning phone number re-anchors at its
        newest opt-in) · Qualified = the lead&apos;s own <b>Typeform</b> answered the qualifying
        question with &ldquo;Yes I can pay for the AI tools&rdquo; (matched by phone/email; instant-form
        leads have no Typeform, so they never qualify) · SMS = the lead <b>texted us back</b> (an
        inbound SMS after the opt-in; texting alone never counts as connected) · SMS+MQL = qualified{' '}
        <i>and</i> texted back · Connects = a <b>call ≥90s only</b> (either direction) — a filed form
        no longer counts as a connect, so Shows can exceed Connects when a pitch happened without a
        90-second call landing in Close · HVC = high-value connect: <b>connected and</b> (qualified{' '}
        <i>or</i> texted us) — always a subset of Connects · Units = Digital College <b>plan units</b> closed · Closed = a DC
        close <b>with an explicit plan</b> — from the DC sale form or a closer report (a closed form
        with no plan counts as a show, not a close) · Cash = $300 per plan unit · Closes, Units and
        Cash honor the team&apos;s <b>Valid</b> verdicts on the Airtable Commission table (blank/Yes
        counts; No excludes the submission; the partial options keep only the verified plan type —
        the QA note by the cash line shows what&apos;s excluded) · Adspend = the
        registered DC campaigns&apos; spend (Meta API, ET days; with only a landing page selected,
        that path&apos;s campaigns) · ROAS = cash ÷ adspend. The stage row is <b>not</b> a funnel —
        stages overlap rather than nest, so no stage need be smaller than the one before it ·{' '}
        <b>Non-attributed</b> = DC funnel leads whose ad tags were lost in transit (the forms exist
        only on the ad pages, so these are ad leads without provable attribution — ~15%); they carry
        no campaign/ad ids, so the all-campaigns view blends them into every count and cost metric —
        select a campaign for pure ad economics, or Non-attributed to see just them.
      </FineNote>
    </div>
  )
}
