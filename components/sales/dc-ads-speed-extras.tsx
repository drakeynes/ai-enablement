import type { DcAdsFunnel } from '@/lib/db/dc-ads'
import type { DcAdsSpeedStats } from '@/lib/db/dc-ads'

// DC ads — the second row(s) of speed-to-lead stats (boss item #20,
// 2026-08-14), under the four/five headline boxes:
//   dial-speed spread  % dialed <5m / <10m / <30m (cumulative) · % >30m ·
//                      % never dialed — <30m + >30m + never = 100% — and the
//                      median time to dial. Same 12p–12a ET clock as the avg.
//   conversion + cost  MQL→Close (closed ÷ qualified) · HVC→Close · Connect→
//                      Close · CPU (adspend ÷ units, Valid-adjusted).
// Same window + filters as everything on the page.

export function DcAdsSpeedExtras({
  speed,
  funnel,
  spendUsd,
}: {
  speed: DcAdsSpeedStats
  funnel: DcAdsFunnel
  spendUsd: number
}) {
  const cohort = speed.cohortSize
  const pct = (n: number, d: number): string => (d > 0 ? `${((n / d) * 100).toFixed(0)}%` : '—')
  const rate = (n: number, d: number): string => (d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '—')
  const cells: { label: string; value: string; sub: string }[] = [
    { label: 'Dialed <5m', value: pct(speed.dialedUnder5m, cohort), sub: `${speed.dialedUnder5m} leads` },
    { label: 'Dialed <10m', value: pct(speed.dialedUnder10m, cohort), sub: `${speed.dialedUnder10m} leads` },
    { label: 'Dialed <30m', value: pct(speed.dialedUnder30m, cohort), sub: `${speed.dialedUnder30m} leads` },
    { label: 'Dialed >30m', value: pct(speed.dialedOver30m, cohort), sub: `${speed.dialedOver30m} leads` },
    { label: 'Never dialed', value: pct(speed.neverDialed, cohort), sub: `${speed.neverDialed} leads` },
    { label: 'Median time to dial', value: fmtDuration(speed.medianDialSec), sub: 'dialed leads · 12p–12a clock' },
    { label: 'MQL → Close rate', value: rate(funnel.closed, funnel.qualified), sub: `${funnel.closed} / ${funnel.qualified} qualified` },
    { label: 'HVC → Close rate', value: rate(funnel.closed, funnel.hvc), sub: `${funnel.closed} / ${funnel.hvc} HVC` },
    { label: 'Connect → Close rate', value: rate(funnel.closed, funnel.connected), sub: `${funnel.closed} / ${funnel.connected} connects` },
    {
      label: 'CPU · cost per unit',
      value: funnel.units > 0 ? `$${(spendUsd / funnel.units).toFixed(0)}` : '—',
      sub: `$${Math.round(spendUsd).toLocaleString('en-US')} ÷ ${funnel.units} units`,
    },
  ]
  return (
    <div
      style={{
        marginTop: 10,
        display: 'grid',
        gridTemplateColumns: 'repeat(5, minmax(0, 1fr))',
        gap: 1,
        background: 'var(--color-geg-border)',
        border: '1px solid var(--color-geg-border)',
        borderRadius: 10,
        overflow: 'hidden',
      }}
    >
      {cells.map((c) => (
        <div key={c.label} style={{ padding: '12px 14px 10px', background: 'var(--color-geg-bg-elev)' }}>
          <div
            className="geg-mono"
            style={{ fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
          >
            {c.label}
          </div>
          <div className="geg-numeric-serif" style={{ fontSize: 21, lineHeight: '24px', letterSpacing: '-0.02em', color: 'var(--color-geg-text)' }}>
            {c.value}
          </div>
          <div className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {c.sub}
          </div>
        </div>
      ))}
    </div>
  )
}

function fmtDuration(sec: number | null): string {
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
