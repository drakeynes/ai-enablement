import 'server-only'

import { createAdminClient } from '@/lib/supabase/admin'
import { getRepCandidates, getCloseUsersForPicker } from './sales-rep-verify'
import type { RepCandidate, CloseUserOption } from './sales-rep-verify-shared'

// DC Setup admin page (/sales-dashboard/dc-setup) data layer — server-only.
// One page, three registries, so Zain/Aman can run the DC Ads operation with
// zero code involvement (Drake 2026-08-13):
//   Team          team_members sales rows + the Verify-Reps candidate queue
//                 (reusing the /sales-dashboard/reps machinery, migration 0109)
//   Landing pages dc_landing_pages (0132) — labels, URLs, typeform, videos,
//                 qualify rule
//   Campaigns     dc_ads_campaigns (0130) — active + landing-page link
// See docs/runbooks/dc_setup_admin.md (the plain-English operator guide).

export type { RepCandidate, CloseUserOption }

// A candidate enriched with a SUGGESTED Close user — matched by first name
// against the close_users mirror (the Airtable roster uses first names, Close
// uses full names: 'Flo' → 'Flora Phung'). A suggestion is exactly that: the
// picker pre-selects it and the human confirms. Ambiguous first names (two
// Close users both named Zach) suggest nothing.
export type DcRepCandidate = RepCandidate & {
  suggestedCloseUserId: string | null
  suggestedCloseName: string | null
}

function firstNameKey(name: string | null): string | null {
  const first = (name ?? '').trim().split(/\s+/)[0]?.toLowerCase()
  // Strip invisible separators Airtable names sometimes carry (e.g. U+2060) —
  // keep plain letters/digits only (ASCII-safe for the tsconfig target).
  const cleaned = first?.replace(/[^a-z0-9]/g, '')
  return cleaned && cleaned.length >= 2 ? cleaned : null
}

export async function getDcRepCandidates(): Promise<{
  candidates: DcRepCandidate[]
  closeUsers: CloseUserOption[]
}> {
  const [candidates, closeUsers] = await Promise.all([
    getRepCandidates(),
    getCloseUsersForPicker(),
  ])

  // first name → close users carrying it (only unambiguous matches suggest).
  const byFirst = new Map<string, CloseUserOption[]>()
  for (const u of closeUsers) {
    const key = firstNameKey(u.fullName)
    if (!key) continue
    byFirst.set(key, [...(byFirst.get(key) ?? []), u])
  }

  return {
    closeUsers,
    candidates: candidates.map((c) => {
      const key = firstNameKey(c.fullName)
      const matches = key ? (byFirst.get(key) ?? []) : []
      const suggestion = !c.draft?.closeUserId && matches.length === 1 ? matches[0] : null
      return {
        ...c,
        suggestedCloseUserId: suggestion?.closeUserId ?? null,
        suggestedCloseName: suggestion?.fullName ?? null,
      }
    }),
  }
}

// Dismissed candidates — the accidental-dismiss safety net (Drake
// 2026-08-13): a collapsed list in the Team section with a Restore button.
// No auto-expiry; dismissals are rare and the list stays small.
export type DismissedCandidate = {
  airtableRecordId: string
  fullName: string | null
  dismissedAt: string | null
}

export async function getDismissedCandidates(): Promise<DismissedCandidate[]> {
  const admin = createAdminClient()
  const [{ data: vers }, { data: cands }, { data: tms }] = await Promise.all([
    admin
      .from('sales_rep_verifications' as never)
      .select('airtable_record_id, status, updated_at')
      .eq('status', 'deleted'),
    admin.from('sales_rep_candidates' as never).select('airtable_record_id, full_name'),
    admin
      .from('team_members' as never)
      .select('airtable_user_id')
      .not('airtable_user_id', 'is', null)
      .is('archived_at', null),
  ])
  const nameByRecord = new Map(
    ((cands ?? []) as Array<Record<string, unknown>>).map((c) => [
      c.airtable_record_id as string,
      (c.full_name as string) ?? null,
    ]),
  )
  const mapped = new Set(
    ((tms ?? []) as Array<Record<string, unknown>>).map((t) => t.airtable_user_id as string),
  )
  return ((vers ?? []) as Array<Record<string, unknown>>)
    .filter((v) => !mapped.has(v.airtable_record_id as string))
    .map((v) => ({
      airtableRecordId: v.airtable_record_id as string,
      fullName: nameByRecord.get(v.airtable_record_id as string) ?? null,
      dismissedAt: (v.updated_at as string) ?? null,
    }))
    .sort((a, b) => (b.dismissedAt ?? '').localeCompare(a.dismissedAt ?? ''))
}

