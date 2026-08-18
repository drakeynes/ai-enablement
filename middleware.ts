import { NextResponse, type NextRequest } from 'next/server'

// DC-era route guard (2026-08-15): the dashboard is DC-only — every page
// except DC Ads + DC Setup is HIDDEN, not deleted. The nav twins live in
// components/top-nav.tsx and app/(authenticated)/sales-dashboard/sidebar.tsx
// (entries carry `hidden: true`); this file makes direct URLs match the nav.
// To bring the full dashboard back: delete this file and unhide the nav
// entries.
//
// No Supabase import on purpose — auth stays in the server layouts (the
// middleware auth gate was dropped because @supabase/ssr can't bundle for the
// Edge runtime; see app/(authenticated)/layout.tsx). This is pure path
// matching, which the Edge runtime handles fine.

const ALLOWED_PREFIXES = [
  '/sales-dashboard/dc-ads',
  '/sales-dashboard/dc-setup',
  // Deep-link targets for the DC Ads AI call-review layer (2026-08-18): the
  // per-lead lifecycle page and the per-call review page. Reachable by URL
  // (the DC pages link into them); their NAV entries stay hidden — this is
  // not the full-dashboard unhide.
  '/sales-dashboard/leads',
  '/sales-dashboard/calls',
  '/login',
  // Terminal page for authenticated users WITHOUT the sales area (CSMs) —
  // without it they'd loop: sales layout → home → guard → sales layout.
  '/no-access',
]

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl
  const allowed = ALLOWED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  )
  if (allowed) return NextResponse.next()
  return NextResponse.redirect(new URL('/sales-dashboard/dc-ads', req.url))
}

// Skip /api (Next route handlers AND the Python functions share the prefix),
// Next internals, and file-ish paths (favicon, static assets). Everything
// else — including / and every hidden page — goes through the guard.
export const config = {
  matcher: ['/((?!api/|_next/|.*\\..*).*)'],
}
