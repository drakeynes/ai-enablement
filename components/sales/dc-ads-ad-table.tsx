'use client'

import { useMemo, useState } from 'react'

import type { DcAdsAdTableRow } from '@/lib/db/dc-ads'

import { FineNote } from './fine-note'

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
    return `${m}m ${Math.floor(sec - m * 60)
      .toString()
      .padStart(2, '0')}s`
  }
  const h = Math.floor(sec / 3600)
  return `${h}h ${Math.floor((sec - h * 3600) / 60)}m`
}

// `m` = shown on MOBILE too (the decision set: name, spend, opt-ins, units,
// closed, ROAS). Everything else is desktop-only — on a phone the sticky name
// column was eating the viewport and the other 30 columns lived in a
// two-inch scroll strip (boss 2026-08-15).
const HEADERS: { label: string; align?: 'left'; m?: boolean }[] = [
  { label: 'Ad', align: 'left', m: true },
  { label: 'Spend', m: true },
  { label: 'Impr' },
  { label: 'Clicks' },
  { label: 'CTR' },
  { label: 'CPM' },
  { label: '$/Click' },
  { label: 'Opt-ins', m: true },
  { label: 'Qualified' },
  { label: 'SMS' },
  { label: 'SMS+MQL' },
  { label: 'Connects' },
  { label: 'HVC' },
  { label: 'Units', m: true },
  { label: 'Closed', m: true },
  { label: 'Cash' },
  { label: 'ROAS', m: true },
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

type MsOption = { id: string; label: string; sub?: string; count?: number }

export function DcAdsAdTable({
  rows,
  lpLabels,
}: {
  rows: DcAdsAdTableRow[]
  lpLabels: Record<string, string>
}) {
  // Multi-select narrowing (boss 2026-08-15): union WITHIN a dropdown, AND
  // ACROSS them — pick one campaign, two of its ad sets, three ads spread
  // over those ad sets, and exactly those ads show. Higher levels narrow the
  // OPTIONS offered below (and prune newly-invalid deeper picks); the list
  // filter itself is the plain three-way AND.
  const [campaignSel, setCampaignSel] = useState<ReadonlySet<string>>(new Set())
  const [adsetSel, setAdsetSel] = useState<ReadonlySet<string>>(new Set())
  const [adSel, setAdSel] = useState<ReadonlySet<string>>(new Set())

  const campaigns = useMemo<MsOption[]>(() => {
    const seen = new Map<string, MsOption>()
    for (const r of rows) {
      if (!r.campaignId) continue
      const o = seen.get(r.campaignId)
      if (o) o.count = (o.count ?? 0) + 1
      else seen.set(r.campaignId, { id: r.campaignId, label: r.campaignName ?? r.campaignId, count: 1 })
    }
    return Array.from(seen.values())
  }, [rows])

  const adsets = useMemo<MsOption[]>(() => {
    const seen = new Map<string, MsOption>()
    for (const r of rows) {
      if (!r.adsetId) continue
      if (campaignSel.size > 0 && (!r.campaignId || !campaignSel.has(r.campaignId))) continue
      const o = seen.get(r.adsetId)
      if (o) o.count = (o.count ?? 0) + 1
      else
        seen.set(r.adsetId, {
          id: r.adsetId,
          label: r.adsetName ?? r.adsetId,
          sub: campaignSel.size === 1 ? undefined : (r.campaignName ?? undefined),
          count: 1,
        })
    }
    return Array.from(seen.values())
  }, [rows, campaignSel])

  const adOptions = useMemo<MsOption[]>(() => {
    const out: MsOption[] = []
    for (const r of rows) {
      if (!r.adId) continue
      if (campaignSel.size > 0 && (!r.campaignId || !campaignSel.has(r.campaignId))) continue
      if (adsetSel.size > 0 && (!r.adsetId || !adsetSel.has(r.adsetId))) continue
      out.push({ id: r.adId, label: r.adName, sub: r.adsetName ?? undefined })
    }
    return out
  }, [rows, campaignSel, adsetSel])

  // Toggle handlers prune deeper selections that a higher-level change just
  // invalidated (deselect a campaign → its ad sets/ads drop out of the sets).
  const toggleCampaign = (id: string) => {
    const next = toggleIn(campaignSel, id)
    setCampaignSel(next)
    if (next.size > 0) {
      const validAdsets = new Set(
        rows.filter((r) => r.campaignId && next.has(r.campaignId)).map((r) => r.adsetId),
      )
      const prunedAdsets = new Set(Array.from(adsetSel).filter((a) => validAdsets.has(a)))
      setAdsetSel(prunedAdsets)
      const validAds = new Set(
        rows
          .filter(
            (r) =>
              r.campaignId &&
              next.has(r.campaignId) &&
              (prunedAdsets.size === 0 || (r.adsetId && prunedAdsets.has(r.adsetId))),
          )
          .map((r) => r.adId),
      )
      setAdSel(new Set(Array.from(adSel).filter((a) => validAds.has(a))))
    }
  }
  const toggleAdset = (id: string) => {
    const next = toggleIn(adsetSel, id)
    setAdsetSel(next)
    if (next.size > 0) {
      const validAds = new Set(
        rows.filter((r) => r.adsetId && next.has(r.adsetId)).map((r) => r.adId),
      )
      setAdSel(new Set(Array.from(adSel).filter((a) => validAds.has(a))))
    }
  }

  const visible = useMemo(
    () =>
      rows.filter(
        (r) =>
          (campaignSel.size === 0 || (r.campaignId != null && campaignSel.has(r.campaignId))) &&
          (adsetSel.size === 0 || (r.adsetId != null && adsetSel.has(r.adsetId))) &&
          (adSel.size === 0 || (r.adId != null && adSel.has(r.adId))),
      ),
    [rows, campaignSel, adsetSel, adSel],
  )

  return (
    <div style={{ marginTop: 24 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}
      >
        Ads · {visible.length === rows.length ? rows.length : `${visible.length} of ${rows.length}`} with activity · selected dates
      </div>
      <FineNote style={{ letterSpacing: '0.04em', lineHeight: 1.6, marginBottom: 10 }} summary="How to read this table">
        One row per ad with activity in the selected dates (spend, opt-ins, or clicks — an ad
        spending without opt-ins is exactly the row to notice). Ad-side numbers from Meta; every
        stage from Opt-ins on is the ad&apos;s own leads through the same definitions as the rest of
        the page, with that ad&apos;s <b>cost per</b> underneath each count. The right block is the
        ad&apos;s speed-to-lead set (12p–12a ET clock). D0/D3/D7 = units closed within 0/3/7 days of
        each lead&apos;s own opt-in. The three pickers narrow this list only (the page filter above
        is untouched): tick any mix — within a picker selections add together, across pickers they
        combine, and higher levels narrow what the lower ones offer. Each row&apos;s sub-line says
        which campaign · ad set the ad lives in (hover for the full path). Follows the date picker
        + campaign chooser + landing-page dropdown.
      </FineNote>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <MultiSelect
          label="Campaigns"
          options={campaigns}
          selected={campaignSel}
          onToggle={toggleCampaign}
          onClear={() => setCampaignSel(new Set())}
        />
        <MultiSelect
          label="Ad sets"
          options={adsets}
          selected={adsetSel}
          onToggle={toggleAdset}
          onClear={() => setAdsetSel(new Set())}
        />
        <MultiSelect
          label="Ads"
          options={adOptions}
          selected={adSel}
          onToggle={(id) => setAdSel(toggleIn(adSel, id))}
          onClear={() => setAdSel(new Set())}
        />
      </div>

      <div style={{ maxHeight: SCROLL_MAX_HEIGHT, overflow: 'auto', border: '1px solid var(--color-geg-border)', borderRadius: 8 }}>
        {/* min-width only from md up — on a phone the visible column set is
            small enough to fit, and forcing 3150px would stretch it absurdly. */}
        <table
          className="md:min-w-[3150px]"
          style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%' }}
        >
          <thead>
            <tr>
              {HEADERS.map((h, i) => (
                <th
                  key={h.label}
                  // Ad (i=0) is sticky-left everywhere; Spend (i=1) joins it
                  // on md+ (boss 2026-08-17, desktop only) — the Ad column is
                  // width-fixed at 260px so Spend can pin beside it.
                  className={`${h.m ? 'geg-mono' : 'geg-mono hidden md:table-cell'}${
                    i === 0 ? ' md:w-[260px] md:min-w-[260px]' : i === 1 ? ' md:left-[260px]' : ''
                  }`}
                  style={{
                    position: 'sticky',
                    top: 0,
                    ...(i === 0 ? { left: 0, zIndex: 3 } : { zIndex: i === 1 ? 3 : 2 }),
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
                // Lineage indicator (boss 2026-08-15): every ad row says which
                // campaign + ad set it lives in — essential once picks span
                // ad sets. Truncated; the tooltip carries the full path.
                const subBits = [
                  trunc(r.campaignName, 20),
                  trunc(r.adsetName, 20),
                  r.lpSlug ? (lpLabels[r.lpSlug] ?? r.lpSlug) : null,
                  paused ? r.status : null,
                ].filter(Boolean)
                const lineage = [r.campaignName, r.adsetName, r.adName]
                  .filter(Boolean)
                  .join(' → ')
                return (
                  <tr key={r.adId ?? '(untagged)'} style={{ opacity: paused ? 0.75 : 1 }}>
                    <td
                      title={lineage}
                      className="max-w-[150px] md:w-[260px] md:min-w-[260px] md:max-w-[260px]"
                      style={{
                        position: 'sticky',
                        left: 0,
                        zIndex: 1,
                        background: 'var(--color-geg-bg)',
                        padding: '8px 12px 7px',
                        whiteSpace: 'nowrap',
                        borderBottom: '1px dashed var(--color-geg-border)',
                        borderRight: '1px solid var(--color-geg-border)',
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
                    <Td
                      top={fmtUsd(r.spendUsd)}
                      accent
                      m
                      xcls="md:sticky md:left-[260px] md:z-[1] md:bg-[var(--color-geg-bg)] md:shadow-[1px_0_0_var(--color-geg-border)]"
                    />
                    <Td top={fmtCount(r.impressions)} />
                    <Td top={fmtCount(r.uniqueClicks)} />
                    <Td top={r.ctr != null ? `${r.ctr.toFixed(1)}%` : '—'} />
                    <Td top={fmtUsd(r.cpm, 2)} />
                    <Td top={fmtUsd(r.cpcUnique, 2)} />
                    <Td top={fmtCount(r.optIns)} sub={costPer(r.spendUsd, r.optIns)} accent m />
                    <Td top={fmtCount(r.qualified)} sub={costPer(r.spendUsd, r.qualified)} />
                    <Td top={fmtCount(r.sms)} sub={costPer(r.spendUsd, r.sms)} />
                    <Td top={fmtCount(r.smsMql)} sub={costPer(r.spendUsd, r.smsMql)} />
                    <Td top={fmtCount(r.connected)} sub={costPer(r.spendUsd, r.connected)} />
                    <Td top={fmtCount(r.hvc)} sub={costPer(r.spendUsd, r.hvc)} />
                    <Td top={fmtCount(r.units)} sub={costPer(r.spendUsd, r.units)} m />
                    <Td top={fmtCount(r.closed)} sub={costPer(r.spendUsd, r.closed)} m />
                    <Td top={fmtUsd(r.cashUsd)} />
                    <Td top={roas(r.cashUsd, r.spendUsd)} accent m />
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

function toggleIn(set: ReadonlySet<string>, id: string): ReadonlySet<string> {
  const next = new Set(set)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}

function trunc(s: string | null, n: number): string | null {
  if (!s) return null
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

// The dropdown-toggle hybrid (boss 2026-08-15): a button opening a checkbox
// panel — union within the panel, AND across the three panels. Page-local on
// purpose; close on outside click via a transparent backdrop.
function MultiSelect({
  label,
  options,
  selected,
  onToggle,
  onClear,
}: {
  label: string
  options: MsOption[]
  selected: ReadonlySet<string>
  onToggle: (id: string) => void
  onClear: () => void
}) {
  const [open, setOpen] = useState(false)
  const active = selected.size > 0
  const buttonText = active
    ? selected.size === 1
      ? (trunc(options.find((o) => selected.has(o.id))?.label ?? '1 selected', 26) ?? '1 selected')
      : `${selected.size} selected`
    : `All ${label.toLowerCase()}`
  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="geg-mono"
        style={{
          fontSize: 10.5,
          letterSpacing: '0.05em',
          padding: '6px 12px',
          borderRadius: 6,
          cursor: 'pointer',
          border: `1px solid ${active ? ACCENT : 'var(--color-geg-border)'}`,
          background: active ? ACCENT : 'var(--color-geg-bg-elev)',
          color: active ? '#fff' : 'var(--color-geg-text-2)',
          maxWidth: 300,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {label}: {buttonText} {open ? '▴' : '▾'}
      </button>
      {open ? (
        <>
          <span
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 19 }}
          />
          <span
            style={{
              position: 'absolute',
              top: 'calc(100% + 4px)',
              left: 0,
              zIndex: 20,
              minWidth: 260,
              maxWidth: 380,
              maxHeight: 300,
              overflowY: 'auto',
              display: 'block',
              background: 'var(--color-geg-bg-elev)',
              border: '1px solid var(--color-geg-border-strong)',
              borderRadius: 8,
              boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
              padding: '6px 0',
            }}
          >
            <button
              type="button"
              onClick={() => {
                onClear()
                setOpen(false)
              }}
              className="geg-mono"
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '6px 12px',
                fontSize: 10,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: active ? ACCENT : 'var(--color-geg-text-faint)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Clear · show all
            </button>
            {options.length === 0 ? (
              <span
                className="geg-mono"
                style={{ display: 'block', padding: '8px 12px', fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}
              >
                Nothing matches the selection above.
              </span>
            ) : (
              options.map((o) => {
                const checked = selected.has(o.id)
                return (
                  <label
                    key={o.id}
                    style={{
                      display: 'flex',
                      alignItems: 'baseline',
                      gap: 8,
                      padding: '5px 12px',
                      cursor: 'pointer',
                      background: checked ? 'var(--color-geg-accent-fill)' : 'transparent',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(o.id)}
                      style={{ accentColor: ACCENT, flexShrink: 0, position: 'relative', top: 1 }}
                    />
                    <span style={{ minWidth: 0 }}>
                      <span
                        className="geg-mono"
                        style={{ display: 'block', fontSize: 11, color: 'var(--color-geg-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                      >
                        {o.label}
                        {o.count != null ? (
                          <span style={{ color: 'var(--color-geg-text-faint)' }}> · {o.count}</span>
                        ) : null}
                      </span>
                      {o.sub ? (
                        <span
                          className="geg-mono"
                          style={{ display: 'block', fontSize: 8.5, color: 'var(--color-geg-text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                        >
                          {o.sub}
                        </span>
                      ) : null}
                    </span>
                  </label>
                )
              })
            )}
          </span>
        </>
      ) : null}
    </span>
  )
}

function Td({
  top,
  sub,
  accent,
  m,
  xcls,
}: {
  top: string
  sub?: string
  accent?: boolean
  m?: boolean
  // Extra classes — the Spend cell's md-only sticky-left treatment.
  xcls?: string
}) {
  return (
    <td
      className={[m ? '' : 'hidden md:table-cell', xcls ?? ''].join(' ').trim() || undefined}
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
