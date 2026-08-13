'use server'

// Admin actions for the DC Setup page (/sales-dashboard/dc-setup) — the one
// place Zain/Aman run the DC Ads operation without code (Drake 2026-08-13):
// Team (verify / edit / deactivate reps), Landing pages (dc_landing_pages,
// 0132) and Campaigns (dc_ads_campaigns, 0130). The whole segment is
// admin-gated by its layout; every action re-checks admin server-side.
//
// Team verify semantics are the /sales-dashboard/reps machinery reused
// verbatim (same tables, same completeRep write shape) so the two pages can't
// drift; this file adds the missing pieces for turnover — edit + deactivate.
// Registry edits only touch curated columns: the ingestion resolver
// (resolve_dc_landing_pages) fills nulls and never overwrites what a human
// saved here.

import { revalidatePath } from 'next/cache'

import { getCurrentUserAccessTier, tierAtLeast } from '@/lib/auth/access-tier'
import { createAdminClient } from '@/lib/supabase/admin'
import { getTypeformFields, type TypeformField } from '@/lib/db/landing-page-assets'
import { normalizeLpUrl, lpShortLabel, lpSlugify } from '@/lib/lp-urls'
import type { SalesRole } from '@/lib/db/sales-rep-verify'
import {
  saveRepDraft,
  completeRep,
  deleteRepCandidate,
  type RepDraftInput,
  type RepActionResult,
} from '../reps/actions'

const PATH = '/sales-dashboard/dc-setup'
// Every surface that reads these registries.
const CONSUMER_PATHS = ['/sales-dashboard/dc-ads', '/sales-dashboard/people', '/sales-dashboard/people/by-rep']

export type SimpleResult = { ok: true } | { ok: false; error: string }

function clean(v: string | null | undefined): string | null {
  if (typeof v !== 'string') return null
  const t = v.trim()
  return t.length ? t : null
}

async function requireAdmin() {
  const access = await getCurrentUserAccessTier()
  if (!access || !tierAtLeast(access.tier, 'admin')) return null
  return access
}

function revalidateAll() {
  revalidatePath(PATH)
  for (const p of CONSUMER_PATHS) revalidatePath(p)
}

// ---------------------------------------------------------------- team ------

// Verify-queue actions: delegate to the reps-page actions (one write path for
// team_members), then revalidate THIS page's consumers too.
export async function dcVerifyRep(input: RepDraftInput): Promise<RepActionResult> {
  const res = await completeRep(input)
  if (res.ok) revalidateAll()
  return res
}

export async function dcSaveRepDraft(input: RepDraftInput): Promise<RepActionResult> {
  const res = await saveRepDraft(input)
  if (res.ok) revalidatePath(PATH)
  return res
}

export async function dcDismissRepCandidate(recordId: string): Promise<RepActionResult> {
  const res = await deleteRepCandidate(recordId)
  if (res.ok) revalidatePath(PATH)
  return res
}

// Undo an accidental dismiss (Drake 2026-08-13): flip the verification back
// to 'draft' — the candidate reappears in the verify queue (any pre-dismiss
// draft fields survive, since dismissing only overwrote the status).
export async function dcRestoreRepCandidate(recordId: string): Promise<RepActionResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }
  const id = clean(recordId)
  if (!id) return { ok: false, error: 'invalid_record_id' }
  const admin = createAdminClient()
  const { error } = await admin
    .from('sales_rep_verifications' as never)
    .upsert(
      {
        airtable_record_id: id,
        status: 'draft',
        updated_by: access.team_member.email,
      } as never,
      { onConflict: 'airtable_record_id' } as never,
    )
  if (error) return { ok: false, error: error.message }
  revalidatePath(PATH)
  return { ok: true }
}

export type TeamMemberEditInput = {
  id: string
  fullName: string
  salesRole: SalesRole
  email: string
  closeUserId: string | null
  airtableUserId: string | null
  calendlyEventTypeUri: string | null
}

const VALID_ROLES: SalesRole[] = ['setter', 'closer', 'dc_closer']

// Edit an existing sales team member (name, role, identity links). Email is
// the auth join key and partial-unique among non-archived rows — a duplicate
// surfaces as a friendly error, never a half-write.
export async function updateTeamMember(input: TeamMemberEditInput): Promise<SimpleResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }

  const id = clean(input.id)
  const fullName = clean(input.fullName)
  const email = clean(input.email)
  if (!id) return { ok: false, error: 'invalid_id' }
  if (!fullName) return { ok: false, error: 'full_name_required' }
  if (!email) return { ok: false, error: 'email_required' }
  if (!VALID_ROLES.includes(input.salesRole)) return { ok: false, error: 'invalid_sales_role' }

  const admin = createAdminClient()
  const { error } = await admin
    .from('team_members' as never)
    .update({
      full_name: fullName,
      email,
      sales_role: input.salesRole,
      close_user_id: clean(input.closeUserId),
      airtable_user_id: clean(input.airtableUserId),
      calendly_event_type_uri: clean(input.calendlyEventTypeUri),
    } as never)
    .eq('id', id)
  if (error) {
    if (error.message.includes('duplicate') || error.message.includes('unique')) {
      return { ok: false, error: 'duplicate_identity' }
    }
    return { ok: false, error: error.message }
  }
  revalidateAll()
  return { ok: true }
}

// Deactivate / reactivate. Deactivation is the offboarding path — history
// stays attributed (the row keeps its identity links); the person just stops
// counting as active on rosters. Never a hard delete.
export async function setTeamMemberActive(id: string, active: boolean): Promise<SimpleResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }
  const cleanId = clean(id)
  if (!cleanId) return { ok: false, error: 'invalid_id' }
  const admin = createAdminClient()
  const { error } = await admin
    .from('team_members' as never)
    .update({ is_active: active } as never)
    .eq('id', cleanId)
  if (error) return { ok: false, error: error.message }
  revalidateAll()
  return { ok: true }
}

