import 'server-only'

import { createAdminClient } from '@/lib/supabase/admin'
import { businessHoursElapsedSec } from '@/lib/time/est-periods'
import { summarizeCohortRows, type CohortStats } from './funnel-appointment-setting'
import type { DcPlanCounts } from './funnel-dc'

// DC ads funnel — the Digital College paid-ads funnel, on its own
// /sales-dashboard/dc-ads page. Sibling of the Outbound page's data layer
// (lib/db/funnel-revival.ts): same materialized-facts pattern, different
// membership + anchor (migrations 0122–0130).
//
// TWO acquisition paths since 2026-07-22 (migration 0130):
//   instant_form  — Meta ad → Meta instant form → Close      (the original)
//   landing_page  — Meta ad → LP → Typeform → Close          (the live motion)
// Both are scoped by dc_ads_campaigns, THE campaign registry. Never widen this
// to "all OFFSITE_CONVERSIONS campaigns": the same ad account runs the
// unrelated ANDROMEDA / Closer Funnel motion against theaipartner.io.
//
// Sources, all Supabase (never the Meta API from here):
//   dc_ads_funnel() / dc_ads_funnel_by_rep()  — per-lead facts rollups
//     (dc_ads_lead_facts: close_leads on a campaign in dc_ads_campaigns,
//     anchored at the opt-in; carries source_kind/funnel_label/typeform_id)
//   cortana_campaign_daily × dc_ads_campaigns — the AD SPEND in front of the
//     funnel, scoped to the registry (the cortana_* tables kept their legacy
//     name but are fed by the Meta API since the 2026-06-30 cutover)
//   meta_form_leads — the Meta-side opt-in count for the instant-form path
//     (bridge-drift check; landing-page leads never appear here)

export type DcAdsFunnel = {
  optIns: number
  called: number
  connected: number
  booked: number
  bookedDc: number
  bookedHt: number
  showed: number
  closed: number
  closedPlans: DcPlanCounts
  cashUsd: number
  markedNoPlan: number
}

export type DcAdsSpeedBucket = { label: string; count: number; connected: number }

export type DcAdsCalled = {
  optIns: number
  called: number
  connected: number
  notCalled: number
  speed: DcAdsSpeedBucket[]
  speedN: number
  speedMedianMin: number | null
}

export type DcAdsHourBucket = { label: string; optIns: number; dials: number; connects: number }

export type DcAdsRepRow = {
  rep: string
  dials: number
  connections: number
  closes: number
  cash: number
}

export type DcAdsRepTotals = {
  closes: number
  base44Monthly: number
  base44Yearly: number
  wixMonthly: number
  wixYearly: number
}

export type DcAdsByRep = { reps: DcAdsRepRow[]; totals: DcAdsRepTotals }

const TOD_LABELS = ['12a', '2a', '4a', '6a', '8a', '10a', '12p', '2p', '4p', '6p', '8p', '10p']

// The page's ad-cascade selection (campaign → ad set → ad) plus the
// landing-page facet. Cascade: deepest wins — the RPC args carry only the
// deepest id, mirroring the Advertising Hub. The landing page (funnelLabel,
// matching dc_ads_lead_facts.funnel_label — 'Aman Funnel', 'Luke Funnel',
// 'Digital College') is an independent AND facet (a path spans many ads), so
// it composes with the cascade instead of competing. formId (the Meta instant
// form, 0128) stays supported at this layer — the forms dropdown left the
// page's filter row (0131) but the facet is planned to resurface in its own
// forms section.
export type DcAdsEntityFilter = {
  campaignId?: string | null
  adsetId?: string | null
  adId?: string | null
  formId?: string | null
  funnelLabel?: string | null
}

function entityArgs(filter?: DcAdsEntityFilter): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  if (filter?.adId) args.p_ad_id = filter.adId
  else if (filter?.adsetId) args.p_adset_id = filter.adsetId
  else if (filter?.campaignId) args.p_campaign_id = filter.campaignId
  if (filter?.formId) args.p_form_id = filter.formId
  if (filter?.funnelLabel) args.p_funnel_label = filter.funnelLabel
  return args
}

