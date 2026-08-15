import 'server-only'

import { createAdminClient } from '@/lib/supabase/admin'
import { getTypVideoMetrics, getVslMetrics, type VideoMetrics } from './funnel-lp'
import type { DateRange } from './funnel-window'
import { INSTANT_FORM_SLUG, spendScope, type DcAdsEntityFilter } from './dc-ads'

// DC Ads — the inline Ads + Landing-Page summary (the Hub's AdsLpSummary
// counterpart, Drake 2026-08-13). Three blocks under the daily strip:
//
//   Meta ads       cortana_* mirrors over the ACTIVE SELECTION (cascade
//                  deepest entity wins, else the landing page, else every
//                  registered DC campaign) — same scoping the spend node uses.
//   Landing page   FOLLOWS THE CASCADE since 2026-08-15 (boss item 9 — was
//                  Hub semantics, LP dropdown + window only): visits = the
//                  selection's Meta unique link clicks (same scope as the ads
//                  block), and Typeform submissions filter by the response's
//                  hidden campaign/adset/ad ids when a cascade entity is
//                  selected (deepest wins). ~1 in 6 submissions arrives
//                  without the hidden ids (untagged path to the form —
//                  return visits, rep-sent links, unfilled Meta macros) and
//                  is EXCLUDED under a selection — footnoted on the page.
//                  Starts/completion need Typeform's Insights API, which we
//                  don't mirror — same gap as the Hub.
//   Videos         wistia_media_daily via the SAME getVslMetrics math the Hub
//                  uses (no drift), over the LP's registered videos
//                  (dc_landing_pages.vsl — auto-attached by the Wistia
//                  embed-location scan). ⚠ Wistia stats are per-VIDEO across
//                  all its embeds: DC_VSL_Thank you_v2 plays on BOTH funnels,
//                  so an LP selection scopes WHICH videos show, not where
//                  they were watched.

export type DcAdsSummaryBlock = {
  adspend: number | null
  impressions: number | null
  uniqueClicks: number | null
  ctr: number | null // 0..100
  cpm: number | null
  cpcUnique: number | null
  frequency: number | null
}

export type DcAdsLpSummary = {
  ads: DcAdsSummaryBlock
  lpLabel: string
  lpVisits: number | null
  lpConversionPct: number | null
  typeformSubmits: number | null
  typeformLabel: string | null
  vsl: VideoMetrics | null
  confirm: VideoMetrics | null
  // True when a cascade entity (campaign/adset/ad) narrowed the LP block —
  // the page footnotes the attributed-submissions caveat.
  cascadeScoped: boolean
  // Cascade + a specific LP both selected, and the dc_meta_ads registry
  // (0146) had the selection's ads: visits were SPLIT to only the ads whose
  // creative points at this LP (the boss's "count the ads within the
  // campaign" rule, 2026-08-15).
  lpVariantSplit: boolean
  // Cascade + LP both selected but the registry couldn't split (no rows yet —
  // e.g. first tick after deploy): visits are the selection's total clicks.
  lpVariantNote: boolean
}

type LpRow = {
  slug: string
  label: string
  typeform_id: string | null
  vsl: Array<{ hashedId: string; label: string }>
  confirm_video_hashed_id: string | null
  confirm_video_label: string | null
}

