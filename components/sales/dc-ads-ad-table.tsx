'use client'

import { useMemo, useState } from 'react'

import type { DcAdsAdTableRow } from '@/lib/db/dc-ads'

// DC ads page — the PER-AD table (boss item 10, 2026-08-15), directly under
// the 30-day daily table: one row per ad with window activity (spend, opt-ins,
// or clicks — so zero-opt-in spend is visible), same construction as the daily
// table: one scroll container, sticky header, STICKY AD-NAME column, cost-per
// sub-lines under every stage count, and the full per-ad speed-to-lead block
// (same per-lead rows + 12p–12a ET clock as the boxes). Scoped to the page's
// date picker + the global cascade/LP facets; the two dropdowns here narrow
// the LIST client-side (campaign → ad set) without touching the page filter —
// jump from many ads to a few without losing the rest of the page's view.
// Small formatters duplicated from dc-ads-daily-table on purpose — the two
// tables must be free to drift apart.

const SCROLL_MAX_HEIGHT = 480
const MIN_TABLE_WIDTH = 3150
const ACCENT = '#b48ead'

function roas(cashUsd: number, spendUsd: number | null): string {
  if (spendUsd == null || spendUsd <= 0) return '—'
  return (cashUsd / spendUsd).toFixed(2)
}

function fmtUsd(value: number | null, digits = 0): string {
  if (value == null) return '—'
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function fmtCount(value: number | null): string {
  return value == null ? '—' : value.toLocaleString('en-US')
}

function costPer(spendUsd: number | null, count: number): string {
  if (count <= 0) return '—'
  return fmtUsd((spendUsd ?? 0) / count)
}

function pct(n: number, d: number): string {
  return d > 0 ? `${((n / d) * 100).toFixed(0)}%` : '—'
}

function rate1(n: number, d: number): string {
  return d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '—'
}

function fmtDur(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) {
    const m = Math.floor(sec / 60)
    return `${m}m ${Math.round(sec - m * 60)
      .toString()
      .padStart(2, '0')}s`
  }
  const h = Math.floor(sec / 3600)
  return `${h}h ${Math.round((sec - h * 3600) / 60)}m`
}

const HEADERS: { label: string; align?: 'left' }[] = [
  { label: 'Ad', align: 'left' },
  { label: 'Spend' },
  { label: 'Impr' },
  { label: 'Clicks' },
  { label: 'CTR' },
  { label: 'CPM' },
  { label: '$/Click' },
  { label: 'Opt-ins' },
  { label: 'Qualified' },
  { label: 'SMS' },
  { label: 'SMS+MQL' },
  { label: 'Connects' },
  { label: 'HVC' },
  { label: 'Units' },
  { label: 'Closed' },
  { label: 'Cash' },
  { label: 'ROAS' },
  { label: 'D0 U' },
  { label: 'D3 U' },
  { label: 'D7 U' },
  { label: 'Avg speed' },
  { label: 'Median dial' },
  { label: 'Intensity' },
  { label: 'Conn rate' },
  { label: 'Dialed <1m' },
  { label: '<5m' },
  { label: '<10m' },
  { label: '<30m' },
  { label: '>30m' },
  { label: 'Never' },
  { label: 'SMS eng' },
  { label: 'MQL→C' },
  { label: 'NonQ→C' },
  { label: 'HVC→C' },
  { label: 'Conn→C' },
]