type RawDcAds = {
  funnel: DcAdsFunnel
  called: Omit<DcAdsCalled, 'speed'> & { buckets: DcAdsSpeedBucket[] }
  timeOfDay: { optIns: number; dials: number; connects: number }[]
  activeFrom: string | null
  activeTo: string | null
}

// Cohort funnel + speed-to-dial + time-of-day, scoped by opt-in anchor (and
// optionally to one campaign/adset/ad).
export async function getDcAdsFunnel(
  range?: { startUtcIso: string; endUtcIso: string },
  filter?: DcAdsEntityFilter,
): Promise<{
  funnel: DcAdsFunnel
  called: DcAdsCalled
  timeOfDay: { buckets: DcAdsHourBucket[] }
  activeFrom: string | null
  activeTo: string | null
}> {
  const sb = createAdminClient()
  const args: Record<string, unknown> = { ...entityArgs(filter) }
  if (range) {
    args.p_start = range.startUtcIso
    args.p_end = range.endUtcIso
  }
  const { data, error } = await sb.rpc('dc_ads_funnel' as never, args as never)
  if (error) throw new Error(`dc_ads_funnel RPC failed: ${error.message}`)
  const r = data as unknown as RawDcAds

  return {
    funnel: r.funnel,
    called: {
      optIns: r.called.optIns,
      called: r.called.called,
      connected: r.called.connected,
      notCalled: r.called.notCalled,
      speed: r.called.buckets,
      speedN: r.called.speedN,
      speedMedianMin: r.called.speedMedianMin,
    },
    timeOfDay: {
      buckets: r.timeOfDay.map((b, i) => ({
        label: TOD_LABELS[i] ?? '',
        optIns: b.optIns,
        dials: b.dials,
        connects: b.connects,
      })),
    },
    activeFrom: r.activeFrom ?? null,
    activeTo: r.activeTo ?? null,
  }
}

// Per-rep breakdown. ACTIVITY-scoped like outbound's: calls by activity_at,
// closes by form date, within [start, end). Unlike outbound (closers only),
// every rep with any activity is listed — the DC ads pool is dial-heavy and
// closes are the rare event.
export async function getDcAdsByRep(
  range: { startUtcIso: string; endUtcIso: string },
  filter?: DcAdsEntityFilter,
): Promise<DcAdsByRep> {
  const sb = createAdminClient()
  const { data, error } = await sb.rpc('dc_ads_funnel_by_rep' as never, {
    p_start: range.startUtcIso,
    p_end: range.endUtcIso,
    ...entityArgs(filter),
  } as never)
  if (error) throw new Error(`dc_ads_funnel_by_rep RPC failed: ${error.message}`)
  const d = data as unknown as DcAdsByRep | null
  return {
    reps: d?.reps ?? [],
    totals: d?.totals ?? { closes: 0, base44Monthly: 0, base44Yearly: 0, wixMonthly: 0, wixYearly: 0 },
  }
}

// Which cortana_* mirror + entity ids feed the spend read for the active
// cascade selection. Deepest wins: ad → cortana_ad_daily, ad set →
// cortana_adset_daily, campaign → cortana_campaign_daily (that id only). A
// form-only selection maps to the ads that served that form (a form is not a
// Meta spend entity; its ads are); a landing-page-only selection maps to the
// registry campaigns carrying that funnel_label (a lead whose Close-side label
// matches no registry campaign — rare cross-tagging — reads as $0 spend).
// When a cascade entity is selected alongside either facet, the entity wins
// the spend read while the funnel ANDs everything. No selection →
// cortana_campaign_daily over the whole dc_ads_campaigns registry.
async function spendScope(
  filter?: DcAdsEntityFilter,
): Promise<{ table: string; ids: string[]; campaigns: number }> {
  const sb = createAdminClient()
  const { data: camps, error } = await sb
    .from('dc_ads_campaigns' as never)
    .select('campaign_id, funnel_label')
    .eq('active', true)
  if (error) throw new Error(`dc_ads_campaigns read failed: ${error.message}`)
  const rows = (camps ?? []) as Array<{ campaign_id: string; funnel_label: string | null }>
  const all = rows.map((c) => c.campaign_id)
  if (filter?.adId) return { table: 'cortana_ad_daily', ids: [filter.adId], campaigns: all.length }
  if (filter?.adsetId) return { table: 'cortana_adset_daily', ids: [filter.adsetId], campaigns: all.length }
  if (filter?.campaignId)
    return { table: 'cortana_campaign_daily', ids: [filter.campaignId], campaigns: all.length }
  if (filter?.formId) {
    const { data: ads, error: aErr } = await sb
      .from('meta_form_leads' as never)
      .select('ad_id')
      .eq('form_id', filter.formId)
      .not('ad_id', 'is', null)
      .limit(10000)
    if (aErr) throw new Error(`meta_form_leads form-ads read failed: ${aErr.message}`)
    const ids = Array.from(new Set(((ads ?? []) as Array<{ ad_id: string }>).map((r) => r.ad_id)))
    return { table: 'cortana_ad_daily', ids, campaigns: all.length }
  }
  if (filter?.funnelLabel) {
    const ids = rows.filter((c) => c.funnel_label === filter.funnelLabel).map((c) => c.campaign_id)
    return { table: 'cortana_campaign_daily', ids, campaigns: all.length }
  }
  return { table: 'cortana_campaign_daily', ids: all, campaigns: all.length }
}