// -------------------------------------------------------- landing pages -----

export type DcLpInput = {
  slug?: string // present = edit; absent = create
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
}

export type DcLpSaveResult = { ok: true; slug: string } | { ok: false; error: string }

export async function saveDcLandingPage(input: DcLpInput): Promise<DcLpSaveResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }

  const label = clean(input.label)
  if (!label) return { ok: false, error: 'label_required' }
  const rawUrl = clean(input.lpUrl)
  if (!rawUrl) return { ok: false, error: 'url_required' }
  // Same normalization the ingestion resolver uses (lib/lp-urls.ts ↔
  // shared/lp_urls.py) — un-normalized URLs would fork LP identities.
  const lpUrl = normalizeLpUrl(rawUrl)

  const isEdit = !!clean(input.slug)
  const slug = clean(input.slug) ?? lpSlugify(lpShortLabel(lpUrl))
  if (!slug) return { ok: false, error: 'could_not_derive_slug' }

  const admin = createAdminClient()

  // Guard: the URL is the LP's identity — reject one already owned by a
  // different row.
  const { data: urlOwner } = await admin
    .from('dc_landing_pages' as never)
    .select('slug')
    .eq('lp_url', lpUrl)
    .maybeSingle()
  const ownerSlug = (urlOwner as Record<string, unknown> | null)?.slug as string | undefined
  if (ownerSlug && ownerSlug !== slug) {
    return { ok: false, error: `url_already_used_by:${ownerSlug}` }
  }

  let sortOrder: number | null = null
  if (!isEdit) {
    const { data: maxRow } = await admin
      .from('dc_landing_pages' as never)
      .select('sort_order')
      .order('sort_order', { ascending: false })
      .limit(1)
      .maybeSingle()
    sortOrder = (((maxRow as Record<string, unknown> | null)?.sort_order as number) ?? 0) + 10
  }

  const row: Record<string, unknown> = {
    slug,
    label,
    lp_url: lpUrl,
    page_urls: (input.pageUrls ?? []).map((u) => normalizeLpUrl(u)).filter(Boolean),
    typeform_id: clean(input.typeformId),
    vsl: (input.vsl ?? [])
      .map((v) => ({ hashedId: clean(v.hashedId), label: clean(v.label) ?? 'Video' }))
      .filter((v) => v.hashedId),
    confirm_video_hashed_id: clean(input.confirmVideoHashedId),
    confirm_video_label: clean(input.confirmVideoLabel),
    qualify_field_ref: clean(input.qualifyFieldRef),
    qualify_answers: (input.qualifyAnswers ?? []).map((a) => a.trim()).filter(Boolean),
    active: input.active !== false,
    // A human touched it — auto_created off so the row reads as curated.
    auto_created: false,
  }
  if (sortOrder !== null) row.sort_order = sortOrder

  const { error } = await admin
    .from('dc_landing_pages' as never)
    .upsert(row as never, { onConflict: 'slug' } as never)
  if (error) return { ok: false, error: error.message }

  revalidateAll()
  return { ok: true, slug }
}

// Hide from the DC Ads dropdown without losing history (facts keep the
// lp_slug; campaign links stay). There is deliberately NO delete — facts and
// campaigns reference the slug.
export async function setDcLandingPageActive(slug: string, active: boolean): Promise<SimpleResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }
  const s = clean(slug)
  if (!s) return { ok: false, error: 'invalid_slug' }
  const admin = createAdminClient()
  const { error } = await admin
    .from('dc_landing_pages' as never)
    .update({ active } as never)
    .eq('slug', s)
  if (error) return { ok: false, error: error.message }
  revalidateAll()
  return { ok: true }
}

// A form's questions + answer choices for the qualification picker.
export async function loadDcTypeformFields(formId: string): Promise<TypeformField[]> {
  const access = await requireAdmin()
  if (!access) return []
  return getTypeformFields(clean(formId) ?? '')
}

// ------------------------------------------------------------ campaigns -----

// Retire / restore a campaign on the DC Ads page. Inactive = its spend AND
// its leads leave every number on the page (facts membership requires
// active) — the off-switch for a campaign that never belonged.
export async function setDcCampaignActive(campaignId: string, active: boolean): Promise<SimpleResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }
  const id = clean(campaignId)
  if (!id) return { ok: false, error: 'invalid_campaign_id' }
  const admin = createAdminClient()
  const { error } = await admin
    .from('dc_ads_campaigns' as never)
    .update({ active } as never)
    .eq('campaign_id', id)
  if (error) return { ok: false, error: error.message }
  revalidateAll()
  return { ok: true }
}

// Point a campaign at a different landing page. Facts re-stamp on the next
// refresh tick (≤15 min); spend scoping follows immediately.
export async function setDcCampaignLp(campaignId: string, lpSlug: string | null): Promise<SimpleResult> {
  const access = await requireAdmin()
  if (!access) return { ok: false, error: 'forbidden' }
  const id = clean(campaignId)
  if (!id) return { ok: false, error: 'invalid_campaign_id' }
  const slug = clean(lpSlug)
  const admin = createAdminClient()
  if (slug) {
    const { data: lp } = await admin
      .from('dc_landing_pages' as never)
      .select('slug')
      .eq('slug', slug)
      .maybeSingle()
    if (!lp) return { ok: false, error: 'unknown_landing_page' }
  }
  const { error } = await admin
    .from('dc_ads_campaigns' as never)
    .update({ lp_slug: slug } as never)
    .eq('campaign_id', id)
  if (error) return { ok: false, error: error.message }
  revalidateAll()
  return { ok: true }
}
