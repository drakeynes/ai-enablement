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
//   Landing page   visits = Meta unique link clicks of the LP SCOPE ONLY
//                  (the LP block follows the LP dropdown + window, never the
//                  ad cascade — Hub semantics), + Typeform submissions from
//                  the typeform_responses mirror. Starts/completion need
//                  Typeform's Insights API, which we don't mirror — same gap
//                  as the Hub.
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
  const cascadeActive = !!(filter.adId || filter.adsetId || filter.campaignId || filter.formId)

  // Ads block follows the full selection; the LP block ignores the cascade.
  // When no cascade entity is active the two scopes are identical — one read.
  const lpOnly: DcAdsEntityFilter = { lpSlug: filter.lpSlug }
  const [adsScope, lpScope] = await Promise.all([
    spendScope(filter),
    cascadeActive ? spendScope(lpOnly) : Promise.resolve(null),
  ])
  const [ads, lpAds] = await Promise.all([
    adsAggregate(adsScope, range),
    lpScope ? adsAggregate(lpScope, range) : Promise.resolve(null),
  ])
  const lpVisits = (lpAds ?? ads).uniqueClicks

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
    const [{ count, error: sErr }, { data: titles, error: tErr }] = await Promise.all([
      sb
        .from('typeform_responses' as never)
        .select('response_id', { count: 'exact', head: true })
        .in('form_id', formIds)
        .gte('submitted_at', range.startUtcIso)
        .lt('submitted_at', range.endUtcIso),
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
  }
}
