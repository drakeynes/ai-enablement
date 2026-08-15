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

// Seconds → "5h 40m" / "12m" / "45s" / "—" (zero). Talk time reads as time on
// the phone, not a raw number.
function fmtTalk(sec: number): string {
  if (!sec) return '—'
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.round((sec % 3600) / 60)}m`
  if (sec >= 60) return `${Math.round(sec / 60)}m`
  return `${sec}s`
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

function RepTr({ r, faded = false }: { r: DcAdsRepRow; faded?: boolean }) {
  return (
    <tr style={{ borderBottom: '1px solid var(--color-geg-border)', opacity: faded ? 0.65 : 1 }}>
      <td className="geg-mono" style={{ padding: '9px 14px', fontSize: 12, letterSpacing: '0.02em', color: 'var(--color-geg-text)', whiteSpace: 'nowrap' }}>
        {r.rep}
      </td>
      <Cell value={r.dials.toLocaleString('en-US')} />
      <Cell value={r.connections.toLocaleString('en-US')} />
      <Cell value={fmtTalk(r.talkSeconds ?? 0)} muted={!r.talkSeconds} />
      <Cell value={r.closes.toLocaleString('en-US')} strong />
      <Cell value={r.units.toLocaleString('en-US')} />
      <Cell value={r.base44Monthly.toLocaleString('en-US')} muted={r.base44Monthly === 0} />
      <Cell value={r.base44Yearly.toLocaleString('en-US')} muted={r.base44Yearly === 0} />
      <Cell value={r.wixMonthly.toLocaleString('en-US')} muted={r.wixMonthly === 0} />
      <Cell value={r.wixYearly.toLocaleString('en-US')} muted={r.wixYearly === 0} />
      <Cell value={fmtCash(r.cash)} strong />
    </tr>
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

export function DcAdsByRepSection({
  rows,
  totals,
  activeTeamMemberIds,
}: {
  rows: DcAdsRepRow[]
  totals: DcAdsRepTotals
  // team_members ids of the ACTIVE sales roster (DC Setup). Rows of CONFIRMED
  // former members collapse into a "former reps" group so the table reads as
  // the current team (boss 2026-08-14); activity from identities with NO team
  // row at all is not rendered — membership is controlled via the Airtable
  // Sales Team Member table → DC Setup verify (Drake 2026-08-14).
  activeTeamMemberIds: string[]
}) {
  const activeIds = new Set(activeTeamMemberIds)
  const confirmed = rows.filter((r) => r.teamMemberId)
  const current = confirmed.filter((r) => activeIds.has(r.teamMemberId as string))
  const former = confirmed.filter((r) => !activeIds.has(r.teamMemberId as string))
  const colTotals = confirmed.reduce(
    (a, r) => ({
      dials: a.dials + r.dials,
      connections: a.connections + r.connections,
      talkSeconds: a.talkSeconds + (r.talkSeconds ?? 0),
      closes: a.closes + r.closes,
      units: a.units + r.units,
      cash: a.cash + r.cash,
    }),
    { dials: 0, connections: 0, talkSeconds: 0, closes: 0, units: 0, cash: 0 },
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
                <HeadCell label="Talk time" />
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
              {current.map((r) => (
                <RepTr key={r.rep} r={r} />
              ))}
              {/* totals — cover EVERYONE incl. the former group below */}
              <tr style={{ background: 'var(--color-geg-bg-elev)' }}>
                <td className="geg-mono" style={{ padding: '9px 14px', fontSize: 9.5, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', whiteSpace: 'nowrap' }}>
                  Total{former.length > 0 ? ' (incl. former)' : ''}
                </td>
                <Cell value={colTotals.dials.toLocaleString('en-US')} muted />
                <Cell value={colTotals.connections.toLocaleString('en-US')} muted />
                <Cell value={fmtTalk(colTotals.talkSeconds)} muted />
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

          {/* Former + unlinked reps — deactivated in DC Setup or not linked to
              a team member. Collapsed by default: their window activity still
              counts (see totals) but the table reads as the current team. */}
          {former.length > 0 ? (
            <details style={{ borderTop: '1px solid var(--color-geg-border)' }}>
              <summary
                className="geg-mono"
                style={{
                  padding: '9px 14px',
                  fontSize: 10,
                  letterSpacing: '0.07em',
                  textTransform: 'uppercase',
                  color: 'var(--color-geg-text-faint)',
                  cursor: 'pointer',
                }}
              >
                Former reps · {former.length} · {former.reduce((a, r) => a + r.dials, 0).toLocaleString('en-US')} dials ·{' '}
                {former.reduce((a, r) => a + r.closes, 0)} closes — click to show
              </summary>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <tbody>
                  {former.map((r) => (
                    <RepTr key={r.rep} r={r} faded />
                  ))}
                </tbody>
              </table>
            </details>
          ) : null}
        </div>
      )}

      {/* footnote */}
      <div className="geg-mono" style={{ padding: '9px 14px', background: 'var(--color-geg-bg-elev)', borderTop: '1px solid var(--color-geg-border)', fontSize: 9, letterSpacing: '0.05em', color: 'var(--color-geg-text-faint)', lineHeight: 1.7 }}>
        Activity-scoped, not cohort-scoped: what each rep did in the selected dates, regardless of when the
        lead opted in. <b>Dials</b> = outbound calls · <b>Connections</b> = calls ≥90s, counted per CALL
        (a lead reached twice counts twice; inbound pickups count) — so the column sum runs higher than the
        funnel&apos;s Connected, which counts each <i>lead</i> once · <b>Talk time</b> = total time on the
        phone (sum of call durations, all calls both directions) · <b>Closes</b> = DC closes with a plan · <b>Units</b> = plan units
        (the B44/Wix columns are their split) · <b>Cash</b> = $300 per unit. A deal with two closers credits
        both; the header totals count each deal once. The main rows are the CURRENT team (DC Setup);
        people deactivated there collapse into the &ldquo;Former reps&rdquo; group, still counted in
        the column totals. Activity from anyone not confirmed on the team is not shown. All rows cover
        DC-ads pool leads only.
      </div>
    </div>
  )
}