// Ad spend for the funnel's front node (Meta-API-fed cortana_* mirrors), scoped
// to the lead-form campaigns — or to the active cascade selection. ET calendar
// dates, inclusive.
export async function getDcAdsSpend(
  startEtDate: string,
  endEtDate: string,
  filter?: DcAdsEntityFilter,
): Promise<{ spendUsd: number; campaigns: number }> {
  const sb = createAdminClient()
  const scope = await spendScope(filter)
  if (scope.ids.length === 0) return { spendUsd: 0, campaigns: 0 }

  const { data, error } = await sb
    .from(scope.table as never)
    .select('spent')
    .in('platform_entity_id', scope.ids)
    .gte('day', startEtDate)
    .lte('day', endEtDate)
  if (error) throw new Error(`dc ads spend read failed: ${error.message}`)
  const spend = ((data ?? []) as Array<{ spent: number | null }>).reduce((a, r) => a + (r.spent ?? 0), 0)
  return { spendUsd: spend, campaigns: scope.campaigns }
}

// The last-5-days strip: per-ET-day cohort rows (opt-ins that day + lifetime
// progression + dials received), newest first — the DC sibling of the hub's
// getDailyFunnelTable, minus speed-to-lead and bookings. Pinned to the rolling
// strip regardless of the date picker; scoped to the cascade selection.
export type DcAdsDailyRow = {
  etDate: string
  spendUsd: number | null
  optIns: number
  called: number
  connected: number
  closed: number
  cashUsd: number
  dials: number
}

export async function getDcAdsDaily(
  endEtDate: string,
  filter?: DcAdsEntityFilter,
  days = 5,
): Promise<DcAdsDailyRow[]> {
  const sb = createAdminClient()
  const [{ data, error }, scope] = await Promise.all([
    sb.rpc('dc_ads_daily' as never, {
      p_end_et: endEtDate,
      p_days: days,
      ...entityArgs(filter),
    } as never),
    spendScope(filter),
  ])
  if (error) throw new Error(`dc_ads_daily RPC failed: ${error.message}`)
  const rows = (data ?? []) as unknown as Array<Omit<DcAdsDailyRow, 'spendUsd'>>
  if (rows.length === 0) return []

  const daySpend = new Map<string, number>()
  if (scope.ids.length > 0) {
    const etDates = rows.map((r) => r.etDate)
    const { data: spendRows, error: sErr } = await sb
      .from(scope.table as never)
      .select('day, spent')
      .in('platform_entity_id', scope.ids)
      .gte('day', etDates[etDates.length - 1])
      .lte('day', etDates[0])
    if (sErr) throw new Error(`dc ads daily spend read failed: ${sErr.message}`)
    for (const r of (spendRows ?? []) as Array<{ day: string; spent: number | null }>) {
      daySpend.set(r.day, (daySpend.get(r.day) ?? 0) + (r.spent ?? 0))
    }
  }
  return rows.map((r) => ({ ...r, spendUsd: daySpend.get(r.etDate) ?? null }))
}

