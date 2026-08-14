import type { DcAdsFunnel } from '@/lib/db/dc-ads'
import type { DcPlanCounts } from '@/lib/db/funnel-dc'

const PLAN_COLS: { key: keyof DcPlanCounts; label: string }[] = [
  { key: 'base44Monthly', label: 'Base44·Mo' },
  { key: 'base44Yearly', label: 'Base44·Yr' },
  { key: 'wixMonthly', label: 'Wix·Mo' },
  { key: 'wixYearly', label: 'Wix·Yr' },
]

function PlanChip({ label, count }: { label: string; count: number }) {
  const zero = count === 0
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 4 }}>
      <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.04em', color: zero ? 'var(--color-geg-text-faint)' : 'var(--color-geg-text-3)' }}>
        {label}
      </span>
      <span className="geg-numeric-serif" style={{ fontSize: 13, color: zero ? 'var(--color-geg-text-faint)' : 'var(--color-geg-text)' }}>
        {count}
      </span>
    </span>
  )
}

// DC ads stage row — the boss's nine numbers (2026-08-13):
//   Adspend > Opt-ins > Qualified > SMS > SMS+MQL > Connects > HVC > Units > Closed
// Deliberately NOT a funnel: the stages overlap rather than nest (SMS ⊄
// Qualified, Units ≥ Closed when multi-unit deals land), so the arrows carry
// no conversion percentages — the row just puts the numbers side by side.
// One exception is guaranteed (0137): HVC = connected AND (qualified OR
// texted-us), so HVC ≤ Connects always. Cash + ROAS keep their own line
// below. Definitions in the page footer; per-lead facts in lib/db/dc-ads.ts.

const ACCENT = '#b48ead' // purple — distinct from Direct green / setter yellow / reactivation blue / outbound coral

function usd(n: number): string {
  return '$' + Math.round(n).toLocaleString('en-US')
}

function Stage({ label, value, display, accent }: { label: string; value: number; display?: string; accent?: boolean }) {
  return (
    <div style={{ flex: 1, textAlign: 'center', padding: '14px 4px' }}>
      <div
        className="geg-numeric-serif"
        style={{ fontSize: 23, lineHeight: 1, color: value === 0 ? 'var(--color-geg-text-faint)' : accent ? ACCENT : 'var(--color-geg-text)' }}
      >
        {display ?? value.toLocaleString('en-US')}
      </div>
      <div className="geg-mono" style={{ fontSize: 8.5, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', marginTop: 6, whiteSpace: 'nowrap' }}>
        {label}
      </div>
    </div>
  )
}

// Plain separator — no conversion %: the stages aren't subsets of each other.
function Arrow() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 18 }}>
      <div className="geg-mono" style={{ color: 'var(--color-geg-text-faint)', fontSize: 13 }}>→</div>
    </div>
  )
}

export function DcAdsFunnelSection({ funnel, spendUsd }: { funnel: DcAdsFunnel; spendUsd: number }) {
  const f = funnel
  const roas = spendUsd > 0 ? f.cashUsd / spendUsd : null

  return (
    <div style={{ marginTop: 14, border: '1px solid var(--color-geg-border)', borderRadius: 8, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: 'var(--color-geg-bg-elev)', borderBottom: '1px solid var(--color-geg-border)' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: ACCENT }} />
        <span className="geg-mono" style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-geg-text)' }}>
          DC Ads
        </span>
        <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}>
          · both acquisition paths · selected dates
        </span>
      </div>

      {/* The stage row — ad spend leads it; numbers only, no conversion %
          (the stages overlap rather than nest). */}
      <div style={{ display: 'flex', alignItems: 'stretch', padding: '4px 10px' }}>
        <Stage label="Adspend" value={spendUsd} display={usd(spendUsd)} accent />
        <Arrow />
        <Stage label="Opt-ins" value={f.optIns} accent />
        <Arrow />
        <Stage label="Qualified" value={f.qualified} />
        <Arrow />
        <Stage label="SMS" value={f.sms} />
        <Arrow />
        <Stage label="SMS+MQL" value={f.smsMql} />
        <Arrow />
        <Stage label="Connects" value={f.connected} />
        <Arrow />
        <Stage label="HVC" value={f.hvc} />
        <Arrow />
        <Stage label="Units" value={f.units} />
        <Arrow />
        <Stage label="Closed" value={f.closed} accent />
      </div>

      {/* Cash + ROAS line */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', borderTop: '1px solid var(--color-geg-border)', background: 'var(--color-geg-bg)' }}>
        <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}>
          Cash collected
        </span>
        <span className="geg-numeric-serif" style={{ fontSize: 18, color: f.cashUsd > 0 ? 'var(--color-geg-text)' : 'var(--color-geg-text-faint)' }}>
          {usd(f.cashUsd)}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, paddingLeft: 10, borderLeft: '1px solid var(--color-geg-border)' }}>
          <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}>
            ROAS
          </span>
          <span className="geg-numeric-serif" style={{ fontSize: 16, color: roas && roas > 0 ? 'var(--color-geg-text)' : 'var(--color-geg-text-faint)' }}>
            {roas === null ? '—' : roas.toFixed(2)}
          </span>
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 14, paddingLeft: 10, borderLeft: '1px solid var(--color-geg-border)' }}>
          {PLAN_COLS.map((c) => (
            <PlanChip key={c.key} label={c.label} count={f.closedPlans[c.key]} />
          ))}
        </span>
        <span className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)' }}>
          · $300 per DC plan unit
        </span>
        {f.markedNoPlan > 0 ? (
          <span className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)', marginLeft: 'auto' }}>
            {f.markedNoPlan} marked “DC Closed” w/o a plan → counted as showed, not closed
          </span>
        ) : null}
      </div>
    </div>
  )
}
