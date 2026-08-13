import type { DcAdsRepRow, DcAdsRepTotals } from '@/lib/db/dc-ads'

const PLAN_COLS: { key: keyof Omit<DcAdsRepTotals, 'closes'>; label: string }[] = [
  { key: 'base44Monthly', label: 'Base44·Mo' },
  { key: 'base44Yearly', label: 'Base44·Yr' },
  { key: 'wixMonthly', label: 'Wix·Mo' },
  { key: 'wixYearly', label: 'Wix·Yr' },
]

// Per-rep DC ads breakdown — the Talent DC-table detail scoped to the DC ad
// cohort (boss item 7, 2026-08-13): Dials / Connections / Shows / Closes /
// Units / plan splits / Cash, same identity bridge as ever (Close calls +
// Airtable forms via team_members — link people in DC Setup). ACTIVITY-scoped.
// Unlike Outbound (closers only), EVERY rep with activity is listed: this
// pool is dial-heavy and the dialing work is what the page manages.

const ACCENT = '#b48ead' // purple

function fmtCash(n: number): string {
  return `$${n.toLocaleString('en-US')}`
}

function Cell({ value, strong = false, muted = false }: { value: string; strong?: boolean; muted?: boolean }) {
  return (
    <td
      className="geg-numeric-serif"
      style={{
        padding: '9px 14px',
        textAlign: 'right',
        fontSize: 14,
        whiteSpace: 'nowrap',
        color: muted ? 'var(--color-geg-text-faint)' : strong ? 'var(--color-geg-text)' : 'var(--color-geg-text-2)',
        fontWeight: strong ? 600 : 400,
      }}
    >
      {value}
    </td>
  )
}

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