// A current team member as the Team section edits it. Only sales rows —
// engineering / CSM / leadership rows are invisible here on purpose.
export type DcTeamMember = {
  id: string
  fullName: string
  email: string | null
  salesRole: string | null
  closeUserId: string | null
  closeUserName: string | null
  airtableUserId: string | null
  calendlyEventTypeUri: string | null
  isActive: boolean
}

export async function getDcTeam(): Promise<DcTeamMember[]> {
  const admin = createAdminClient()
  const [{ data, error }, closeUsers] = await Promise.all([
    admin
      .from('team_members' as never)
      .select(
        'id, full_name, email, sales_role, close_user_id, airtable_user_id, calendly_event_type_uri, is_active',
      )
      .eq('role', 'sales')
      .is('archived_at', null)
      .order('is_active', { ascending: false })
      .order('full_name', { ascending: true }),
    getCloseUsersForPicker(),
  ])
  if (error) throw new Error(`team_members read failed: ${error.message}`)
  const closeNames = new Map(closeUsers.map((u) => [u.closeUserId, u.fullName]))
  return ((data ?? []) as Array<Record<string, unknown>>).map((r) => ({
    id: r.id as string,
    fullName: (r.full_name as string) ?? '',
    email: (r.email as string) ?? null,
    salesRole: (r.sales_role as string) ?? null,
    closeUserId: (r.close_user_id as string) ?? null,
    closeUserName: r.close_user_id ? (closeNames.get(r.close_user_id as string) ?? null) : null,
    airtableUserId: (r.airtable_user_id as string) ?? null,
    calendlyEventTypeUri: (r.calendly_event_type_uri as string) ?? null,
    isActive: r.is_active === true,
  }))
}

// People seen DIALING DC ad leads who have no team_members row — the "someone
// new is on the phones" radar. Read-only: the fix is adding them to the
// Airtable Sales Team Member table (→ the verify queue above), never a direct
// insert from here.
export type UnmappedDcCaller = { closeUserId: string; name: string; dials: number }

export async function getUnmappedDcCallers(): Promise<UnmappedDcCaller[]> {
  const admin = createAdminClient()
  const { data, error } = await admin.rpc('dc_ads_unmapped_callers' as never, {} as never)
  if (error) throw new Error(`dc_ads_unmapped_callers RPC failed: ${error.message}`)
  return (data ?? []) as unknown as UnmappedDcCaller[]
}

// ------------------------------------------------------------ system health --

// The SYSTEM HEALTH panel at the bottom of DC Setup (boss 2026-08-14): per
// data source feeding the DC Ads page, when it last succeeded — read from the
// webhook_deliveries audit trail via dc_setup_system_health() (0139).
// staleAfterMin is ~4× each source's cadence, so a hiccup doesn't false-alarm
// but a real outage shows within the hour.
export type DcHealthRow = {
  key: string
  label: string
  detail: string
  lastOkIso: string | null
  status: 'ok' | 'stale' | 'down'
}

const HEALTH_SOURCES: { key: string; label: string; detail: string; staleAfterMin: number }[] = [
  { key: 'meta_leads_sync', label: 'Meta Ads', detail: 'leads + campaign detection', staleAfterMin: 60 },
  { key: 'meta_sync', label: 'Meta Ads spend', detail: 'adspend mirrors', staleAfterMin: 240 },
  { key: 'close_webhook', label: 'Close CRM', detail: 'leads · calls · SMS', staleAfterMin: 360 },
  { key: 'typeform_sync_cron', label: 'Typeform', detail: 'form submissions', staleAfterMin: 60 },
  { key: 'airtable_sync_cron', label: 'Airtable', detail: 'sale forms · closer reports', staleAfterMin: 60 },
  { key: 'wistia_sync', label: 'Wistia', detail: 'video stats', staleAfterMin: 720 },
  { key: 'outbound_facts_refresh', label: 'Dashboard numbers', detail: 'DC Ads page refresh', staleAfterMin: 60 },
]

