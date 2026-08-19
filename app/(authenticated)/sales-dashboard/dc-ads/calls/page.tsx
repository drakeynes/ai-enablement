import { HeaderBand } from '@/components/gregory/header-band'
import { AdCascadeFilter } from '@/components/sales/ad-cascade-filter'
import { DcAdsCallIntelSection } from '@/components/sales/dc-ads-call-intel'
import { DcRepCoachingSection } from '@/components/sales/dc-ads-rep-coaching'
import {
  getDcAdsCallIntel,
  getDcAdsHierarchy,
  getDcRepCoaching,
  type DcAdsEntityFilter,
} from '@/lib/db/dc-ads'
import { dateRangeFromExplicit, todayEtDate } from '@/lib/db/funnel-window'
import { DateRangePicker } from '../../funnel/landing-pages/date-range-picker'
import { PersonPill } from '../../header-pills'

// Sales Dashboard — Connected Calls (own sidebar entry since the boss's
// same-day feedback; route stays nested under /dc-ads for the middleware
// allowlist).
//
// The AI call-intelligence surface (Nabeel's build list): every connected
// call on a DC-ads cohort lead with its dc_ads-rubric review — the calls
// FEED leads the page (labeled table), then the why-not-closing
// distribution, missed-sales / great-saves queues, archetypes, and
// voice-of-customer quotes. Same URL contract as the DC Ads page
// (?start/?end + cascade + ?lp) so the two navigate as one surface.
// Data: dc_ads_call_reviews() behind getDcAdsCallIntel (lib/db/dc-ads.ts).
// Scoring is forward-only from 2026-08-18 — see docs/sales/surfaces.md.

export const dynamic = 'force-dynamic'
export const maxDuration = 60

// Default window floor = the ads-page floor: the 0150-rubric backfill
// re-graded the cohort's earlier calls, so history is populated back to
// the first lead-form campaign.
const DC_AI_FLOOR_ET = '2026-07-08'

export default async function DcAdsCallsPage({
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

  const todayEt = todayEtDate()
  const startEt = param(searchParams?.start) ?? DC_AI_FLOOR_ET
  const endEt = param(searchParams?.end) ?? todayEt
  const campaign = param(searchParams?.campaign)
  const adset = param(searchParams?.adset)
  const ad = param(searchParams?.ad)
  const lp = param(searchParams?.lp)
  const filter: DcAdsEntityFilter = { campaignId: campaign, adsetId: adset, adId: ad, lpSlug: lp }

  const range = dateRangeFromExplicit(startEt, endEt)
  const rangeBounds = { startUtcIso: range.startUtcIso, endUtcIso: range.endUtcIso }

  const [intel, hierarchy, coaching] = await Promise.all([
    getDcAdsCallIntel(rangeBounds, filter),
    getDcAdsHierarchy(rangeBounds),
    // Newest generated week (0152) — window-independent; empty until the
    // first Monday cron run.
    getDcRepCoaching(),
  ])

  return (
    <div>
      <HeaderBand
        eyebrow="SALES · DIGITAL COLLEGE"
        title="Connected Calls."
        backlink={{ href: '/sales-dashboard/dc-ads', label: 'Back to DC Ads' }}
        actions={<PersonPill label="EST · Nabeel" />}
      />

      <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <AdCascadeFilter
          hierarchy={hierarchy}
          campaign={campaign}
          adset={adset}
          ad={ad}
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
      </div>

      <DcAdsCallIntelSection intel={intel} />

      <DcRepCoachingSection rows={coaching} />
    </div>
  )
}
