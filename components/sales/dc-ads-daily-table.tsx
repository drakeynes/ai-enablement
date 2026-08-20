'use client'

import { useMemo, useState } from 'react'

import type { DcAdsDailyRow } from '@/lib/db/dc-ads'

import { FineNote } from './fine-note'

// DC ads page — the rolling last-30-days daily cohort table (was 5 days;
// boss 2026-08-13; rebuilt 2026-08-15). Each row is that ET day's opt-in
// cohort: spend + opt-ins freeze when the day ends, every stage column is the
// cohort's LIFETIME progression and keeps climbing as those leads text back,
// connect, and close. Pinned to the rolling window, independent of the date
// picker; scoped to the ad cascade + landing-page dropdown.
//
// 2026-08-15 (boss items 7+8): one scroll container with a STICKY header and
// a STICKY Day column (scroll anywhere, always know the day); every stage
// count carries its per-that-day cost underneath (spend ÷ count — the boss's
// "cost per anything" ask, as a sub-line instead of 8 more columns); D0/D3/D7
// units show a dash while the day is too young for the window to have matured
// (a hard 0 read as "no closes" when the answer was "too early"); and the
// full speed-to-lead block runs per day on the right (same per-lead rows +
// 12p–12a ET clock as the speed boxes — computed in lib/db/dc-ads.ts).
// A real <table> (not a CSS grid): position:sticky on th/td needs a single
// scrollport, and the old two-tier grid scroller couldn't freeze a column.
//
// 2026-08-20 (Nabeel): COLUMN HEADERS SORT — click a metric header to order
// the 30 days by it (highest first → lowest first → back to day order).
// Client-side and display-only; dash cells sort last either way.

const SCROLL_MAX_HEIGHT = 480

// dN ROAS = dN units × $300 ÷ the day's spend.
function roas(units: number, spendUsd: number | null): string {
  if (spendUsd == null || spendUsd <= 0) return '—'
  return ((units * 300) / spendUsd).toFixed(2)
}

function fmtUsd(value: number | null): string {
  // Null = no spend rows that day (e.g. days before a filtered campaign
  // launched). Render $0, not "—" — the boss reads "—" as missing data.
  return (value ?? 0).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtCount(value: number): string {
  return value.toLocaleString('en-US')
}

// AI lead-quality cell (0151): avg /10 over the cohort's dc_ads-reviewed
// leads; '—' until the 0150 rubric has graded any (forward-only — old-rubric
// reviews never show). Sub-line = the qualified-only avg (only rendered
// once any leads are reviewed; the review count stays out of the cell by
// boss request 2026-08-19).
export function aiQTop(aiQ: number | null): string {
  return aiQ !== null ? aiQ.toFixed(1) : '—'
}

export function aiQSub(aiQQual: number | null, n: number): string | undefined {
  if (n === 0) return undefined
  return `Q ${aiQQual !== null ? aiQQual.toFixed(1) : '—'}`
}

// Cost-per sub-line: the day's spend ÷ the count. '—' when the count is 0
// (no division), $0 when the spend is null/zero (boss rule: $0, not "—").
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

// ET date string → "Wed, Jul 9".
function fmtDay(etDate: string): string {
  const [y, m, d] = etDate.split('-').map((n) => parseInt(n, 10))
  const dt = new Date(Date.UTC(y, m - 1, d, 12, 0, 0))
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).format(dt)
}

// Whole days between two YYYY-MM-DD dates (todayEt - etDate).
function ageDays(etDate: string, todayEt: string): number {
  const toUtc = (ymd: string) => {
    const [y, m, d] = ymd.split('-').map((n) => parseInt(n, 10))
    return Date.UTC(y, m - 1, d)
  }
  return Math.round((toUtc(todayEt) - toUtc(etDate)) / 86_400_000)
}

// Ratio for sorting: null (sorts last) when the denominator is 0 — matches
// the '—' the cell shows.
function share(n: number, d: number): number | null {
  return d > 0 ? n / d : null
}

