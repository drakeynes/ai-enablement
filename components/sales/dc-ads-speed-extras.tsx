// DC ads — the second rows of speed-to-lead stats (boss item #20, 2026-08-14;
// reshaped 2026-08-15), under the five headline boxes. Two rows of six:
//   dial-speed spread  % dialed <1m / <5m / <10m / <30m (cumulative) · % >30m ·
//                      % never dialed — <30m + >30m + never = 100%. Same
//                      12p–12a ET clock as the avg.
//   conversion + cost  median time to dial · MQL→Close (closed ÷ qualified) ·
//                      Non-qual→Close (closed non-qualified ÷ non-qualified) ·
//                      HVC→Close · Connect→Close · CPU (adspend ÷ units,
//                      Valid-adjusted).
// Since 2026-08-15 every number here is computed from the lead-roster rows by
// the dc-ads-speed-leads wrapper, so the stacked toggles narrow them all —
// EXCEPT the CPU numerator: spend has no per-lead attribution, so adspend
// stays the whole window while units shrink with the filter (footnoted on
// the page).

export function DcAdsSpeedExtras({
  cohort,
  under1,
  under5,
  under10,
  under30,
  over30,
  never,
  medianSec,
  closed,
  qualified,
  unqualified,
  unqualifiedClosed,
  hvc,
  connected,
  units,
  spendUsd,
}: {
  cohort: number
  under1: number
  under5: number
  under10: number
  under30: number
  over30: number
  never: number
  medianSec: number | null
  closed: number
  qualified: number
  unqualified: number
  // Non-qualified leads that closed anyway — the Non-qual→Close numerator is
  // the INTERSECTION (unlike MQL→Close's step-ratio closed ÷ qualified, whose
  // numerator is all closes): "of the people who said they can't pay, how
  // many bought" is the question being asked.
  unqualifiedClosed: number
  hvc: number
  connected: number
  units: number
  spendUsd: number
}) {
  const pct = (n: number, d: number): string => (d > 0 ? `${((n / d) * 100).toFixed(0)}%` : '—')
  const rate = (n: number, d: number): string => (d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '—')
  const cells: { label: string; value: string; sub: string }[] = [
    { label: 'Dialed <1m', value: pct(under1, cohort), sub: `${under1} leads` },
    { label: 'Dialed <5m', value: pct(under5, cohort), sub: `${under5} leads` },
    { label: 'Dialed <10m', value: pct(under10, cohort), sub: `${under10} leads` },
    { label: 'Dialed <30m', value: pct(under30, cohort), sub: `${under30} leads` },
    { label: 'Dialed >30m', value: pct(over30, cohort), sub: `${over30} leads` },
    { label: 'Never dialed', value: pct(never, cohort), sub: `${never} leads` },
    { label: 'Median time to dial', value: fmtDuration(medianSec), sub: 'dialed leads · 12p–12a clock' },
    { label: 'MQL → Close rate', value: rate(closed, qualified), sub: `${closed} / ${qualified} qualified` },
    { label: 'Non-qual → Close rate', value: rate(unqualifiedClosed, unqualified), sub: `${unqualifiedClosed} / ${unqualified} non-qualified` },
    { label: 'HVC → Close rate', value: rate(closed, hvc), sub: `${closed} / ${hvc} HVC` },
    { label: 'Connect → Close rate', value: rate(closed, connected), sub: `${closed} / ${connected} connects` },
    {
      label: 'CPU · cost per unit',
      value: units > 0 ? `$${(spendUsd / units).toFixed(0)}` : '—',
      sub: `$${Math.round(spendUsd).toLocaleString('en-US')} ÷ ${units} units`,
    },
  ]
  return (
    // Six columns on wide screens (the boss's two rows of six); 3 / 2 on
    // tablet / phone (mobile pass 2026-08-15) — column count via classes so
    // the breakpoints work (inline styles can't carry media queries).
    <div
      className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6"
      style={{
        marginTop: 10,
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