// Sum a cortana_* scope over the ET window and derive the rates from the
// summed base (mirrors the Hub's adsSummaryForEntity — never average rates).
async function adsAggregate(
  scope: { table: string; ids: string[] },
  range: DateRange,
): Promise<DcAdsSummaryBlock> {
  const empty: DcAdsSummaryBlock = {
    adspend: null, impressions: null, uniqueClicks: null,
    ctr: null, cpm: null, cpcUnique: null, frequency: null,
  }
  if (scope.ids.length === 0) return empty
  const sb = createAdminClient()
  const { data, error } = await sb
    .from(scope.table as never)
    .select('spent, impressions, reach, unique_clicks')
    .in('platform_entity_id', scope.ids)
    .gte('day', range.startEtDate)
    .lte('day', range.endEtDate)
  if (error) throw new Error(`${scope.table} summary read failed: ${error.message}`)
  const rows = (data ?? []) as Array<{
    spent: unknown; impressions: unknown; reach: unknown; unique_clicks: unknown
  }>
  const n = (v: unknown): number => (Number.isFinite(Number(v)) ? Number(v) : 0)
  const spent = rows.reduce((a, r) => a + n(r.spent), 0)
  const impressions = rows.reduce((a, r) => a + n(r.impressions), 0)
  const reach = rows.reduce((a, r) => a + n(r.reach), 0)
  const uniqueClicks = rows.reduce((a, r) => a + n(r.unique_clicks), 0)
  return {
    adspend: spent,
    impressions,
    uniqueClicks,
    ctr: impressions > 0 ? (uniqueClicks / impressions) * 100 : null,
    cpm: impressions > 0 ? (spent / impressions) * 1000 : null,
    cpcUnique: uniqueClicks > 0 ? spent / uniqueClicks : null,
    frequency: reach > 0 ? impressions / reach : null,
  }
}

