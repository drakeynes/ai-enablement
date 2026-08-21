// Shared (server + client) access-tier types + pure helpers.
//
// The companion module `lib/auth/access-tier.ts` is marked
// `'server-only'` because it imports the service-role Supabase admin
// client. Client Components (e.g. `components/top-nav.tsx`) need the
// AccessTier type + `tierAtLeast` helper for conditional rendering but
// can't import the server-only module without breaking the build.
// Splitting the pure utilities here lets both sides reach for the same
// vocabulary.

export type AccessTier = 'csm' | 'head_csm' | 'admin' | 'creator'

// Ordered tier ranks. creator outranks admin outranks head_csm
// outranks csm. New tiers slot in here; migration 0032's CHECK
// constraint must move in lockstep.
const TIER_ORDER: Record<AccessTier, number> = {
  csm: 0,
  head_csm: 1,
  admin: 2,
  creator: 3,
}

export function tierAtLeast(actual: AccessTier, required: AccessTier): boolean {
  return TIER_ORDER[actual] >= TIER_ORDER[required]
}

// Department/area access — orthogonal to tier (migration 0112). Tier gates
// seniority WITHIN an area (admin → cost-hub/CEO, head_csm → /teams); areas gate
// WHICH departments a person sees. A person can hold one or both.
export type Area = 'fulfillment' | 'sales'

export function hasArea(areas: readonly string[] | null | undefined, area: Area): boolean {
  return !!areas && areas.includes(area)
}

// Where to send a user who lacks access to the page they hit — their own home.
// Sales-area users land on DC Ads (the dashboard's sales side is DC-only,
// middleware.ts). Fulfillment-area users land on /clients — the Fulfillment
// section was restored 2026-08-21 (middleware.ts allowlists it), so this no
// longer loops. Only users with NO area at all get the terminal /no-access
// page. Sales is checked first so dual-area users keep DC Ads as home.
export function homePathForAreas(areas: readonly string[] | null | undefined): string {
  if (hasArea(areas, 'sales')) return '/sales-dashboard/dc-ads'
  if (hasArea(areas, 'fulfillment')) return '/clients'
  return '/no-access'
}
