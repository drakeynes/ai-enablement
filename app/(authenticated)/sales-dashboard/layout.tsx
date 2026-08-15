import { redirect } from 'next/navigation'
import { getCurrentUserAccessTier, hasArea, tierAtLeast } from '@/lib/auth/access-tier'
import { homePathForAreas } from '@/lib/auth/access-tier-shared'
import { SalesSidebar } from './sidebar'

// Sales-AREA gate + two-column shell for /sales-dashboard/* (migration 0112).
// Was an admin-TIER gate — which meant sales reps (csm tier) couldn't see their
// own dashboard. Now gated on the 'sales' department instead, so any tier with
// the sales area gets in; non-sales users are sent to their own home.
// Preview-mode bypass passes through.
//
// v2 adds a sales-only left sidebar at 240px + flexible main. The
// sidebar lives ONLY under this segment layout — the global TopNav
// (in app/(authenticated)/layout.tsx) is untouched, and other pages
// (/clients, /calls, /cost-hub, etc.) see no sidebar.
//
// The States reference link surfaces in the sidebar only when the
// states route exists. Toggled via the includeStatesLink prop so the
// sidebar component stays decoupled from route discovery.
//
// Spec: docs/specs/sales-dashboard-v2.md § Sidebar.
const INCLUDE_STATES_LINK = true

export default async function SalesDashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const preview = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true'
  let isAdmin = true // preview defaults to creator → admin tools visible
  if (!preview) {
    const access = await getCurrentUserAccessTier()
    if (!access) {
      redirect('/login?error=no_team_member_row')
    }
    if (!hasArea(access.areas, 'sales')) {
      redirect(homePathForAreas(access.areas))
    }
    // Admin tools inside Sales (Verify Reps, Landing Pages) stay admin-tier —
    // sales reps (csm + sales area) see the data pages, not the admin tools.
    isAdmin = tierAtLeast(access.tier, 'admin')
  }

  return (
    // Mobile (boss batch 2026-08-15): single column, the 240px sidebar
    // collapses to a slim horizontal strip — the phone keeps the full width
    // for the data. Desktop unchanged.
    <div
      className="grid grid-cols-1 md:grid-cols-[240px_1fr]"
      style={{ minHeight: 'calc(100vh - 64px)' }}
    >
      <div className="hidden md:block">
        <SalesSidebar includeStatesLink={INCLUDE_STATES_LINK} isAdmin={isAdmin} />
      </div>
      <div
        className="md:hidden flex items-center gap-1 px-3"
        style={{
          background: 'var(--color-geg-bg-elev)',
          borderBottom: '1px solid var(--color-geg-border)',
        }}
      >
        <MobileNavLink href="/sales-dashboard/dc-ads" label="DC Ads" />
        {isAdmin ? <MobileNavLink href="/sales-dashboard/dc-setup" label="DC Setup" /> : null}
      </div>
      {/* `<div>` not `<main>` — the parent (authenticated)/layout.tsx
          already wraps every authenticated route in a `<main>` for
          a11y. Nesting another `<main>` here would violate the
          one-main-per-document landmark rule and trip Playwright's
          strict-mode role queries. */}
      <div
        className="px-4 pt-5 pb-16 md:px-14 md:pt-9 md:pb-24"
        style={{
          maxWidth: 1480,
          width: '100%',
          // CSS grid + 1fr: without min-width:0 the child column won't
          // shrink below its content's intrinsic min-content size,
          // which causes the whole page to overflow when a child block
          // has wide internal min-content (the funnel chevron stack
          // was the trigger).
          minWidth: 0,
        }}
      >
        {children}
      </div>
    </div>
  )
}

// The phone-width nav: just the DC-era pages, as quiet text links.
function MobileNavLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="geg-mono"
      style={{
        padding: '10px 12px',
        fontSize: 10.5,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--color-geg-text-2)',
      }}
    >
      {label}
    </a>
  )
}
