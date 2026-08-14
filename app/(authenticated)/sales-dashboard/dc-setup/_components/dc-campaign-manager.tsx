'use client'

import { useState, useTransition } from 'react'

import type { AdminDcCampaign, AdminDcLandingPage } from '@/lib/db/dc-setup'
import { setDcCampaignActive, setDcCampaignLps } from '../actions'
import { primaryBtn, dangerBtn, SectionNote } from './ui'

// DC Setup · Campaigns — the dc_ads_campaigns registry (0130). Campaigns are
// AUTO-DETECTED (instant-form scan + creative destination scan) — this editor
// only curates: which landing page(s) a campaign drives to (tick several when
// split-testing — 0138; the first ticked is the primary), and whether it
// counts on the DC Ads page at all. Retiring one removes its spend AND its
// leads from every number on the page. Whatever is ticked here is exactly
// what the DC Ads page's landing-page dropdown offers.

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
          <span style={{ display: 'inline-flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {pages
              .filter((p) => p.active || c.lpSlugs.includes(p.slug))
              .map((p) => {
                const checked = c.lpSlugs.includes(p.slug)
                return (
                  <label
                    key={p.slug}
                    className="geg-mono"
                    style={{
                      fontSize: 11,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      color: checked ? 'var(--color-geg-text)' : 'var(--color-geg-text-faint)',
                      cursor: pending ? 'default' : 'pointer',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={pending}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...c.lpSlugs, p.slug]
                          : c.lpSlugs.filter((s) => s !== p.slug)
                        run(
                          () => setDcCampaignLps(c.campaignId, next),
                          'Landing pages updated — lead numbers re-stamp within ~15 min.',
                        )
                      }}
                    />
                    {p.label}
                    {checked && c.lpSlugs[0] === p.slug && c.lpSlugs.length > 1 ? ' (primary)' : ''}
                  </label>
                )
              })}
          </span>
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