// Campaign → Ad Set → Ad hierarchy for the cascade chooser, built from the
// window's Meta form submissions (meta_form_leads carries every level's id AND
// name natively — no adset-name mirror lookup needed). Counts are form opt-ins.
export type DcAdNode = { adId: string; adName: string; count: number }
export type DcAdsetNode = { adsetId: string; adsetName?: string; count: number; ads: DcAdNode[] }
export type DcCampaignNode = {
  campaignId: string
  campaignName: string
  count: number
  adsets: DcAdsetNode[]
}
// The Forms facet options — Meta runs more than one instant form ("7/8 -
// Basic Form", "7/13 - Basic Form", …). Counts are ad-attributed submissions
// in the window, same source as the cascade counts; names come from the
// meta_lead_forms registry.
export type DcFormOption = { formId: string; formName: string; count: number }
// The funnel facet (0130): which acquisition path an opt-in came through —
// 'Digital College' (instant form) vs 'Aman Funnel' / 'Luke Funnel' (the
// landing-page + Typeform motions). Labels are the Close funnel_name.
export type DcFunnelOption = { label: string; sourceKind: string | null; count: number }
export type DcAdHierarchy = {
  campaigns: DcCampaignNode[]
  adsetsAll: DcAdsetNode[]
  adsAll: DcAdNode[]
  forms: DcFormOption[]
  typeforms: DcFormOption[]
  funnels: DcFunnelOption[]
}

// Entity-id → display-name, from the Meta-fed spend mirror. One row per entity
// per day, so dedupe (last non-null wins); these are the only tables carrying
// adset/ad names for LANDING-PAGE campaigns, which never appear in
// meta_form_leads.
async function entityNames(
  sb: ReturnType<typeof createAdminClient>,
  table: string,
  ids: string[],
): Promise<Map<string, string>> {
  const out = new Map<string, string>()
  if (ids.length === 0) return out
  const { data, error } = await sb
    .from(table as never)
    .select('platform_entity_id, entity_name')
    .in('platform_entity_id', ids)
    .limit(20000)
  if (error) throw new Error(`${table} name read failed: ${error.message}`)
  for (const r of (data ?? []) as Array<{ platform_entity_id: string; entity_name: string | null }>) {
    if (r.entity_name) out.set(r.platform_entity_id, r.entity_name)
  }
  return out
}

