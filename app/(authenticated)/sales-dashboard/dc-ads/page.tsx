import { HeaderBand } from '@/components/gregory/header-band'
import { AdCascadeFilter } from '@/components/sales/ad-cascade-filter'
import { DcAdsCalledSection } from '@/components/sales/dc-ads-called'
import { DcAdsDailyTable } from '@/components/sales/dc-ads-daily-table'
import { DcAdsLpSummarySection } from '@/components/sales/dc-ads-lp-summary'
import { DcAdsFunnelSection } from '@/components/sales/dc-ads-funnel'
import { DcAdsTimeOfDaySection } from '@/components/sales/dc-ads-time-of-day'
import { DcAdsByRepSection } from '@/components/sales/dc-ads-by-rep'
import { SpeedToLeadBoxes } from '@/components/sales/speed-to-lead-boxes'
import {
  getDcAdsFunnel,
  getDcAdsByRep,
  getDcAdsSpend,
  getDcAdsMetaOptIns,
  getDcAdsInstantFormOptIns,
  getDcAdsDaily,
  getDcAdsHierarchy,
  getDcAdsSpeedCohort,
  type DcAdsEntityFilter,
} from '@/lib/db/dc-ads'
import { getDcAdsLpSummary } from '@/lib/db/dc-ads-summary'
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
    speedCohort,
    adsLp,
  ] = await Promise.all([
    getDcAdsFunnel(rangeBounds, filter),
    getDcAdsByRep(rangeBounds, filter),
    getDcAdsSpend(startEt, endEt, filter),
    getDcAdsMetaOptIns(rangeBounds),
    getDcAdsInstantFormOptIns(rangeBounds),
    getDcAdsDaily(todayEt, filter),
    getDcAdsHierarchy(rangeBounds),
    getDcAdsSpeedCohort(rangeBounds, filter),
    getDcAdsLpSummary(range, filter),
  ])

  return (
    <div>
      <HeaderBand
        eyebrow="SALES · DIGITAL COLLEGE"
        title="DC Ads."
        actions={<PersonPill label="EST · Nabeel" />}
      />

      <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <AdCascadeFilter
          hierarchy={hierarchy}
          campaign={campaign}
          adset={adset}
          ad={ad}
          landingPages={hierarchy.landingPages.map((p) => ({ value: p.slug, label: p.label, count: p.count }))}
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

      <DcAdsDailyTable rows={dailyRows} />

      {/* Ads + Landing page + Videos — the Hub's summary section shaped to
          the DC funnel; follows the cascade + landing-page dropdown. */}
      <DcAdsLpSummarySection summary={adsLp} />

      <DcAdsByRepSection rows={byRep.reps} totals={byRep.totals} />

      {/* Speed-to-lead boxes — the Leads page's four top-line stats, computed
          over the DC ads opt-in cohort only (same 10a–10p ET business-hours
          clock + 24h cap, so the numbers are comparable across pages). */}
      <div style={{ marginTop: 26 }}>
        <div
          className="geg-mono"
          style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 10 }}
        >
          Speed to lead · DC ad opt-ins · selected dates
        </div>
        <SpeedToLeadBoxes
          cohort={speedCohort}
          connectedLeads={speedCohort.connectedBroad}
          connectedDenominator={speedCohort.dialedOrConnected}
        />
      </div>

      <DcAdsCalledSection called={called} />

      <div
        className="geg-mono"
        style={{ marginTop: 14, fontSize: 9, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.8 }}
      >
        Of the opt-ins we dialed, how fast we got to them and whether the dial connected. <b>Speed to
        dial</b> = form submit → first outbound call (the opt-in is the hand-raise — no reply needed
        first); bars stack connected (purple) over not-connected, with the connect % inside. Small n per
        bucket — read the trend, not single bars.
      </div>

      <DcAdsTimeOfDaySection buckets={timeOfDay.buckets} />

      <div
        className="geg-mono"
        style={{ marginTop: 14, fontSize: 9, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.8 }}
      >
        When leads <b>opt in</b> vs when we <b>dial</b> vs when we <b>connect</b>, by 2-hour ET window —
        wall-clock, no business-hours adjustment. Opt-in volume that lands outside the dialing window is
        the coverage gap to staff for. Connects are timed by the call (never the form).
      </div>

      <div
        className="geg-mono"
        style={{ marginTop: 16, fontSize: 9, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.8 }}
      >
        Opt-ins = Digital College ad leads mirrored into Close — Meta instant form <i>and</i> landing
        page → Typeform (anchored at the form submit; a returning phone number re-anchors at its
        newest opt-in) · Qualified = the lead&apos;s own <b>Typeform</b> answered the qualifying
        question with &ldquo;Yes I can pay for the AI tools&rdquo; (matched by phone/email; instant-form
        leads have no Typeform, so they never qualify) · SMS = the lead <b>texted us back</b> (an
        inbound SMS after the opt-in) · SMS+MQL = qualified <i>and</i> texted back · Connects = a{' '}
        <b>call ≥90s</b> (either direction) or a filed pitch form · HVC = high-value connect —
        SMS+MQL <i>or</i> a connect · Units = Digital College <b>plan units</b> closed · Closed = a DC
        close <b>with an explicit plan</b> — from the DC sale form or a closer report (a closed form
        with no plan counts as a show, not a close) · Cash = $300 per plan unit · Adspend = the
        registered DC campaigns&apos; spend (Meta API, ET days; with only a landing page selected,
        that path&apos;s campaigns) · ROAS = cash ÷ adspend. The stage row is <b>not</b> a funnel —
        stages overlap rather than nest, so no stage need be smaller than the one before it.
      </div>
    </div>
  )
}
