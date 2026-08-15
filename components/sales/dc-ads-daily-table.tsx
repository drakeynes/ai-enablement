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

// `m` = shown on MOBILE too (Day, Spend, Opt-ins, Units, Closed, ROAS); the
// other ~26 columns are desktop-only — the sticky Day column plus a sliver
// of scrolling was unusable on a phone (boss 2026-08-15).
const HEADERS: { label: string; align?: 'left'; m?: boolean }[] = [
  { label: 'Day', align: 'left', m: true },
  { label: 'Spend', m: true },
  { label: 'Opt-ins', m: true },
  { label: 'Qualified' },
  { label: 'SMS' },
  { label: 'SMS+MQL' },
  { label: 'Connects' },
  { label: 'HVC' },
  { label: 'Units', m: true },
  { label: 'Closed', m: true },
  { label: 'D0 U' },
  { label: 'D3 U' },
  { label: 'D7 U' },
  { label: 'D0 ROAS' },
  { label: 'D3 ROAS' },
  { label: 'D7 ROAS' },
  { label: 'ROAS', m: true },
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

export function DcAdsDailyTable({ rows, todayEt }: { rows: DcAdsDailyRow[]; todayEt: string }) {
  return (
    <div style={{ marginTop: 24 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}
      >
        Last 30 days · by opt-in day
      </div>
      <FineNote style={{ letterSpacing: '0.04em', lineHeight: 1.6, marginBottom: 12 }} summary="How to read this table">
        Each row is the cohort that opted in that ET day; the Day column stays frozen while the rest
        scrolls. Spend and opt-ins are fixed once the day ends; every stage column keeps climbing as
        that day&apos;s leads text back, connect, and close — recent days always look lighter. The
        small figure under each stage count is that day&apos;s <b>cost per</b> (spend ÷ count).{' '}
        <b>D0 / D3 / D7 U</b> = units closed the same day / under 3 days / under 7 days after the
        opt-in (cumulative); a cell stays a dash until its window has FULLY elapsed — a DN number
        only ever appears final (early closes show in the stage columns meanwhile); the
        matching ROAS columns = those units × $300 ÷ the day&apos;s spend. The right block is the
        speed-to-lead set per day (12p–12a ET clock, same math as the boxes below): dialed-within
        shares are % of that day&apos;s opt-ins. Follows the ad chooser and landing-page dropdown.
      </FineNote>

      {/* ONE scroll container both ways — sticky header (top) + sticky Day
          column (left) need a single scrollport to pin against. */}
      <div style={{ maxHeight: SCROLL_MAX_HEIGHT, overflow: 'auto', border: '1px solid var(--color-geg-border)', borderRadius: 8 }}>
        {/* min-width from md up only — the phone's six-column set fits as-is. */}
        <table
          className="md:min-w-[2680px]"
          style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%' }}
        >
          <thead>
            <tr>
              {HEADERS.map((h, i) => (
                <th
                  key={h.label}
                  className={h.m ? 'geg-mono' : 'geg-mono hidden md:table-cell'}
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
            {rows.map((r) => {
              const age = ageDays(r.etDate, todayEt)
              return (
                <tr key={r.etDate}>
                  <td
                    className="geg-serif"
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
                  <Td top={fmtUsd(r.spendUsd)} m />
                  <Td top={fmtCount(r.optIns)} sub={costPer(r.spendUsd, r.optIns)} accent m />
                  <Td top={fmtCount(r.qualified)} sub={costPer(r.spendUsd, r.qualified)} />
                  <Td top={fmtCount(r.sms)} sub={costPer(r.spendUsd, r.sms)} />
                  <Td top={fmtCount(r.smsMql)} sub={costPer(r.spendUsd, r.smsMql)} />
                  <Td top={fmtCount(r.connected)} sub={costPer(r.spendUsd, r.connected)} />
                  <Td top={fmtCount(r.hvc)} sub={costPer(r.spendUsd, r.hvc)} />
                  <Td top={fmtCount(r.units)} sub={costPer(r.spendUsd, r.units)} m />
                  <Td top={fmtCount(r.closed)} sub={costPer(r.spendUsd, r.closed)} m />
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
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Td({ top, sub, accent, m }: { top: string; sub?: string; accent?: boolean; m?: boolean }) {
  return (
    <td
      className={m ? undefined : 'hidden md:table-cell'}
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
