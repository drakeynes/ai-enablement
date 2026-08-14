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
  // The stage row (0133) — NOT monotonic; stages overlap rather than nest.
  qualified: number // lead's own Typeform hit the LP's qualify answer
  sms: number // inbound SMS after the opt-in (has_inbound)
  smsMql: number // qualified AND texted back
  hvc: number // "high-value connect": smsMql OR connected
  units: number // DC plan units closed (cash = units × $300)
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
  // The Valid QA audit line (0141): submissions the team marked invalid in
  // Airtable, and closed-form units the verdicts excluded — the receipt that
  // closes/units/cash are QA-adjusted.
  qaInvalidForms: number
  qaExcludedUnits: number
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
  // team_members.id when the rep's identity is linked (0136); null = the raw
  // Close-name or form-name fallback — a "not linked" row until the person is
  // verified in DC Setup.
  teamMemberId: string | null
  dials: number
  connections: number
  shows: number
  closes: number
  units: number
  base44Monthly: number
  base44Yearly: number
  wixMonthly: number
  wixYearly: number
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
// deepest id, mirroring the Advertising Hub. The landing page (lpSlug,
// matching dc_ads_lead_facts.lp_slug — a dc_landing_pages slug, or the
// 'instant-form' pseudo-slug for the legacy no-LP path; 0132) is an
// independent AND facet (a page spans many ads), so it composes with the
// cascade instead of competing. formId (the Meta instant form, 0128) stays
// supported at this layer — the forms dropdown left the page's filter row
// but the facet is planned to resurface in its own forms section.
export type DcAdsEntityFilter = {
  campaignId?: string | null
  adsetId?: string | null
  adId?: string | null
  formId?: string | null
  lpSlug?: string | null
}

// The facts pseudo-slug for instant-form leads (no landing page) — kept in
// sync with refresh_dc_ads_facts() (0132).
export const INSTANT_FORM_SLUG = 'instant-form'