export function DcAdsAdTable({
  rows,
  lpLabels,
}: {
  rows: DcAdsAdTableRow[]
  lpLabels: Record<string, string>
}) {
  const [campaignSel, setCampaignSel] = useState<string>('')
  const [adsetSel, setAdsetSel] = useState<string>('')

  const campaigns = useMemo(() => {
    const seen = new Map<string, string>()
    for (const r of rows) {
      if (r.campaignId && !seen.has(r.campaignId))
        seen.set(r.campaignId, r.campaignName ?? r.campaignId)
    }
    return Array.from(seen, ([id, label]) => ({ id, label }))
  }, [rows])

  const adsets = useMemo(() => {
    const seen = new Map<string, string>()
    for (const r of rows) {
      if (campaignSel && r.campaignId !== campaignSel) continue
      if (r.adsetId && !seen.has(r.adsetId)) seen.set(r.adsetId, r.adsetName ?? r.adsetId)
    }
    return Array.from(seen, ([id, label]) => ({ id, label }))
  }, [rows, campaignSel])

  const visible = useMemo(
    () =>
      rows.filter(
        (r) =>
          (!campaignSel || r.campaignId === campaignSel) &&
          (!adsetSel || r.adsetId === adsetSel),
      ),
    [rows, campaignSel, adsetSel],
  )

  return (
    <div style={{ marginTop: 24 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}
      >
        Ads · {visible.length === rows.length ? rows.length : `${visible.length} of ${rows.length}`} with activity · selected dates
      </div>
      <div
        className="geg-mono"
        style={{ fontSize: 9, letterSpacing: '0.04em', color: 'var(--color-geg-text-faint)', marginBottom: 10 }}
      >
        One row per ad with activity in the selected dates (spend, opt-ins, or clicks — an ad
        spending without opt-ins is exactly the row to notice). Ad-side numbers from Meta; every
        stage from Opt-ins on is the ad&apos;s own leads through the same definitions as the rest of
        the page, with that ad&apos;s <b>cost per</b> underneath each count. The right block is the
        ad&apos;s speed-to-lead set (12p–12a ET clock). D0/D3/D7 = units closed within 0/3/7 days of
        each lead&apos;s own opt-in. The dropdowns narrow this list only — the page filter above is
        untouched. Follows the date picker + campaign chooser + landing-page dropdown.
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <select
          value={campaignSel}
          onChange={(e) => {
            setCampaignSel(e.target.value)
            setAdsetSel('')
          }}
          aria-label="Narrow to one campaign"
          className="geg-mono"
          style={selectStyle(campaignSel !== '')}
        >
          <option value="">All campaigns</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
        <select
          value={adsetSel}
          onChange={(e) => setAdsetSel(e.target.value)}
          aria-label="Narrow to one ad set"
          className="geg-mono"
          style={selectStyle(adsetSel !== '')}
        >
          <option value="">All ad sets</option>
          {adsets.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
      </div>

      <div style={{ maxHeight: SCROLL_MAX_HEIGHT, overflow: 'auto', border: '1px solid var(--color-geg-border)', borderRadius: 8 }}>
        <table style={{ borderCollapse: 'separate', borderSpacing: 0, minWidth: MIN_TABLE_WIDTH, width: '100%' }}>
          <thead>
            <tr>
              {HEADERS.map((h, i) => (
                <th
                  key={h.label}
                  className="geg-mono"
                  style={{
                    position: 'sticky',
                    top: 0,
                    ...(i === 0 ? { left: 0, zIndex: 3 } : { zIndex: 2 }),
                    background: 'var(--color-geg-bg-elev)',
                    padding: '9px 12px',
                    fontSize: 9.5,
                    letterSpacing: '0.1em',
                    textTransform: 'uppercase',
                    color: 'var(--color-geg-text-faint)',
                    fontWeight: 500,
                    textAlign: h.align ?? 'right',
                    whiteSpace: 'nowrap',
                    borderBottom: '1px solid var(--color-geg-border)',
                  }}
                >
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td
                  colSpan={HEADERS.length}
                  className="geg-serif"
                  style={{ padding: '22px 12px', textAlign: 'center', fontStyle: 'italic', color: 'var(--color-geg-text-3)', fontSize: 14 }}
                >
                  No ads match.
                </td>
              </tr>
            ) : (
              visible.map((r) => {
                const paused = !!r.status && r.status !== 'ACTIVE'
                const subBits = [
                  r.lpSlug ? (lpLabels[r.lpSlug] ?? r.lpSlug) : null,
                  campaignSel ? null : r.campaignName,
                  paused ? r.status : null,
                ].filter(Boolean)
                return (
                  <tr key={r.adId ?? '(untagged)'} style={{ opacity: paused ? 0.75 : 1 }}>
                    <td
                      style={{
                        position: 'sticky',
                        left: 0,
                        zIndex: 1,
                        background: 'var(--color-geg-bg)',
                        padding: '8px 12px 7px',
                        whiteSpace: 'nowrap',
                        borderBottom: '1px dashed var(--color-geg-border)',
                        borderRight: '1px solid var(--color-geg-border)',
                        maxWidth: 260,
                      }}
                    >
                      <span
                        className="geg-serif"
                        style={{ display: 'block', fontSize: 13.5, color: 'var(--color-geg-text)', overflow: 'hidden', textOverflow: 'ellipsis' }}
                      >
                        {r.adName}
                      </span>
                      <span
                        className="geg-mono"
                        style={{ display: 'block', fontSize: 8.5, letterSpacing: '0.04em', color: paused ? 'var(--color-geg-text-3)' : 'var(--color-geg-text-faint)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis' }}
                      >
                        {subBits.join(' · ') || '—'}
                      </span>
                    </td>
                    <Td top={fmtUsd(r.spendUsd)} accent />
                    <Td top={fmtCount(r.impressions)} />
                    <Td top={fmtCount(r.uniqueClicks)} />
                    <Td top={r.ctr != null ? `${r.ctr.toFixed(1)}%` : '—'} />
                    <Td top={fmtUsd(r.cpm, 2)} />
                    <Td top={fmtUsd(r.cpcUnique, 2)} />
                    <Td top={fmtCount(r.optIns)} sub={costPer(r.spendUsd, r.optIns)} accent />
                    <Td top={fmtCount(r.qualified)} sub={costPer(r.spendUsd, r.qualified)} />
                    <Td top={fmtCount(r.sms)} sub={costPer(r.spendUsd, r.sms)} />
                    <Td top={fmtCount(r.smsMql)} sub={costPer(r.spendUsd, r.smsMql)} />
                    <Td top={fmtCount(r.connected)} sub={costPer(r.spendUsd, r.connected)} />
                    <Td top={fmtCount(r.hvc)} sub={costPer(r.spendUsd, r.hvc)} />
                    <Td top={fmtCount(r.units)} sub={costPer(r.spendUsd, r.units)} />
                    <Td top={fmtCount(r.closed)} sub={costPer(r.spendUsd, r.closed)} />
                    <Td top={fmtUsd(r.cashUsd)} />
                    <Td top={roas(r.cashUsd, r.spendUsd)} accent />
                    <Td top={fmtCount(r.unitsD0)} />
                    <Td top={fmtCount(r.unitsD3)} />
                    <Td top={fmtCount(r.unitsD7)} />
                    <Td top={fmtDur(r.avgSpeedSec)} />
                    <Td top={fmtDur(r.medianDialSec)} />
                    <Td top={r.avgIntensity != null ? `${r.avgIntensity.toFixed(1)}×` : '—'} />
                    <Td
                      top={r.connectedRate != null ? `${(r.connectedRate * 100).toFixed(0)}%` : '—'}
                      sub={`${r.connected} conn`}
                    />
                    <Td top={pct(r.under1, r.optIns)} sub={fmtCount(r.under1)} />
                    <Td top={pct(r.under5, r.optIns)} sub={fmtCount(r.under5)} />
                    <Td top={pct(r.under10, r.optIns)} sub={fmtCount(r.under10)} />
                    <Td top={pct(r.under30, r.optIns)} sub={fmtCount(r.under30)} />
                    <Td top={pct(r.over30, r.optIns)} sub={fmtCount(r.over30)} />
                    <Td top={pct(r.neverDialed, r.optIns)} sub={fmtCount(r.neverDialed)} />
                    <Td top={pct(r.smsEngaged, r.smsTexted)} sub={`${r.smsEngaged} / ${r.smsTexted}`} />
                    <Td top={rate1(r.closed, r.qualified)} sub={`${r.closed} / ${r.qualified}`} />
                    <Td top={rate1(r.unqualifiedClosed, r.unqualified)} sub={`${r.unqualifiedClosed} / ${r.unqualified}`} />
                    <Td top={rate1(r.closed, r.hvc)} sub={`${r.closed} / ${r.hvc}`} />
                    <Td top={rate1(r.closed, r.connected)} sub={`${r.closed} / ${r.connected}`} />
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function selectStyle(active: boolean): React.CSSProperties {
  return {
    fontSize: 11,
    padding: '6px 10px',
    borderRadius: 6,
    cursor: 'pointer',
    border: `1px solid ${active ? ACCENT : 'var(--color-geg-border)'}`,
    background: 'var(--color-geg-bg-elev)',
    color: active ? 'var(--color-geg-text)' : 'var(--color-geg-text-2)',
    maxWidth: 320,
  }
}

function Td({ top, sub, accent }: { top: string; sub?: string; accent?: boolean }) {
  return (
    <td
      style={{
        padding: sub ? '8px 12px 7px' : '10px 12px',
        textAlign: 'right',
        whiteSpace: 'nowrap',
        verticalAlign: 'middle',
        borderBottom: '1px dashed var(--color-geg-border)',
      }}
    >
      <span
        className="geg-numeric-serif"
        style={{
          display: 'block',
          fontSize: 14,
          color: accent ? 'var(--color-geg-accent)' : 'var(--color-geg-text-2)',
          letterSpacing: '-0.01em',
        }}
      >
        {top}
      </span>
      {sub ? (
        <span
          className="geg-mono"
          style={{ display: 'block', fontSize: 8.5, letterSpacing: '0.04em', color: 'var(--color-geg-text-faint)', marginTop: 2 }}
        >
          {sub}
        </span>
      ) : null}
    </td>
  )
}