// `m` = shown on MOBILE too (Day, Spend, Opt-ins, Units, Closed, ROAS); the
// other ~26 columns are desktop-only — the sticky Day column plus a sliver
// of scrolling was unusable on a phone (boss 2026-08-15).
//
// `sort` (Nabeel 2026-08-20) = the header-click sort value: what the CELL
// shows, as a number — dashes (immature DN, zero denominators) sort as null
// so a click never reveals an order the eye can't verify. Day has no sort:
// day order IS the reset state (third click on any column).
type DailyHeader = {
  label: string
  align?: 'left'
  m?: boolean
  sort?: (r: DcAdsDailyRow, age: number) => number | null
}
const HEADERS: DailyHeader[] = [
  { label: 'Day', align: 'left', m: true },
  // Null spend renders as $0 here (boss rule) — sort it as 0 to match.
  { label: 'Spend', m: true, sort: (r) => r.spendUsd ?? 0 },
  { label: 'Opt-ins', m: true, sort: (r) => r.optIns },
  { label: 'Qualified', sort: (r) => r.qualified },
  { label: 'SMS', sort: (r) => r.sms },
  { label: 'SMS+MQL', sort: (r) => r.smsMql },
  { label: 'Connects', sort: (r) => r.connected },
  { label: 'HVC', sort: (r) => r.hvc },
  // AI lead-quality (0151): the day's avg dc_ads-rubric review score over
  // reviewed cohort leads — sub-line carries the qualified-only avg + n.
  { label: 'AI Q', sort: (r) => r.aiQ },
  { label: 'Units', m: true, sort: (r) => r.units },
  { label: 'Closed', m: true, sort: (r) => r.closed },
  { label: 'D0 U', sort: (r, age) => (age >= 1 ? r.unitsD0 : null) },
  { label: 'D3 U', sort: (r, age) => (age >= 3 ? r.unitsD3 : null) },
  { label: 'D7 U', sort: (r, age) => (age >= 7 ? r.unitsD7 : null) },
  { label: 'D0 ROAS', sort: (r, age) => (age >= 1 ? share(r.unitsD0 * 300, r.spendUsd ?? 0) : null) },
  { label: 'D3 ROAS', sort: (r, age) => (age >= 3 ? share(r.unitsD3 * 300, r.spendUsd ?? 0) : null) },
  { label: 'D7 ROAS', sort: (r, age) => (age >= 7 ? share(r.unitsD7 * 300, r.spendUsd ?? 0) : null) },
  { label: 'ROAS', m: true, sort: (r) => share(r.cashUsd, r.spendUsd ?? 0) },
  { label: 'Avg speed', sort: (r) => r.avgSpeedSec },
  { label: 'Median dial', sort: (r) => r.medianDialSec },
  { label: 'Intensity', sort: (r) => r.avgIntensity },
  { label: 'Conn rate', sort: (r) => r.connectedRate },
  { label: 'Dialed <1m', sort: (r) => share(r.under1, r.optIns) },
  { label: '<5m', sort: (r) => share(r.under5, r.optIns) },
  { label: '<10m', sort: (r) => share(r.under10, r.optIns) },
  { label: '<30m', sort: (r) => share(r.under30, r.optIns) },
  { label: '>30m', sort: (r) => share(r.over30, r.optIns) },
  { label: 'Never', sort: (r) => share(r.neverDialed, r.optIns) },
  { label: 'SMS eng', sort: (r) => share(r.smsEngaged, r.smsTexted) },
  { label: 'MQL→C', sort: (r) => share(r.closed, r.qualified) },
  { label: 'NonQ→C', sort: (r) => share(r.unqualifiedClosed, r.unqualified) },
  { label: 'HVC→C', sort: (r) => share(r.closed, r.hvc) },
  { label: 'Conn→C', sort: (r) => share(r.closed, r.connected) },
  // Qualified-only speed block (boss 2026-08-17): the same speed set over
  // that day's tf-qualified leads only — % denominators are the day's
  // Qualified count. Desktop-only like the rest of the speed columns.
  { label: 'Q avg speed', sort: (r) => r.qspeed.avgSpeedSec },
  { label: 'Q median', sort: (r) => r.qspeed.medianDialSec },
  { label: 'Q intensity', sort: (r) => r.qspeed.avgIntensity },
  { label: 'Q conn rate', sort: (r) => r.qspeed.connectedRate },
  { label: 'Q <1m', sort: (r) => share(r.qspeed.under1, r.qualified) },
  { label: 'Q <5m', sort: (r) => share(r.qspeed.under5, r.qualified) },
  { label: 'Q <10m', sort: (r) => share(r.qspeed.under10, r.qualified) },
  { label: 'Q <30m', sort: (r) => share(r.qspeed.under30, r.qualified) },
  { label: 'Q >30m', sort: (r) => share(r.qspeed.over30, r.qualified) },
  { label: 'Q never', sort: (r) => share(r.qspeed.neverDialed, r.qualified) },
  { label: 'Q SMS eng', sort: (r) => share(r.qspeed.smsEngaged, r.qspeed.smsTexted) },
]

