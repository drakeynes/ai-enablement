import { redirect } from 'next/navigation'

import { HeaderBand } from '@/components/gregory/header-band'
import { getCurrentUserAccessTier, tierAtLeast } from '@/lib/auth/access-tier'
import {
  getDcRepCandidates,
  getDcTeam,
  getUnmappedDcCallers,
  getAllDcLandingPagesAdmin,
  getAllDcCampaignsAdmin,
} from '@/lib/db/dc-setup'
import { getWistiaInventory, getTypeformForms } from '@/lib/db/landing-page-assets'
import { TeamManager } from './_components/team-manager'
import { DcLpManager } from './_components/dc-lp-manager'
import { DcCampaignManager } from './_components/dc-campaign-manager'

// Sales Dashboard — DC Setup. ADMIN-only within Sales: the one page where
// Zain/Aman run the whole DC Ads operation without code (Drake 2026-08-13) —
// Team (who shows on the by-rep table + roster, verify new hires, offboard
// leavers), Landing pages (names / URLs / Typeforms / videos / qualification)
// and Campaigns (which campaigns count, which landing page each drives to).
// Everything else self-maintains: campaigns + landing pages auto-register
// from the ads, videos auto-attach from Wistia — this page is for naming,
// people, and corrections.
//
// Operator guide (the Loom script lives there too):
// docs/runbooks/dc_setup_admin.md.

export const dynamic = 'force-dynamic'
export const maxDuration = 60

export default async function DcSetupPage() {
  if (process.env.NEXT_PUBLIC_DISABLE_AUTH !== 'true') {
    const access = await getCurrentUserAccessTier()
    if (!access || !tierAtLeast(access.tier, 'admin')) redirect('/sales-dashboard')
  }

  const [{ candidates, closeUsers }, team, unmapped, pages, campaigns, wistia, typeforms] =
    await Promise.all([
      getDcRepCandidates(),
      getDcTeam(),
      getUnmappedDcCallers(),
      getAllDcLandingPagesAdmin(),
      getAllDcCampaignsAdmin(),
      getWistiaInventory(),
      getTypeformForms(),
    ])

  return (
    <div>
      <HeaderBand eyebrow="SALES · ADMIN" title="DC Setup." />
      <p
        style={{
          marginTop: 12,
          maxWidth: 760,
          fontSize: 13.5,
          lineHeight: 1.6,
          color: 'var(--color-geg-text-2)',
        }}
      >
        Everything the DC Ads page needs to stay accurate, in one place — no engineer required.
        People, landing pages, and campaigns mostly register themselves; this page is where you
        confirm new reps, offboard leavers, rename things, and fix what the automation can&apos;t
        know. Changes show up on the DC Ads page within a minute or two.
      </p>

      <Section title="Team" subtitle="Who appears on the DC Ads by-rep table and roster.">
        <TeamManager candidates={candidates} closeUsers={closeUsers} team={team} unmapped={unmapped} />
      </Section>

      <Section
        title="Landing pages"
        subtitle="The pages ads drive to — their names, Typeforms, videos, and the answer that counts as a qualified opt-in."
      >
        <DcLpManager pages={pages} wistia={wistia} typeforms={typeforms} />
      </Section>

      <Section
        title="Campaigns"
        subtitle="Which Meta campaigns count on the DC Ads page, and which landing page each one drives to."
      >
        <DcCampaignManager campaigns={campaigns} pages={pages} />
      </Section>
    </div>
  )
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <section style={{ marginTop: 34 }}>
      <div
        className="geg-mono"
        style={{
          fontSize: 12,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: 'var(--color-geg-text)',
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-geg-text-3)', margin: '4px 0 14px' }}>
        {subtitle}
      </div>
      {children}
    </section>
  )
}