export async function getDcSystemHealth(): Promise<DcHealthRow[]> {
  const admin = createAdminClient()
  const { data, error } = await admin.rpc('dc_setup_system_health' as never, {} as never)
  if (error) throw new Error(`dc_setup_system_health RPC failed: ${error.message}`)
  const lastBySource = (data ?? {}) as Record<string, string>
  const now = Date.now()
  return HEALTH_SOURCES.map((s) => {
    const lastOkIso = lastBySource[s.key] ?? null
    let status: DcHealthRow['status'] = 'down'
    if (lastOkIso) {
      const ageMin = (now - new Date(lastOkIso).getTime()) / 60_000
      status = ageMin <= s.staleAfterMin ? 'ok' : 'stale'
    }
    return { key: s.key, label: s.label, detail: s.detail, lastOkIso, status }
  })
}

// ---------------------------------------------------------------- registries --

export type AdminDcLandingPage = {
  slug: string
  label: string
  lpUrl: string
  pageUrls: string[]
  typeformId: string | null
  vsl: { hashedId: string; label: string }[]
  confirmVideoHashedId: string | null
  confirmVideoLabel: string | null
  qualifyFieldRef: string | null
  qualifyAnswers: string[]
  active: boolean
  autoCreated: boolean
  sortOrder: number
}

export async function getAllDcLandingPagesAdmin(): Promise<AdminDcLandingPage[]> {
  const admin = createAdminClient()
  const { data, error } = await admin
    .from('dc_landing_pages' as never)
    .select(
      'slug, label, lp_url, page_urls, typeform_id, vsl, confirm_video_hashed_id, confirm_video_label, qualify_field_ref, qualify_answers, active, auto_created, sort_order',
    )
    .order('sort_order', { ascending: true })
  if (error) throw new Error(`dc_landing_pages read failed: ${error.message}`)
  return ((data ?? []) as Array<Record<string, unknown>>).map((r) => ({
    slug: r.slug as string,
    label: (r.label as string) ?? '',
    lpUrl: (r.lp_url as string) ?? '',
    pageUrls: (r.page_urls as string[]) ?? [],
    typeformId: (r.typeform_id as string) ?? null,
    vsl: ((r.vsl as Array<Record<string, unknown>>) ?? [])
      .map((v) => ({ hashedId: (v.hashedId as string) ?? '', label: (v.label as string) ?? 'Video' }))
      .filter((v) => v.hashedId),
    confirmVideoHashedId: (r.confirm_video_hashed_id as string) ?? null,
    confirmVideoLabel: (r.confirm_video_label as string) ?? null,
    qualifyFieldRef: (r.qualify_field_ref as string) ?? null,
    qualifyAnswers: (r.qualify_answers as string[]) ?? [],
    active: r.active === true,
    autoCreated: r.auto_created === true,
    sortOrder: (r.sort_order as number) ?? 100,
  }))
}

export type AdminDcCampaign = {
  campaignId: string
  campaignName: string
  sourceKind: string
  // Every landing page the campaign drives to (0138) — several when
  // split-testing. lpSlug (the primary) = lpSlugs[0].
  lpSlugs: string[]
  funnelLabel: string | null
  destinationUrl: string | null
  active: boolean
  lastSeenAt: string | null
}

export async function getAllDcCampaignsAdmin(): Promise<AdminDcCampaign[]> {
  const admin = createAdminClient()
  const { data, error } = await admin
    .from('dc_ads_campaigns' as never)
    .select(
      'campaign_id, campaign_name, source_kind, lp_slug, lp_slugs, funnel_label, destination_url, active, last_seen_at',
    )
    .order('last_seen_at', { ascending: false })
  if (error) throw new Error(`dc_ads_campaigns read failed: ${error.message}`)
  return ((data ?? []) as Array<Record<string, unknown>>).map((r) => {
    const slugs = (r.lp_slugs as string[]) ?? []
    const primary = (r.lp_slug as string) ?? null
    return {
      campaignId: r.campaign_id as string,
      campaignName: (r.campaign_name as string) ?? (r.campaign_id as string),
      sourceKind: (r.source_kind as string) ?? 'landing_page',
      lpSlugs: slugs.length ? slugs : primary ? [primary] : [],
      funnelLabel: (r.funnel_label as string) ?? null,
      destinationUrl: (r.destination_url as string) ?? null,
      active: r.active === true,
      lastSeenAt: (r.last_seen_at as string) ?? null,
    }
  })
}