export async function getDcAdsHierarchy(range: {
  startUtcIso: string
  endUtcIso: string
}): Promise<DcAdHierarchy> {
  const sb = createAdminClient()
  // Sourced from the FACTS table, not meta_form_leads. Landing-page opt-ins
  // never submit a Meta instant form, so building the cascade from
  // meta_form_leads hid every LP campaign from the dropdown regardless of
  // spend — half of the 0130 bug (the other half was facts membership).
  const [{ data, error }, { data: formRows, error: fErr }, { data: tfRows, error: tErr }] =
    await Promise.all([
      sb
        .from('dc_ads_lead_facts' as never)
        .select('campaign_id, adset_id, ad_id, form_id, typeform_id, source_kind, funnel_label')
        .gte('anchor', range.startUtcIso)
        .lt('anchor', range.endUtcIso)
        .limit(20000),
      sb.from('meta_lead_forms' as never).select('form_id, name'),
      sb.from('typeform_forms' as never).select('form_id, title'),
    ])
  if (error) throw new Error(`dc_ads_lead_facts hierarchy read failed: ${error.message}`)
  if (fErr) throw new Error(`meta_lead_forms registry read failed: ${fErr.message}`)
  if (tErr) throw new Error(`typeform_forms registry read failed: ${tErr.message}`)
  const formNames = new Map(
    ((formRows ?? []) as Array<{ form_id: string; name: string | null }>).map((r) => [r.form_id, r.name]),
  )
  const typeformNames = new Map(
    ((tfRows ?? []) as Array<{ form_id: string; title: string | null }>).map((r) => [r.form_id, r.title]),
  )
  type Row = {
    campaign_id: string | null
    adset_id: string | null
    ad_id: string | null
    form_id: string | null
    typeform_id: string | null
    source_kind: string | null
    funnel_label: string | null
  }
  const factRows = ((data ?? []) as Row[]).filter((r) => r.ad_id)
  const [campaignNames, adsetNames, adNames] = await Promise.all([
    entityNames(
      sb,
      'cortana_campaign_daily',
      Array.from(new Set(factRows.map((r) => r.campaign_id).filter(Boolean) as string[])),
    ),
    entityNames(
      sb,
      'cortana_adset_daily',
      Array.from(new Set(factRows.map((r) => r.adset_id).filter(Boolean) as string[])),
    ),
    entityNames(
      sb,
      'cortana_ad_daily',
      Array.from(new Set(factRows.map((r) => r.ad_id).filter(Boolean) as string[])),
    ),
  ])
  type AdsetAgg = { adsetName?: string; count: number; ads: Map<string, { adName: string; count: number }> }
  const camps = new Map<string, { campaignName: string; count: number; adsets: Map<string, AdsetAgg> }>()
  const adsetsAll = new Map<string, AdsetAgg>()
  const adsAll = new Map<string, { adName: string; count: number }>()
  const formsAgg = new Map<string, number>()
  const typeformsAgg = new Map<string, number>()
  const funnelsAgg = new Map<string, { sourceKind: string | null; count: number }>()
  const bump = (m: Map<string, AdsetAgg>, r: Row) => {
    const key = r.adset_id ?? '—'
    const a = m.get(key) ?? {
      adsetName: (r.adset_id ? adsetNames.get(r.adset_id) : undefined) ?? undefined,
      count: 0,
      ads: new Map(),
    }
    a.count += 1
    const adId = r.ad_id as string
    const ad = a.ads.get(adId) ?? { adName: adNames.get(adId) ?? adId, count: 0 }
    ad.count += 1
    a.ads.set(adId, ad)
    m.set(key, a)
  }
  for (const r of factRows) {
    const cId = r.campaign_id ?? '—'
    const c = camps.get(cId) ?? {
      campaignName: (r.campaign_id ? campaignNames.get(r.campaign_id) : undefined) ?? cId,
      count: 0,
      adsets: new Map(),
    }
    c.count += 1
    bump(c.adsets, r)
    camps.set(cId, c)
    bump(adsetsAll, r)
    const adId = r.ad_id as string
    const g = adsAll.get(adId) ?? { adName: adNames.get(adId) ?? adId, count: 0 }
    g.count += 1
    adsAll.set(adId, g)
    if (r.form_id) formsAgg.set(r.form_id, (formsAgg.get(r.form_id) ?? 0) + 1)
    if (r.typeform_id) typeformsAgg.set(r.typeform_id, (typeformsAgg.get(r.typeform_id) ?? 0) + 1)
    if (r.funnel_label) {
      const f = funnelsAgg.get(r.funnel_label) ?? { sourceKind: r.source_kind, count: 0 }
      f.count += 1
      funnelsAgg.set(r.funnel_label, f)
    }
  }
  const adNodes = (ads: Map<string, { adName: string; count: number }>): DcAdNode[] => {
    const list = Array.from(ads.entries()).map(([adId, v]) => ({ adId, adName: v.adName, count: v.count }))
    // Meta reuses creative names — disambiguate duplicates with an id suffix.
    const names = new Map<string, number>()
    for (const a of list) names.set(a.adName, (names.get(a.adName) ?? 0) + 1)
    return list
      .map((a) => ((names.get(a.adName) ?? 0) > 1 ? { ...a, adName: `${a.adName} · …${a.adId.slice(-4)}` } : a))
      .sort((x, y) => y.count - x.count)
  }
  const adsetNodes = (m: Map<string, AdsetAgg>): DcAdsetNode[] =>
    Array.from(m.entries())
      .map(([adsetId, v]) => ({ adsetId, adsetName: v.adsetName, count: v.count, ads: adNodes(v.ads) }))
      .sort((x, y) => y.count - x.count)
  return {
    campaigns: Array.from(camps.entries())
      .map(([campaignId, v]) => ({ campaignId, campaignName: v.campaignName, count: v.count, adsets: adsetNodes(v.adsets) }))
      .sort((x, y) => y.count - x.count),
    adsetsAll: adsetNodes(adsetsAll),
    adsAll: adNodes(adsAll),
    forms: Array.from(formsAgg.entries())
      .map(([formId, count]) => ({ formId, formName: formNames.get(formId) ?? formId, count }))
      .sort((x, y) => y.count - x.count),
    typeforms: Array.from(typeformsAgg.entries())
      .map(([formId, count]) => ({ formId, formName: typeformNames.get(formId) ?? formId, count }))
      .sort((x, y) => y.count - x.count),
    funnels: Array.from(funnelsAgg.entries())
      .map(([label, v]) => ({ label, sourceKind: v.sourceKind, count: v.count }))
      .sort((x, y) => y.count - x.count),
  }
}