export async function getDcAdsLpSummary(
  range: DateRange,
  filter: DcAdsEntityFilter,
): Promise<DcAdsLpSummary> {
  const sb = createAdminClient()
  const [{ data: lpData, error }, { data: campData, error: cErr }] = await Promise.all([
    sb
      .from('dc_landing_pages' as never)
      .select('slug, label, typeform_id, vsl, confirm_video_hashed_id, confirm_video_label')
      .eq('active', true)
      .order('sort_order', { ascending: true }),
    sb.from('dc_ads_campaigns' as never).select('lp_slug, lp_slugs').eq('active', true),
  ])
  if (error) throw new Error(`dc_landing_pages read failed: ${error.message}`)
  if (cErr) throw new Error(`dc_ads_campaigns read failed: ${cErr.message}`)
  const allLps = (lpData ?? []) as unknown as LpRow[]

  // "All landing pages" = the pages ACTIVE campaigns drive to (boss
  // 2026-08-14) — a registered page no live campaign uses stays out of the
  // aggregate. A directly selected page still resolves either way.
  const linked = new Set<string>()
  for (const c of (campData ?? []) as Array<{ lp_slug: string | null; lp_slugs: string[] | null }>) {
    for (const s of c.lp_slugs?.length ? c.lp_slugs : c.lp_slug ? [c.lp_slug] : []) linked.add(s)
  }
  const lps = allLps.filter((l) => linked.has(l.slug))

  const isInstant = filter.lpSlug === INSTANT_FORM_SLUG
  const selected = !isInstant && filter.lpSlug ? (allLps.find((l) => l.slug === filter.lpSlug) ?? null) : null
  // Cascade entities with a Typeform-side counterpart (hidden campaign/adset/
  // ad ids). p_form_id (Meta instant form) has none — its visits still follow
  // spendScope, but submissions can't narrow by it (facet unreachable from
  // the UI today).
  const cascadeScoped = !!(filter.adId || filter.adsetId || filter.campaignId)

  // Since 2026-08-15 (boss item 9) the LP block follows the FULL selection —
  // visits are the same scope the ads block reads, one read for both.
  const adsScope = await spendScope(filter)
  const ads = await adsAggregate(adsScope, range)
  let lpVisits = ads.uniqueClicks

  // Cascade + a specific LP: split visits to only the selection's ads whose
  // creative points at THIS page (dc_meta_ads, 0146) — a split-test campaign
  // stops showing both variants' clicks under one LP. Falls back to the
  // selection's total (footnoted) until the registry has the ads.
  let lpVariantSplit = false
  if (cascadeScoped && selected) {
    let regQuery = sb
      .from('dc_meta_ads' as never)
      .select('ad_id')
      .eq('lp_slug', selected.slug)
    if (filter.adId) regQuery = regQuery.eq('ad_id', filter.adId)
    else if (filter.adsetId) regQuery = regQuery.eq('adset_id', filter.adsetId)
    else if (filter.campaignId) regQuery = regQuery.eq('campaign_id', filter.campaignId)
    const { data: regAds, error: regErr } = await regQuery
    if (regErr) throw new Error(`dc_meta_ads read failed: ${regErr.message}`)
    const adIds = ((regAds ?? []) as Array<{ ad_id: string }>).map((r) => r.ad_id)
    if (adIds.length > 0) {
      const lpAds = await adsAggregate({ table: 'cortana_ad_daily', ids: adIds }, range)
      lpVisits = lpAds.uniqueClicks
      lpVariantSplit = true
    }
  }

  // Typeform submissions — the selected LP's form, or every registered DC
  // form. The instant-form path has no Typeform (its opt-in IS the Meta form).
  const formIds = isInstant
    ? []
    : selected
      ? (selected.typeform_id ? [selected.typeform_id] : [])
      : Array.from(new Set(lps.map((l) => l.typeform_id).filter((id): id is string => !!id)))
  let typeformSubmits: number | null = null
  let typeformLabel: string | null = null
  if (formIds.length > 0) {
    let submitsQuery = sb
      .from('typeform_responses' as never)
      .select('response_id', { count: 'exact', head: true })
      .in('form_id', formIds)
      .gte('submitted_at', range.startUtcIso)
      .lt('submitted_at', range.endUtcIso)
    // Cascade attribution via the response's hidden fields (deepest wins) —
    // the LPs pass Meta's URL macros into the Typeform embed, so ~5 in 6
    // submissions carry these ids; untagged arrivals are excluded here and
    // footnoted on the page.
    if (filter.adId) submitsQuery = submitsQuery.eq('hidden->>ad_id', filter.adId)
    else if (filter.adsetId) submitsQuery = submitsQuery.eq('hidden->>adset_id', filter.adsetId)
    else if (filter.campaignId) submitsQuery = submitsQuery.eq('hidden->>campaign_id', filter.campaignId)
    const [{ count, error: sErr }, { data: titles, error: tErr }] = await Promise.all([
      submitsQuery,
      sb.from('typeform_forms' as never).select('form_id, title').in('form_id', formIds),
    ])
    if (sErr) throw new Error(`typeform_responses count failed: ${sErr.message}`)
    if (tErr) throw new Error(`typeform_forms read failed: ${tErr.message}`)
    typeformSubmits = count ?? 0
    const titleRows = (titles ?? []) as Array<{ form_id: string; title: string | null }>
    typeformLabel =
      titleRows.map((t) => t.title ?? t.form_id).join(' + ') || formIds.join(' + ')
  }

  // Videos — the selection's registered videos, deduped (funnels share the
  // VSL today). One unique video keeps its own name; several combine.
  const vslOptions = isInstant ? [] : selected ? selected.vsl : lps.flatMap((l) => l.vsl)
  const uniqueVsl = Array.from(
    new Map(vslOptions.map((v) => [v.hashedId, v])).values(),
  )
  const confirmSource = selected ?? lps[0] ?? null
  const confirmId = isInstant ? null : (confirmSource?.confirm_video_hashed_id ?? null)
  const [vsl, confirm] = await Promise.all([
    uniqueVsl.length === 0
      ? Promise.resolve(null)
      : uniqueVsl.length === 1
        ? getVslMetrics(range, uniqueVsl, uniqueVsl[0].hashedId)
        : getVslMetrics(range, uniqueVsl, undefined, true),
    confirmId
      ? getTypVideoMetrics(range, confirmId, confirmSource?.confirm_video_label ?? 'Confirmation video')
      : Promise.resolve(null),
  ])

  return {
    ads,
    lpLabel: isInstant
      ? 'Instant form (no LP)'
      : (selected?.label ?? 'All landing pages'),
    lpVisits,
    lpConversionPct:
      lpVisits && lpVisits > 0 && typeformSubmits != null
        ? (typeformSubmits / lpVisits) * 100
        : null,
    typeformSubmits,
    typeformLabel,
    vsl,
    confirm,
    cascadeScoped,
    lpVariantSplit,
    lpVariantNote: cascadeScoped && !!selected && !lpVariantSplit,
  }
}