function entityArgs(filter?: DcAdsEntityFilter): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  if (filter?.adId) args.p_ad_id = filter.adId
  else if (filter?.adsetId) args.p_adset_id = filter.adsetId
  else if (filter?.campaignId) args.p_campaign_id = filter.campaignId
  if (filter?.formId) args.p_form_id = filter.formId
  if (filter?.lpSlug) args.p_lp_slug = filter.lpSlug
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
// registry campaigns driving to that page (lp_slug; the 'instant-form'
// pseudo-slug maps to the instant-form campaigns). When a cascade entity is
// selected alongside either facet, the entity wins the spend read while the
// funnel ANDs everything. No selection → cortana_campaign_daily over the
// whole dc_ads_campaigns registry.
export async function spendScope(
  filter?: DcAdsEntityFilter,
): Promise<{ table: string; ids: string[]; campaigns: number }> {
  const sb = createAdminClient()
  const { data: camps, error } = await sb
    .from('dc_ads_campaigns' as never)
    .select('campaign_id, lp_slug, lp_slugs, source_kind')
    .eq('active', true)
  if (error) throw new Error(`dc_ads_campaigns read failed: ${error.message}`)
  const rows = (camps ?? []) as Array<{
    campaign_id: string
    lp_slug: string | null
    lp_slugs: string[] | null
    source_kind: string
  }>
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
  if (filter?.lpSlug) {
    const slug = filter.lpSlug
    // A split-test campaign (several lp_slugs, 0138) counts toward EACH of its
    // pages' spend — Meta can't split one campaign's spend per destination.
    const ids = rows
      .filter((c) =>
        slug === INSTANT_FORM_SLUG
          ? c.source_kind === 'instant_form'
          : (c.lp_slugs?.length ? c.lp_slugs.includes(slug) : c.lp_slug === slug),
      )
      .map((c) => c.campaign_id)
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

// The rolling daily cohort table (last 30 days on the page since 0134):
// per-ET-day rows, newest first — the DC sibling of the hub's
// getDailyFunnelTable. Spend + opt-ins freeze once the day ends; every other
// column is the cohort's LIFETIME progression, so a day's SMS / Connects /
// Units keep climbing on later visits. Pinned to the rolling window
// regardless of the date picker; scoped to the cascade + LP selection.
export type DcAdsDailyRow = {
  etDate: string
  spendUsd: number | null
  optIns: number
  qualified: number
  sms: number
  smsMql: number
  hvc: number
  units: number
  // Speed-to-unit (0142): valid-adjusted units closed within 0 / <3 / <7 ET
  // calendar days of the opt-in — cumulative (d0 ⊆ d3 ⊆ d7 ⊆ units). The dN
  // ROAS columns derive in the table (units × $300 ÷ the day's spend).
  unitsD0: number
  unitsD3: number
  unitsD7: number
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
// The funnel read-out (0130): which acquisition path an opt-in came through —
// 'Digital College' (instant form) vs 'Aman Funnel' / 'Luke Funnel' (the
// landing-page + Typeform motions). Labels are the Close funnel_name.
export type DcFunnelOption = { label: string; sourceKind: string | null; count: number }
// The landing-page dropdown options (0132): dc_landing_pages registry rows
// (URL-derived labels — 'join/training', 'go') plus the instant-form
// pseudo-entry for the legacy no-LP path. Counts are window opt-ins.
export type DcLandingPageOption = { slug: string; label: string; count: number }
export type DcAdHierarchy = {
  campaigns: DcCampaignNode[]
  adsetsAll: DcAdsetNode[]
  adsAll: DcAdNode[]
  forms: DcFormOption[]
  typeforms: DcFormOption[]
  funnels: DcFunnelOption[]
  landingPages: DcLandingPageOption[]
  // campaign_id → the landing pages it drives to (dc_ads_campaigns.lp_slugs,
  // 0138) — the page narrows the LP dropdown to the selected campaign's set.
  campaignLps: Record<string, string[]>
}

// Campaign names lead with a launch date ('07/25 | …', '08/12 | …'); parse it
// into a sortable key so the dropdown orders newest-first like the boss's Meta
// view (undated names sink to the bottom). Mirrors the Hub's leadingDateKey.
function leadingDateKey(name: string): number | null {
  const m = name.match(/^\s*(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?/)
  if (!m) return null
  const month = Number(m[1])
  const day = Number(m[2])
  let year = m[3] ? Number(m[3]) : 2026
  if (year < 100) year += 2000
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  return year * 10000 + month * 100 + day
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
  const [
    { data, error },
    { data: formRows, error: fErr },
    { data: tfRows, error: tErr },
    { data: lpRows, error: lErr },
    { data: campRows, error: cErr },
  ] = await Promise.all([
    sb
      .from('dc_ads_lead_facts' as never)
      .select('campaign_id, adset_id, ad_id, form_id, typeform_id, source_kind, funnel_label, lp_slug')
      .gte('anchor', range.startUtcIso)
      .lt('anchor', range.endUtcIso)
      .limit(20000),
    sb.from('meta_lead_forms' as never).select('form_id, name'),
    sb.from('typeform_forms' as never).select('form_id, title'),
    sb
      .from('dc_landing_pages' as never)
      .select('slug, label, sort_order')
      .eq('active', true)
      .order('sort_order', { ascending: true }),
    // The FULL registry — the campaign dropdown lists every registered
    // campaign (Drake's boss 2026-08-13: all six, like the Meta view), not
    // just the ones with opt-ins in the window.
    sb
      .from('dc_ads_campaigns' as never)
      .select('campaign_id, campaign_name, lp_slug, lp_slugs')
      .eq('active', true),
  ])
  if (error) throw new Error(`dc_ads_lead_facts hierarchy read failed: ${error.message}`)
  if (fErr) throw new Error(`meta_lead_forms registry read failed: ${fErr.message}`)
  if (tErr) throw new Error(`typeform_forms registry read failed: ${tErr.message}`)
  if (lErr) throw new Error(`dc_landing_pages registry read failed: ${lErr.message}`)
  if (cErr) throw new Error(`dc_ads_campaigns registry read failed: ${cErr.message}`)
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
    lp_slug: string | null
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
  }
  // Facet counts run over EVERY fact in the window (not just ad-attributed
  // rows) so they agree with the RPC-filtered funnel numbers.
  const lpAgg = new Map<string, number>()
  for (const r of (data ?? []) as Row[]) {
    if (r.form_id) formsAgg.set(r.form_id, (formsAgg.get(r.form_id) ?? 0) + 1)
    if (r.typeform_id) typeformsAgg.set(r.typeform_id, (typeformsAgg.get(r.typeform_id) ?? 0) + 1)
    if (r.funnel_label) {
      const f = funnelsAgg.get(r.funnel_label) ?? { sourceKind: r.source_kind, count: 0 }
      f.count += 1
      funnelsAgg.set(r.funnel_label, f)
    }
    if (r.lp_slug) lpAgg.set(r.lp_slug, (lpAgg.get(r.lp_slug) ?? 0) + 1)
  }
  // The campaign dropdown = the FULL registry, window counts where leads
  // exist and 0 where none (the CBO campaign that never ran still shows).
  // Registry names win over the spend-mirror lookup. Also collect each
  // campaign's landing pages (0138) — the LP dropdown corroborates with them.
  const campaignLps: Record<string, string[]> = {}
  const activeLpSlugs = new Set<string>()
  type CampRow = {
    campaign_id: string
    campaign_name: string | null
    lp_slug: string | null
    lp_slugs: string[] | null
  }
  for (const c of (campRows ?? []) as CampRow[]) {
    const existing = camps.get(c.campaign_id)
    if (existing) {
      if (c.campaign_name) existing.campaignName = c.campaign_name
    } else {
      camps.set(c.campaign_id, {
        campaignName: c.campaign_name ?? c.campaign_id,
        count: 0,
        adsets: new Map(),
      })
    }
    const slugs = c.lp_slugs?.length ? c.lp_slugs : c.lp_slug ? [c.lp_slug] : []
    campaignLps[c.campaign_id] = slugs
    for (const s of slugs) activeLpSlugs.add(s)
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
  // Landing-page options: CORROBORATED with the campaign registry (boss
  // 2026-08-14) — only pages an ACTIVE campaign drives to (plus any page that
  // still has window opt-ins, so real data never hides), in sort order.
  // 0-count linked pages show (a just-launched funnel is visible before its
  // first lead); an unlinked page disappears from the dropdown. Instant-form
  // pseudo-entry when the legacy path has window opt-ins.
  const landingPages: DcLandingPageOption[] = (
    (lpRows ?? []) as Array<{ slug: string; label: string }>
  )
    .filter((lp) => activeLpSlugs.has(lp.slug) || (lpAgg.get(lp.slug) ?? 0) > 0)
    .map((lp) => ({ slug: lp.slug, label: lp.label, count: lpAgg.get(lp.slug) ?? 0 }))
  const instantCount = lpAgg.get(INSTANT_FORM_SLUG) ?? 0
  if (instantCount > 0)
    landingPages.push({ slug: INSTANT_FORM_SLUG, label: 'Instant form (no LP)', count: instantCount })

  return {
    // Newest launch first (leading M/D in the name), matching the Meta
    // manager's default view; equal dates break by window volume.
    campaigns: Array.from(camps.entries())
      .map(([campaignId, v]) => ({ campaignId, campaignName: v.campaignName, count: v.count, adsets: adsetNodes(v.adsets) }))
      .sort((x, y) => {
        const dx = leadingDateKey(x.campaignName)
        const dy = leadingDateKey(y.campaignName)
        if (dx !== dy) {
          if (dx === null) return 1
          if (dy === null) return -1
          return dy - dx
        }
        return y.count - x.count
      }),
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
    landingPages,
    campaignLps,
  }
}

// The speed-to-lead boxes (ported from /sales-dashboard/leads), computed over
// the DC ads opt-in cohort only — with the SAME helper + summarize math the
// Leads page uses, but a DIFFERENT business-hours clock: the DC dial team
// works 12p–12a ET (boss 2026-08-13), so this page's speed counts noon→
// midnight, while the Leads page stays on 10a–10p. The clock is labeled on
// the box, so the two pages' numbers are visibly not comparable.

// The DC dial team's working window (ET hours; 24 = midnight — the DST switch
// at 2am can never fall inside noon→midnight, so the day-offset math holds).
const DC_CLOCK_OPEN_HOUR = 12
const DC_CLOCK_CLOSE_HOUR = 24
export const DC_CLOCK_LABEL = '12p–12a ET'

export type DcAdsSpeedStats = CohortStats & {
  // Lead-level Connected — a call ≥90s ONLY since 0140 (the name predates the
  // narrowing; kept to avoid touching every consumer).
  connectedBroad: number
  // Denominator for the true connection rate: leads we actually WORKED
  // (dialed or reached), so never-touched leads don't dilute it — same rule
  // as the Leads page (Drake 2026-06-18).
  dialedOrConnected: number
  // SMS engagement (0135): of the leads we TEXTED (any outbound SMS after the
  // opt-in), how many texted back. Texted, not cohort, as the denominator —
  // the same never-touched-leads-don't-dilute rule as the connected rate. A
  // lead who texted US first (inbound with no outbound) counts in BOTH the
  // numerator and the denominator, so the rate can't exceed 100% — same
  // guard as the connected rate's form-reached leads.
  smsEngaged: number
  smsTexted: number
  // Dial-speed spread (boss item #20), on the SAME 12p–12a business-hours
  // clock as the average. under-X counts are CUMULATIVE (under30 ⊇ under10 ⊇
  // under5); under30 + over30 + neverDialed = cohortSize, so the displayed
  // percentages sum to 100.
  dialedUnder5m: number
  dialedUnder10m: number
  dialedUnder30m: number
  dialedOver30m: number
  neverDialed: number
  // Median opt-in → first dial (business-hours seconds), among dialed leads.
  medianDialSec: number | null
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
    smsIn: boolean
    smsOut: boolean
  }>
  // Business-hours speed per lead, computed once — feeds both the summarize
  // math and the dial-speed spread.
  const speeds = rows.map((r) =>
    r.firstDial
      ? businessHoursElapsedSec(
          new Date(r.anchor),
          new Date(r.firstDial),
          DC_CLOCK_OPEN_HOUR,
          DC_CLOCK_CLOSE_HOUR,
        )
      : null,
  )
  const stats = summarizeCohortRows(
    rows.map((r, i) => ({
      speedSec: speeds[i],
      firstCallAt: r.firstDial,
      anyCallConnected: r.connected,
      intensity: r.dials,
    })),
  )
  const dialed = speeds.filter((s): s is number => s !== null).sort((a, b) => a - b)
  const under = (min: number) => dialed.filter((s) => s < min * 60).length
  const medianDialSec =
    dialed.length === 0
      ? null
      : dialed.length % 2
        ? dialed[(dialed.length - 1) / 2]
        : (dialed[dialed.length / 2 - 1] + dialed[dialed.length / 2]) / 2
  return {
    ...stats,
    connectedBroad: rows.filter((r) => r.connected).length,
    dialedOrConnected: rows.filter((r) => r.firstDial != null || r.connected).length,
    smsEngaged: rows.filter((r) => r.smsIn).length,
    smsTexted: rows.filter((r) => r.smsOut || r.smsIn).length,
    dialedUnder5m: under(5),
    dialedUnder10m: under(10),
    dialedUnder30m: under(30),
    dialedOver30m: dialed.length - under(30),
    neverDialed: rows.length - dialed.length,
    medianDialSec,
  }
}

// The embedded lead roster (0137) — the Leads page's list scoped to DC ad
// leads, filtered IN PLACE on the client (search + disposition toggles never
// navigate). Disposition precedence: Closed > HVC > Connected > SMS > Opt-in.
export type DcAdsLeadRow = {
  closeId: string
  name: string
  phone: string | null
  email: string | null
  anchor: string
  lpSlug: string | null
  dials: number
  sms: boolean
  qualified: boolean
  connected: boolean
  hvc: boolean
  closed: boolean
}

export async function getDcAdsLeadRoster(
  range: { startUtcIso: string; endUtcIso: string },
  filter?: DcAdsEntityFilter,
): Promise<DcAdsLeadRow[]> {
  const sb = createAdminClient()
  const { data, error } = await sb.rpc('dc_ads_lead_roster' as never, {
    p_start: range.startUtcIso,
    p_end: range.endUtcIso,
    ...entityArgs(filter),
  } as never)
  if (error) throw new Error(`dc_ads_lead_roster RPC failed: ${error.message}`)
  return (data ?? []) as unknown as DcAdsLeadRow[]
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