function HeadCell({ label, first = false }: { label: string; first?: boolean }) {
  return (
    <th
      className="geg-mono"
      style={{
        padding: '8px 14px',
        textAlign: first ? 'left' : 'right',
        fontSize: 9.5,
        letterSpacing: '0.07em',
        textTransform: 'uppercase',
        color: 'var(--color-geg-text-faint)',
        fontWeight: 500,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </th>
  )
}

export function DcAdsByRepSection({ rows, totals }: { rows: DcAdsRepRow[]; totals: DcAdsRepTotals }) {
  const colTotals = rows.reduce(
    (a, r) => ({
      dials: a.dials + r.dials,
      connections: a.connections + r.connections,
      shows: a.shows + r.shows,
      closes: a.closes + r.closes,
      units: a.units + r.units,
      cash: a.cash + r.cash,
    }),
    { dials: 0, connections: 0, shows: 0, closes: 0, units: 0, cash: 0 },
  )

  return (
    <div style={{ marginTop: 14, border: '1px solid var(--color-geg-border)', borderRadius: 8, overflow: 'hidden' }}>
      {/* Header — total closes + the unit mix sold in the window */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'var(--color-geg-bg-elev)', borderBottom: '1px solid var(--color-geg-border)', flexWrap: 'wrap' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: ACCENT }} />
        <span className="geg-mono" style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-geg-text)' }}>
          By rep
        </span>
        <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}>
          · activity in the selected dates
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, marginLeft: 'auto', paddingLeft: 10, borderLeft: '1px solid var(--color-geg-border)' }}>
          <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}>
            Closes
          </span>
          <span className="geg-numeric-serif" style={{ fontSize: 16, color: totals.closes > 0 ? 'var(--color-geg-text)' : 'var(--color-geg-text-faint)' }}>
            {totals.closes}
          </span>
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 14, paddingLeft: 10, borderLeft: '1px solid var(--color-geg-border)' }}>
          {PLAN_COLS.map((c) => (
            <PlanChip key={c.key} label={c.label} count={totals[c.key]} />
          ))}
        </span>
        <span className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)' }}>
          · units sold
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="geg-mono" style={{ padding: '16px 14px', background: 'var(--color-geg-bg)', fontSize: 11, letterSpacing: '0.04em', color: 'var(--color-geg-text-faint)' }}>
          No rep activity in the selected dates.
        </div>
      ) : (
        <div style={{ background: 'var(--color-geg-bg)', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-geg-border)' }}>
                <HeadCell label="Rep" first />
                <HeadCell label="Dials" />
                <HeadCell label="Connections" />
                <HeadCell label="Shows" />
                <HeadCell label="Closes" />
                <HeadCell label="Units" />
                <HeadCell label="B44·Mo" />
                <HeadCell label="B44·Yr" />
                <HeadCell label="Wix·Mo" />
                <HeadCell label="Wix·Yr" />
                <HeadCell label="Cash" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.rep} style={{ borderBottom: '1px solid var(--color-geg-border)' }}>
                  <td className="geg-mono" style={{ padding: '9px 14px', fontSize: 12, letterSpacing: '0.02em', color: 'var(--color-geg-text)', whiteSpace: 'nowrap' }}>
                    {r.rep}
                    {r.teamMemberId ? null : (
                      <span
                        title="Not linked to a team member yet — link identities in DC Setup so this person's dials and closes merge into one row."
                        className="geg-mono"
                        style={{ marginLeft: 7, fontSize: 8.5, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', border: '1px dashed var(--color-geg-border)', borderRadius: 3, padding: '1px 4px' }}
                      >
                        NOT LINKED
                      </span>
                    )}
                  </td>
                  <Cell value={r.dials.toLocaleString('en-US')} />
                  <Cell value={r.connections.toLocaleString('en-US')} />
                  <Cell value={r.shows.toLocaleString('en-US')} />
                  <Cell value={r.closes.toLocaleString('en-US')} strong />
                  <Cell value={r.units.toLocaleString('en-US')} />
                  <Cell value={r.base44Monthly.toLocaleString('en-US')} muted={r.base44Monthly === 0} />
                  <Cell value={r.base44Yearly.toLocaleString('en-US')} muted={r.base44Yearly === 0} />
                  <Cell value={r.wixMonthly.toLocaleString('en-US')} muted={r.wixMonthly === 0} />
                  <Cell value={r.wixYearly.toLocaleString('en-US')} muted={r.wixYearly === 0} />
                  <Cell value={fmtCash(r.cash)} strong />
                </tr>
              ))}
              {/* totals */}
              <tr style={{ background: 'var(--color-geg-bg-elev)' }}>
                <td className="geg-mono" style={{ padding: '9px 14px', fontSize: 9.5, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', whiteSpace: 'nowrap' }}>
                  Total
                </td>
                <Cell value={colTotals.dials.toLocaleString('en-US')} muted />
                <Cell value={colTotals.connections.toLocaleString('en-US')} muted />
                <Cell value={colTotals.shows.toLocaleString('en-US')} muted />
                <Cell value={colTotals.closes.toLocaleString('en-US')} strong />
                <Cell value={colTotals.units.toLocaleString('en-US')} strong />
                <Cell value={totals.base44Monthly.toLocaleString('en-US')} muted />
                <Cell value={totals.base44Yearly.toLocaleString('en-US')} muted />
                <Cell value={totals.wixMonthly.toLocaleString('en-US')} muted />
                <Cell value={totals.wixYearly.toLocaleString('en-US')} muted />
                <Cell value={fmtCash(colTotals.cash)} strong />
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* footnote */}
      <div className="geg-mono" style={{ padding: '9px 14px', background: 'var(--color-geg-bg-elev)', borderTop: '1px solid var(--color-geg-border)', fontSize: 9, letterSpacing: '0.05em', color: 'var(--color-geg-text-faint)', lineHeight: 1.7 }}>
        Activity-scoped, not cohort-scoped: what each rep did in the selected dates, regardless of when the
        lead opted in. <b>Dials</b> = outbound calls · <b>Connections</b> = calls ≥90s, counted per CALL
        (a lead reached twice counts twice; inbound pickups count) — so the column sum runs higher than the
        funnel&apos;s Connected, which counts each <i>lead</i> once · <b>Shows</b> = leads pitched (a filed
        DC sale form or closer report) · <b>Closes</b> = DC closes with a plan · <b>Units</b> = plan units
        (the B44/Wix columns are their split) · <b>Cash</b> = $300 per unit. A deal with two closers credits
        both; the header totals count each deal once. Every rep with activity is listed; a{' '}
        <i>not linked</i> tag means the person&apos;s dialing and closing identities haven&apos;t been
        connected yet — fix it in DC Setup. All rows cover DC-ads pool leads only.
      </div>
    </div>
  )
}