// Build one stage-drill href: the day as the window + the current facets +
// the lead-list toggles for that stage, anchored at the list (Nabeel
// 2026-08-18: click a count → see the leads behind it).
function drillHref(etDate: string, facetQuery: string, toggles: string): string {
  const parts = [`start=${etDate}`, `end=${etDate}`, facetQuery, toggles].filter(Boolean)
  return `/sales-dashboard/dc-ads?${parts.join('&')}#leads`
}

export function DcAdsDailyTable({
  rows,
  todayEt,
  facetQuery,
}: {
  rows: DcAdsDailyRow[]
  todayEt: string
  facetQuery: string
}) {
  // Header-click sort (Nabeel 2026-08-20): click a metric → highest day
  // first, click again → lowest first, third click → back to day order.
  // Display-only — nothing else on the page reads the row order.
  const [sort, setSort] = useState<{ idx: number; dir: 'desc' | 'asc' } | null>(null)
  const onSort = (idx: number) =>
    setSort((cur) =>
      cur?.idx !== idx ? { idx, dir: 'desc' } : cur.dir === 'desc' ? { idx, dir: 'asc' } : null,
    )

  const sorted = useMemo(() => {
    const key = sort ? HEADERS[sort.idx].sort : undefined
    if (!key) return rows
    const mul = sort!.dir === 'desc' ? -1 : 1
    return rows
      .slice()
      .sort((a, b) => {
        const va = key(a, ageDays(a.etDate, todayEt))
        const vb = key(b, ageDays(b.etDate, todayEt))
        // Dash cells sort last in BOTH directions — they carry no value.
        if (va == null || vb == null) return va == null && vb == null ? 0 : va == null ? 1 : -1
        return (va - vb) * mul
      })
  }, [rows, sort, todayEt])

  return (
    <div style={{ marginTop: 24 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}
      >
        Last 30 days · by opt-in day
      </div>
      <FineNote style={{ letterSpacing: '0.04em', lineHeight: 1.6, marginBottom: 12 }} summary="How to read this table">
        Each row is the cohort that opted in that ET day; the Day and Spend columns stay frozen while the rest
        scrolls. <b>Column headers are clickable</b> — one click ranks the 30 days by that metric
        (highest first), a second click flips to lowest first, a third restores day order; dash
        cells always sink to the bottom. Spend and opt-ins are fixed once the day ends; every stage column keeps climbing as
        that day&apos;s leads text back, connect, and close — recent days always look lighter. The
        small figure under each stage count is that day&apos;s <b>cost per</b> (spend ÷ count).
        <b> Stage counts are clickable</b> — a click jumps to the lead list below, scoped to that
        day with the matching toggles lit, so the number turns into names.{' '}
        <b>AI Q</b> = the day&apos;s average AI lead-quality score (0–10) from the call reviews —
        each reviewed lead counts once (its newest reviewed call); the sub-line is the same average
        over <b>qualified</b> leads only (only connected calls get reviews, and scoring started
        2026-08-18 — a dash means no reviewed leads that day, not zero quality).{' '}
        <b>D0 / D3 / D7 U</b> = units closed the same day / under 3 days / under 7 days after the
        opt-in (cumulative); a cell stays a dash until its window has FULLY elapsed — a DN number
        only ever appears final (early closes show in the stage columns meanwhile); the
        matching ROAS columns = those units × $300 ÷ the day&apos;s spend. The right block is the
        speed-to-lead set per day (12p–12a ET clock, same math as the boxes below): dialed-within
        shares are % of that day&apos;s opt-ins. The <b>Q-prefixed block</b> repeats the speed set
        over that day&apos;s QUALIFIED leads only (% of the day&apos;s Qualified count). Follows the
        ad chooser and landing-page dropdown.
      </FineNote>

      {/* ONE scroll container both ways — sticky header (top) + sticky Day
          column (left) need a single scrollport to pin against. */}
      <div style={{ maxHeight: SCROLL_MAX_HEIGHT, overflow: 'auto', border: '1px solid var(--color-geg-border)', borderRadius: 8 }}>
        {/* min-width from md up only — the phone's six-column set fits as-is. */}
        <table
          className="md:min-w-[3620px]"
          style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%' }}
        >
          <thead>
            <tr>
              {HEADERS.map((h, i) => {
                const active = sort?.idx === i
                return (
                  <th
                    key={h.label}
                    // Day (i=0) is sticky-left everywhere; Spend (i=1) joins it
                    // on md+ (boss 2026-08-15, desktop only) — pinned at the Day
                    // column's fixed 132px width.
                    className={`${h.m ? 'geg-mono' : 'geg-mono hidden md:table-cell'}${
                      i === 0 ? ' md:w-[132px]' : i === 1 ? ' md:left-[132px]' : ''
                    }`}
                    onClick={h.sort ? () => onSort(i) : undefined}
                    title={h.sort ? 'Sort the days by this column — again for lowest first, once more for day order' : undefined}
                    aria-sort={active ? (sort!.dir === 'desc' ? 'descending' : 'ascending') : undefined}
                    style={{
                      position: 'sticky',
                      top: 0,
                      ...(i === 0 ? { left: 0, zIndex: 3 } : { zIndex: i === 1 ? 3 : 2 }),
                      background: 'var(--color-geg-bg-elev)',
                      padding: '9px 12px',
                      fontSize: 9.5,
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      color: active ? 'var(--color-geg-accent)' : 'var(--color-geg-text-faint)',
                      fontWeight: 500,
                      textAlign: h.align ?? 'right',
                      whiteSpace: 'nowrap',
                      borderBottom: '1px solid var(--color-geg-border)',
                      ...(h.sort ? { cursor: 'pointer', userSelect: 'none' } : {}),
                    }}
                  >
                    {h.label}
                    {active ? (sort!.dir === 'desc' ? ' ▾' : ' ▴') : ''}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const age = ageDays(r.etDate, todayEt)
              return (
                <tr key={r.etDate}>
                  <td
                    className="geg-serif md:w-[132px]"
                    style={{
                      position: 'sticky',
                      left: 0,
                      zIndex: 1,
                      background: 'var(--color-geg-bg)',
                      padding: '10px 12px',
                      fontSize: 14,
                      color: 'var(--color-geg-text)',
                      letterSpacing: '-0.002em',
                      whiteSpace: 'nowrap',
                      borderBottom: '1px dashed var(--color-geg-border)',
                      borderRight: '1px solid var(--color-geg-border)',
                    }}
                  >
                    {fmtDay(r.etDate)}
                  </td>
                  <Td
                    top={fmtUsd(r.spendUsd)}
                    m
                    xcls="md:sticky md:left-[132px] md:z-[1] md:bg-[var(--color-geg-bg)] md:shadow-[1px_0_0_var(--color-geg-border)]"
                  />
                  <Td top={fmtCount(r.optIns)} sub={costPer(r.spendUsd, r.optIns)} accent m href={drillHref(r.etDate, facetQuery, '')} />
                  <Td top={fmtCount(r.qualified)} sub={costPer(r.spendUsd, r.qualified)} href={drillHref(r.etDate, facetQuery, 'lq=qualified')} />
                  <Td top={fmtCount(r.sms)} sub={costPer(r.spendUsd, r.sms)} href={drillHref(r.etDate, facetQuery, 'ld=sms')} />
                  <Td top={fmtCount(r.smsMql)} sub={costPer(r.spendUsd, r.smsMql)} href={drillHref(r.etDate, facetQuery, 'ld=sms&lq=qualified')} />
                  <Td top={fmtCount(r.connected)} sub={costPer(r.spendUsd, r.connected)} href={drillHref(r.etDate, facetQuery, 'ld=connected')} />
                  <Td top={fmtCount(r.hvc)} sub={costPer(r.spendUsd, r.hvc)} href={drillHref(r.etDate, facetQuery, 'ld=hvc')} />
                  <Td top={aiQTop(r.aiQ)} sub={aiQSub(r.aiQQual, r.aiQN)} />
                  <Td top={fmtCount(r.units)} sub={costPer(r.spendUsd, r.units)} m href={drillHref(r.etDate, facetQuery, 'ld=closed')} />
                  <Td top={fmtCount(r.closed)} sub={costPer(r.spendUsd, r.closed)} m href={drillHref(r.etDate, facetQuery, 'ld=closed')} />
                  {/* STRICT maturity dashes (boss 2026-08-15): a DN cell is a
                      dash until the window has fully elapsed — even if units
                      already landed (the stage columns tell that story). A DN
                      number only ever appears final. */}
                  <Td top={age >= 1 ? fmtCount(r.unitsD0) : '—'} />
                  <Td top={age >= 3 ? fmtCount(r.unitsD3) : '—'} />
                  <Td top={age >= 7 ? fmtCount(r.unitsD7) : '—'} />
                  <Td top={age >= 1 ? roas(r.unitsD0, r.spendUsd) : '—'} />
                  <Td top={age >= 3 ? roas(r.unitsD3, r.spendUsd) : '—'} />
                  <Td top={age >= 7 ? roas(r.unitsD7, r.spendUsd) : '—'} />
                  <Td top={r.spendUsd && r.spendUsd > 0 ? (r.cashUsd / r.spendUsd).toFixed(2) : '—'} accent m />
                  <Td top={fmtDur(r.avgSpeedSec)} />
                  <Td top={fmtDur(r.medianDialSec)} />
                  <Td top={r.avgIntensity !== null ? `${r.avgIntensity.toFixed(1)}×` : '—'} />
                  <Td
                    top={r.connectedRate !== null ? `${(r.connectedRate * 100).toFixed(0)}%` : '—'}
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
                  <Td top={fmtDur(r.qspeed.avgSpeedSec)} />
                  <Td top={fmtDur(r.qspeed.medianDialSec)} />
                  <Td top={r.qspeed.avgIntensity !== null ? `${r.qspeed.avgIntensity.toFixed(1)}×` : '—'} />
                  <Td
                    top={r.qspeed.connectedRate !== null ? `${(r.qspeed.connectedRate * 100).toFixed(0)}%` : '—'}
                    sub={`of ${r.qualified} qual`}
                  />
                  <Td top={pct(r.qspeed.under1, r.qualified)} sub={fmtCount(r.qspeed.under1)} />
                  <Td top={pct(r.qspeed.under5, r.qualified)} sub={fmtCount(r.qspeed.under5)} />
                  <Td top={pct(r.qspeed.under10, r.qualified)} sub={fmtCount(r.qspeed.under10)} />
                  <Td top={pct(r.qspeed.under30, r.qualified)} sub={fmtCount(r.qspeed.under30)} />
                  <Td top={pct(r.qspeed.over30, r.qualified)} sub={fmtCount(r.qspeed.over30)} />
                  <Td top={pct(r.qspeed.neverDialed, r.qualified)} sub={fmtCount(r.qspeed.neverDialed)} />
                  <Td
                    top={pct(r.qspeed.smsEngaged, r.qspeed.smsTexted)}
                    sub={`${r.qspeed.smsEngaged} / ${r.qspeed.smsTexted}`}
                  />
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Td({
  top,
  sub,
  accent,
  m,
  xcls,
  href,
}: {
  top: string
  sub?: string
  accent?: boolean
  m?: boolean
  // Extra classes — the Spend cell uses this for its md-only sticky-left
  // treatment (frozen beside Day on desktop; normal cell on the phone).
  xcls?: string
  // Stage-drill link (Nabeel 2026-08-18) — the whole cell becomes a quiet
  // link to the lead list pre-filtered to this slice.
  href?: string
}) {
  const body = (
    <>
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
    </>
  )
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
      {href ? (
        <a href={href} title="See these leads in the list below" style={{ display: 'block', textDecoration: 'none', cursor: 'pointer' }}>
          {body}
        </a>
      ) : (
        body
      )}
    </td>
  )
}
