'use client'

import { useState, useTransition } from 'react'

import type { AdminDcCampaign, AdminDcLandingPage } from '@/lib/db/dc-setup'
import { setDcCampaignActive, setDcCampaignLp } from '../actions'
import { primaryBtn, dangerBtn, inputStyle, SectionNote } from './ui'

// DC Setup · Campaigns — the dc_ads_campaigns registry (0130). Campaigns are
// AUTO-DETECTED (instant-form scan + creative destination scan) — this editor
// only curates: which landing page a campaign belongs to, and whether it
// counts on the DC Ads page at all. Retiring one removes its spend AND its
// leads from every number on the page.

export function DcCampaignManager({
  campaigns,
  pages,
}: {
  campaigns: AdminDcCampaign[]
  pages: AdminDcLandingPage[]
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {campaigns.map((c) => (
        <CampaignRow key={c.campaignId} campaign={c} pages={pages} />
      ))}
      <SectionNote text="New campaigns register themselves within ~15 minutes of their ads running (instant-form campaigns by their form setup; landing-page campaigns by where their ads point). If one is missing, check that its ads link to a digitalcollege.ai page." />
    </div>
  )
}

function CampaignRow({ campaign, pages }: { campaign: AdminDcCampaign; pages: AdminDcLandingPage[] }) {
  const [pending, startTransition] = useTransition()
  const [msg, setMsg] = useState<string | null>(null)
  const c = campaign

  const run = (fn: () => Promise<{ ok: true } | { ok: false; error: string }>, okMsg: string) => {
    setMsg(null)
    startTransition(async () => {
      const res = await fn()
      setMsg(res.ok ? okMsg : `Error: ${res.error}`)
    })
  }

  return (
    <div
      style={{
        border: '1px solid var(--color-geg-border)',
        background: 'var(--color-geg-bg-elev)',
        borderRadius: 8,
        padding: '10px 14px',
        opacity: c.active ? 1 : 0.6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="geg-mono" style={{ fontSize: 12.5, color: 'var(--color-geg-text)', minWidth: 280 }}>
          {c.campaignName}
        </span>
        <span className="geg-mono" style={{ fontSize: 10, color: 'var(--color-geg-text-faint)' }}>
          {c.sourceKind === 'instant_form' ? 'instant form (no LP)' : 'landing page'}
        </span>
        {c.sourceKind === 'landing_page' ? (
          <select
            style={{ ...inputStyle, width: 180 }}
            value={c.lpSlug ?? ''}
            disabled={pending}
            onChange={(e) =>
              run(
                () => setDcCampaignLp(c.campaignId, e.target.value || null),
                'Landing page updated — numbers re-stamp within ~15 min.',
              )
            }
            aria-label={`Landing page for ${c.campaignName}`}
          >
            <option value="">— no landing page —</option>
            {pages.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.label}
              </option>
            ))}
          </select>
        ) : null}
        <span style={{ marginLeft: 'auto' }}>
          <button
            type="button"
            disabled={pending}
            style={c.active ? dangerBtn(pending) : primaryBtn(pending)}
            onClick={() => {
              if (
                c.active &&
                !window.confirm(
                  `Retire "${c.campaignName}" from the DC Ads page? Its spend AND its leads leave every number. Use for campaigns that never belonged.`,
                )
              )
                return
              run(() => setDcCampaignActive(c.campaignId, !c.active), c.active ? 'Retired.' : 'Restored.')
            }}
          >
            {c.active ? 'Retire' : 'Restore'}
          </button>
        </span>
      </div>
      {msg ? (
        <div
          className="geg-mono"
          style={{ marginTop: 6, fontSize: 11.5, color: msg.startsWith('Error') ? 'var(--color-geg-danger, #c0392b)' : 'var(--color-geg-text-2)' }}
        >
          {msg}
        </div>
      ) : null}
    </div>
  )
}
