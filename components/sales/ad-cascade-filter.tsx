'use client'

import { useRouter, usePathname } from 'next/navigation'
import type { ChangeEvent } from 'react'

// Campaign → Ad Set → Ad cascade filter for the Funnel page. Selecting a level
// re-scopes the whole HT funnel (and the rosters its stages link to) to that
// entity's leads, and clears the downstream selections. URL-param driven
// (?campaign / ?adset / ?ad), preserving the window; persisted by
// PersistPageState. All three levels show names; ad-set names come from the
// cortana_adset_daily medium mirror (an ad set with no name row falls back to
// its id). The option lists cascade: ad sets reflect the chosen campaign, ads
// reflect the chosen ad set.
//
// Callers with a landing-page facet (the DC Ads page) pass `landingPages` +
// `lp` to render a fourth dropdown (?lp) — the DC counterpart of the Hub's
// LandingPageFilter, filtering by acquisition path (funnel_label). Unlike the
// cascade it's an independent AND filter: picking a landing page never clears
// the cascade, and picking a cascade level never clears the landing page.

export type AdNode = { adId: string; adName: string; count: number }
export type AdsetNode = { adsetId: string; adsetName?: string; count: number; ads: AdNode[] }
export type CampaignNode = { campaignId: string; campaignName: string; count: number; adsets: AdsetNode[] }
export type AdHierarchy = { campaigns: CampaignNode[]; adsetsAll: AdsetNode[]; adsAll: AdNode[] }
export type LandingPageFacetOption = { value: string; label: string; count: number }

// Narrow fixed-width trigger (Drake 2026-06-15): the closed select clips its
// label, but the OPEN option list still shows full text — so the header row
// stays compact and never forces a horizontal scroll. Leaves room for more
// filter dropdowns (landing pages) on the wrapping filter row.
const selectStyle = {
  fontSize: 11,
  letterSpacing: '0.04em',
  color: 'var(--color-geg-text-2)',
  background: 'var(--color-geg-bg-elev)',
  border: '1px solid var(--color-geg-border)',
  borderRadius: 6,
  padding: '6px 10px',
  width: 140,
} as const

export function AdCascadeFilter({
  hierarchy,
  campaign,
  adset,
  ad,
  startEtDate,
  endEtDate,
  landingPages,
  lp,
}: {
  hierarchy: AdHierarchy
  campaign: string | null
  adset: string | null
  ad: string | null
  startEtDate: string
  endEtDate: string
  landingPages?: LandingPageFacetOption[]
  lp?: string | null
}) {
  const router = useRouter()
  const pathname = usePathname()

  function go(next: { campaign?: string; adset?: string; ad?: string; lp?: string }) {
    const p = new URLSearchParams()
    p.set('start', startEtDate)
    p.set('end', endEtDate)
    if (next.campaign) p.set('campaign', next.campaign)
    if (next.adset) p.set('adset', next.adset)
    if (next.ad) p.set('ad', next.ad)
    if (next.lp) p.set('lp', next.lp)
    router.push(`${pathname}?${p.toString()}`)
  }

  // Cascading option lists: ad sets narrow to the chosen campaign, ads to the
  // chosen ad set (falling back to all when no parent is selected).
  const campNode = hierarchy.campaigns.find((c) => c.campaignId === campaign) ?? null
  const adsetOptions = campNode ? campNode.adsets : hierarchy.adsetsAll
  const adsetNode = adsetOptions.find((a) => a.adsetId === adset) ?? null
  const adOptions = adsetNode
    ? adsetNode.ads
    : campNode
      ? campNode.adsets.flatMap((a) => a.ads)
      : hierarchy.adsAll

  // Cascade changes carry the landing page through (independent facet); the
  // landing-page change carries the whole cascade through.
  const onCampaign = (e: ChangeEvent<HTMLSelectElement>) =>
    go({ campaign: e.target.value || undefined, lp: lp || undefined }) // changing campaign clears adset + ad
  const onAdset = (e: ChangeEvent<HTMLSelectElement>) =>
    go({ campaign: campaign || undefined, adset: e.target.value || undefined, lp: lp || undefined }) // clears ad
  const onAd = (e: ChangeEvent<HTMLSelectElement>) =>
    go({ campaign: campaign || undefined, adset: adset || undefined, ad: e.target.value || undefined, lp: lp || undefined })
  const onLp = (e: ChangeEvent<HTMLSelectElement>) =>
    go({ campaign: campaign || undefined, adset: adset || undefined, ad: ad || undefined, lp: e.target.value || undefined })

  return (
    // flexWrap (mobile 2026-08-15): four fixed-width selects are ~600px of
    // min-content — without wrapping they stretched the whole page canvas on
    // a phone (THE page-wide horizontal-scroll bug). Desktop fits one row.
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <select value={campaign ?? ''} onChange={onCampaign} className="geg-mono" aria-label="Filter by campaign" style={selectStyle}>
        <option value="">All campaigns</option>
        {hierarchy.campaigns.map((c) => (
          <option key={c.campaignId} value={c.campaignId}>
            {c.campaignName} ({c.count})
          </option>
        ))}
      </select>
      <select value={adset ?? ''} onChange={onAdset} className="geg-mono" aria-label="Filter by ad set" style={selectStyle}>
        <option value="">All ad sets</option>
        {adsetOptions.map((a) => (
          <option key={a.adsetId} value={a.adsetId}>
            {a.adsetName ?? a.adsetId} ({a.count})
          </option>
        ))}
      </select>
      <select value={ad ?? ''} onChange={onAd} className="geg-mono" aria-label="Filter by ad" style={selectStyle}>
        <option value="">All ads</option>
        {adOptions.map((a) => (
          <option key={a.adId} value={a.adId}>
            {a.adName} ({a.count})
          </option>
        ))}
      </select>
      {landingPages ? (
        // Width 160 matches the Hub's LandingPageFilter trigger.
        <select
          value={lp ?? ''}
          onChange={onLp}
          className="geg-mono"
          aria-label="Filter by landing page"
          style={{ ...selectStyle, width: 160 }}
        >
          <option value="">All landing pages</option>
          {landingPages.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label} ({p.count})
            </option>
          ))}
        </select>
      ) : null}
    </div>
  )
}
