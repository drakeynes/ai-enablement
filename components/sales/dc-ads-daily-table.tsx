import type { DcAdsDailyRow } from '@/lib/db/dc-ads'

// DC ads page — the rolling last-30-days daily cohort table (was 5 days;
// boss 2026-08-13), borrowed from the Advertising Hub's DailyFunnelTable but
// carrying the DC stage-row metrics: Spend · Opt-ins · Qualified · SMS ·
// SMS+MQL · Connects · HVC · Units · Closed. Each row is that ET day's
// opt-in cohort: spend + opt-ins freeze when the day ends, every column to
// their right is the cohort's LIFETIME progression and keeps climbing as
// those leads text back, connect, and close. Rows scroll inside a fixed-height
// box (header stays put); pinned to the rolling window, independent of the
// date picker; scoped to the ad cascade + landing-page dropdown.

const COLS =
  '1.15fr 0.95fr 0.85fr 0.95fr 0.7fr 0.95fr 0.95fr 0.7fr 0.7fr 0.8fr 0.6fr 0.6fr 0.6fr 0.75fr 0.75fr 0.75fr 0.75fr'
// 17 columns — give them room and let the whole table scroll sideways.
const MIN_TABLE_WIDTH = 1420

// Rows visible before scrolling — the box clips at ~9 so the table doesn't
// dominate the page; the remaining days scroll.
const SCROLL_MAX_HEIGHT = 420

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

export function DcAdsDailyTable({ rows }: { rows: DcAdsDailyRow[] }) {
  return (
    <div style={{ marginTop: 24 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}
      >
        Last 30 days · by opt-in day
      </div>
      <div
        className="geg-mono"
        style={{ fontSize: 9, letterSpacing: '0.04em', color: 'var(--color-geg-text-faint)', marginBottom: 12 }}
      >
        Each row is the cohort that opted in that ET day. Spend and opt-ins are fixed once the day
        ends; every column to their right keeps climbing as that day&apos;s leads text back, connect,
        and close — recent days always look lighter. <b>D0 / D3 / D7 U</b> = units closed the same
        day / under 3 days / under 7 days after the opt-in (cumulative); the matching ROAS columns =
        those units × $300 ÷ the day&apos;s spend, next to overall ROAS — how fast each day&apos;s
        spend pays back. Follows the ad chooser and landing-page dropdown above.
      </div>

      {/* Horizontal scroller wraps BOTH the header and the vertical box so the
          17 columns stay aligned while the page never scrolls sideways. */}
      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: MIN_TABLE_WIDTH }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: COLS,
              gap: 10,
              padding: '6px 4px 12px',
              borderBottom: '1px solid var(--color-geg-border)',
              scrollbarGutter: 'stable',
              overflowY: 'hidden',
            }}
          >
            <ColH label="Day" align="left" />
            <ColH label="Spend" />
            <ColH label="Opt-ins" />
            <ColH label="Qualified" />
            <ColH label="SMS" />
            <ColH label="SMS+MQL" />
            <ColH label="Connects" />
            <ColH label="HVC" />
            <ColH label="Units" />
            <ColH label="Closed" />
            <ColH label="D0 U" />
            <ColH label="D3 U" />
            <ColH label="D7 U" />
            <ColH label="D0 ROAS" />
            <ColH label="D3 ROAS" />
            <ColH label="D7 ROAS" />
            <ColH label="ROAS" />
          </div>

          {/* The scrollable box — header stays put above. scrollbarGutter on
              both keeps the header grid aligned with the scrolling rows. */}
          <div style={{ maxHeight: SCROLL_MAX_HEIGHT, overflowY: 'auto', scrollbarGutter: 'stable' }}>
            {rows.map((r) => (
              <div
                key={r.etDate}
                style={{
                  display: 'grid',
                  gridTemplateColumns: COLS,
                  gap: 10,
                  padding: '13px 4px',
                  borderBottom: '1px dashed var(--color-geg-border)',
                  alignItems: 'center',
                }}
              >
                <span className="geg-serif" style={{ fontSize: 14, color: 'var(--color-geg-text)', letterSpacing: '-0.002em' }}>
                  {fmtDay(r.etDate)}
                </span>
                <Num value={fmtUsd(r.spendUsd)} />
                <Num value={fmtCount(r.optIns)} accent />
                <Num value={fmtCount(r.qualified)} />
                <Num value={fmtCount(r.sms)} />
                <Num value={fmtCount(r.smsMql)} />
                <Num value={fmtCount(r.connected)} />
                <Num value={fmtCount(r.hvc)} />
                <Num value={fmtCount(r.units)} />
                <Num value={fmtCount(r.closed)} />
                <Num value={fmtCount(r.unitsD0)} />
                <Num value={fmtCount(r.unitsD3)} />
                <Num value={fmtCount(r.unitsD7)} />
                <Num value={roas(r.unitsD0, r.spendUsd)} />
                <Num value={roas(r.unitsD3, r.spendUsd)} />
                <Num value={roas(r.unitsD7, r.spendUsd)} />
                <Num value={r.spendUsd && r.spendUsd > 0 ? (r.cashUsd / r.spendUsd).toFixed(2) : '—'} accent />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ColH({ label, align }: { label: string; align?: 'left' | 'right' }) {
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 10,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--color-geg-text-faint)',
        textAlign: align ?? 'right',
      }}
    >
      {label}
    </span>
  )
}

function Num({ value, accent }: { value: string; accent?: boolean }) {
  return (
    <span
      className="geg-numeric-serif"
      style={{
        fontSize: 14,
        color: accent ? 'var(--color-geg-accent)' : 'var(--color-geg-text-2)',
        letterSpacing: '-0.01em',
        textAlign: 'right',
      }}
    >
      {value}
    </span>
  )
}