// The speed-to-lead boxes (ported from /sales-dashboard/leads), computed over
// the DC ads opt-in cohort only. The RPC hands back per-lead timing/effort
// facts; the business-hours speed clock (10a–10p ET) runs here with the SAME
// helper + summarize math the Leads page uses, so the two pages can't drift.
export type DcAdsSpeedStats = CohortStats & {
  // The funnel's broad Connected (≥90s call OR a later stage) — lead-level.
  connectedBroad: number
  // Denominator for the true connection rate: leads we actually WORKED
  // (dialed or reached), so never-touched leads don't dilute it — same rule
  // as the Leads page (Drake 2026-06-18).
  dialedOrConnected: number
}

export async function getDcAdsSpeedCohort(
  range: { startUtcIso: string; endUtcIso: string },
  filter?: DcAdsEntityFilter,
): Promise<DcAdsSpeedStats> {
  const sb = createAdminClient()
  const { data, error } = await sb.rpc('dc_ads_speed_cohort' as never, {
    p_start: range.startUtcIso,
    p_end: range.endUtcIso,
    ...entityArgs(filter),
  } as never)
  if (error) throw new Error(`dc_ads_speed_cohort RPC failed: ${error.message}`)
  const rows = (data ?? []) as unknown as Array<{
    anchor: string
    firstDial: string | null
    dials: number
    connected: boolean
  }>
  const stats = summarizeCohortRows(
    rows.map((r) => ({
      speedSec: r.firstDial
        ? businessHoursElapsedSec(new Date(r.anchor), new Date(r.firstDial))
        : null,
      firstCallAt: r.firstDial,
      anyCallConnected: r.connected,
      intensity: r.dials,
    })),
  )
  return {
    ...stats,
    connectedBroad: rows.filter((r) => r.connected).length,
    dialedOrConnected: rows.filter((r) => r.firstDial != null || r.connected).length,
  }
}

// Close-side opt-ins on the INSTANT-FORM path only, for the bridge-drift check.
// Since 0130 the funnel's optIns spans both paths, so comparing the Meta-side
// count (instant form by definition — landing-page leads never submit a Meta
// form) against the whole funnel would report a permanent phantom gap.
export async function getDcAdsInstantFormOptIns(range: {
  startUtcIso: string
  endUtcIso: string
}): Promise<number> {
  const sb = createAdminClient()
  const { count, error } = await sb
    .from('dc_ads_lead_facts' as never)
    .select('close_id', { count: 'exact', head: true })
    .eq('source_kind', 'instant_form')
    .gte('anchor', range.startUtcIso)
    .lt('anchor', range.endUtcIso)
  if (error) throw new Error(`dc_ads_lead_facts instant-form count failed: ${error.message}`)
  return count ?? 0
}

// Meta-side opt-in count in the window (ad-attributed submissions in
// meta_form_leads). Compared against the INSTANT-FORM Close-side optIns on the
// page: a growing gap = the Meta→Close bridge is dropping leads.
export async function getDcAdsMetaOptIns(range: {
  startUtcIso: string
  endUtcIso: string
}): Promise<number> {
  const sb = createAdminClient()
  const { count, error } = await sb
    .from('meta_form_leads' as never)
    .select('lead_id', { count: 'exact', head: true })
    .eq('is_organic', false)
    .gte('created_time', range.startUtcIso)
    .lt('created_time', range.endUtcIso)
  if (error) throw new Error(`meta_form_leads count failed: ${error.message}`)
  return count ?? 0
}
