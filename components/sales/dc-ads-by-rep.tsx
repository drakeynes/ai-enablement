'use client'

// Client component since the EOD dropdown (boss batch 2026-08-15): clicking a
// rep name expands their in-window EOD reports inline. Everything else is
// unchanged presentational rendering.

import { Fragment, useState } from 'react'

import type { DcAdsRepRow, DcAdsRepTotals } from '@/lib/db/dc-ads'
import type { RepEod } from '@/lib/db/funnel-eods'
import { EodCard } from './eod-card'
import { FineNote } from './fine-note'

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
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
  if (sec >= 60) return `${Math.round(sec / 60)}m`
  return `${sec}s`
}

// `m` = shown on mobile too (Rep, Dials, Connections, Closes, Cash); the
// talk-time/units/plan-split columns are desktop-only (mobile 2026-08-15).
function Cell({ value, strong = false, muted = false, m = false }: { value: string; strong?: boolean; muted?: boolean; m?: boolean }) {
  return (
    <td
      className={m ? 'geg-numeric-serif' : 'geg-numeric-serif hidden md:table-cell'}
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

// Close-rate cell (0157): percent + the raw fraction beside it — rep-level n
// is small, so the counts carry the meaning. Denominators are DISTINCT leads
// connected (not the per-call Connections column). Desktop-only.
function RateCell({ n, d, muted = false }: { n: number; d: number; muted?: boolean }) {
  return (
    <td
      className="geg-numeric-serif hidden md:table-cell"
      style={{ padding: '9px 14px', textAlign: 'right', fontSize: 14, whiteSpace: 'nowrap' }}
    >
      <span style={{ color: d > 0 && !muted ? 'var(--color-geg-text)' : 'var(--color-geg-text-faint)' }}>
        {d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '—'}
      </span>
      <span style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)', marginLeft: 6 }}>
        {n}/{d}
      </span>
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

// Column count for the expanded EOD row's colSpan — keep in sync with the
// header row below.
const COL_COUNT = 15

function RepTr({
  r,
  faded = false,
  eods,
  expanded = false,
  onToggle,
}: {
  r: DcAdsRepRow
  faded?: boolean
  // The rep's in-window EOD reports (undefined = rep not linked, no dropdown).
  eods?: RepEod[]
  expanded?: boolean
  onToggle?: () => void
}) {
  return (
    <tr style={{ borderBottom: expanded ? 'none' : '1px solid var(--color-geg-border)', opacity: faded ? 0.65 : 1 }}>
      <td className="geg-mono" style={{ padding: '9px 14px', fontSize: 12, letterSpacing: '0.02em', color: 'var(--color-geg-text)', whiteSpace: 'nowrap' }}>
        {onToggle ? (
          <button
            type="button"
            onClick={onToggle}
            title="Show this rep's EOD reports for the selected dates"
            className="geg-mono"
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              fontSize: 12,
              letterSpacing: '0.02em',
              color: 'var(--color-geg-text)',
              display: 'inline-flex',
              alignItems: 'baseline',
              gap: 6,
            }}
          >
            <span style={{ color: 'var(--color-geg-text-faint)', fontSize: 9 }}>{expanded ? '▾' : '▸'}</span>
            {r.rep}
            <span style={{ fontSize: 9, letterSpacing: '0.05em', color: eods?.length ? 'var(--color-geg-text-3)' : 'var(--color-geg-text-faint)' }}>
              {eods?.length ? `${eods.length} EOD${eods.length > 1 ? 's' : ''}` : ''}
            </span>
          </button>
        ) : (
          r.rep
        )}
      </td>
      <Cell value={r.dials.toLocaleString('en-US')} m />
      <Cell value={r.connections.toLocaleString('en-US')} m />
      <Cell value={fmtTalk(r.talkSeconds ?? 0)} muted={!r.talkSeconds} />
      <Cell value={r.aiRepScore != null ? r.aiRepScore.toFixed(1) : '—'} muted={!r.aiRepN} />
      <Cell value={r.closes.toLocaleString('en-US')} strong m />
      {/* The close-rate trio (user 2026-08-22, 0157): closes ÷ distinct leads
          connected. NonQ includes partial-survey leads, so Q + NonQ fractions
          sum to the global one. */}
      <RateCell n={r.closes} d={r.leadsConnected} />
      <RateCell n={r.qualifiedClosed} d={r.qualifiedConnected} />
      <RateCell n={r.unqualifiedClosed} d={r.unqualifiedConnected} />
      <Cell value={r.units.toLocaleString('en-US')} />
      <Cell value={r.base44Monthly.toLocaleString('en-US')} muted={r.base44Monthly === 0} />
      <Cell value={r.base44Yearly.toLocaleString('en-US')} muted={r.base44Yearly === 0} />
      <Cell value={r.wixMonthly.toLocaleString('en-US')} muted={r.wixMonthly === 0} />
      <Cell value={r.wixYearly.toLocaleString('en-US')} muted={r.wixYearly === 0} />
      <Cell value={fmtCash(r.cash)} strong m />
    </tr>
  )
}

// The expanded dropdown under a rep row — their EOD reports for the window.
function EodExpandRow({ eods }: { eods: RepEod[] }) {
  return (
    <tr style={{ borderBottom: '1px solid var(--color-geg-border)' }}>
      <td colSpan={COL_COUNT} style={{ padding: '2px 14px 14px 32px' }}>
        {eods.length === 0 ? (
          <div
            className="geg-mono"
            style={{ fontSize: 10, letterSpacing: '0.04em', color: 'var(--color-geg-text-faint)', padding: '4px 0' }}
          >
            No EOD reports filed in the selected dates.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 760 }}>
            {eods.map((e) => (
              <EodCard key={e.recordId} eod={e} />
            ))}
          </div>
        )}
      </td>
    </tr>
  )
}

function HeadCell({ label, first = false, m = false }: { label: string; first?: boolean; m?: boolean }) {
  return (
    <th
      className={m || first ? 'geg-mono' : 'geg-mono hidden md:table-cell'}
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
  eodsByTeamMemberId,
}: {
  rows: DcAdsRepRow[]
  totals: DcAdsRepTotals
  // team_members ids of the ACTIVE sales roster (DC Setup). Rows of CONFIRMED
  // former members collapse into a "former reps" group so the table reads as
  // the current team (boss 2026-08-14); activity from identities with NO team
  // row at all is not rendered — membership is controlled via the Airtable
  // Sales Team Member table → DC Setup verify (Drake 2026-08-14).
  activeTeamMemberIds: string[]
  // In-window EOD reports keyed by team_members.id (boss batch 2026-08-15) —
  // clicking a rep name expands them inline. Everyone files the SETTER EOD
  // form since the DC pivot (setter/closer roles merged), so most cards say
  // "setter EOD" regardless of who filed them.
  eodsByTeamMemberId: Record<string, RepEod[]>
}) {
  const [openRep, setOpenRep] = useState<string | null>(null)
  const activeIds = new Set(activeTeamMemberIds)
  const confirmed = rows.filter((r) => r.teamMemberId)
  const current = confirmed.filter((r) => activeIds.has(r.teamMemberId as string))
  const former = confirmed.filter((r) => !activeIds.has(r.teamMemberId as string))
  const colTotals = confirmed.reduce(
    (a, r) => ({
      dials: a.dials + r.dials,
      connections: a.connections + r.connections,
      talkSeconds: a.talkSeconds + (r.talkSeconds ?? 0),
      aiScoreSum: a.aiScoreSum + (r.aiRepScore ?? 0) * (r.aiRepN ?? 0),
      aiN: a.aiN + (r.aiRepN ?? 0),
      closes: a.closes + r.closes,
      leadsConnected: a.leadsConnected + r.leadsConnected,
      qualifiedConnected: a.qualifiedConnected + r.qualifiedConnected,
      unqualifiedConnected: a.unqualifiedConnected + r.unqualifiedConnected,
      qualifiedClosed: a.qualifiedClosed + r.qualifiedClosed,
      unqualifiedClosed: a.unqualifiedClosed + r.unqualifiedClosed,
      units: a.units + r.units,
      cash: a.cash + r.cash,
    }),
    {
      dials: 0,
      connections: 0,
      talkSeconds: 0,
      aiScoreSum: 0,
      aiN: 0,
      closes: 0,
      leadsConnected: 0,
      qualifiedConnected: 0,
      unqualifiedConnected: 0,
      qualifiedClosed: 0,
      unqualifiedClosed: 0,
      units: 0,
      cash: 0,
    },
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
                <HeadCell label="Dials" m />
                <HeadCell label="Connections" m />
                <HeadCell label="Talk time" />
                <HeadCell label="AI Rep" />
                <HeadCell label="Closes" m />
                <HeadCell label="Close rate" />
                <HeadCell label="Q close rate" />
                <HeadCell label="NonQ close rate" />
                <HeadCell label="Units" />
                <HeadCell label="B44·Mo" />
                <HeadCell label="B44·Yr" />
                <HeadCell label="Wix·Mo" />
                <HeadCell label="Wix·Yr" />
                <HeadCell label="Cash" m />
              </tr>
            </thead>
            <tbody>
              {current.map((r) => {
                const key = r.teamMemberId ?? r.rep
                const eods = r.teamMemberId ? (eodsByTeamMemberId[r.teamMemberId] ?? []) : undefined
                const expanded = openRep === key
                return (
                  <Fragment key={key}>
                    <RepTr
                      r={r}
                      eods={eods}
                      expanded={expanded}
                      onToggle={r.teamMemberId ? () => setOpenRep(expanded ? null : key) : undefined}
                    />
                    {expanded ? <EodExpandRow eods={eods ?? []} /> : null}
                  </Fragment>
                )
              })}
              {/* totals — cover EVERYONE incl. the former group below */}
              <tr style={{ background: 'var(--color-geg-bg-elev)' }}>
                <td className="geg-mono" style={{ padding: '9px 14px', fontSize: 9.5, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', whiteSpace: 'nowrap' }}>
                  Total{former.length > 0 ? ' (incl. former)' : ''}
                </td>
                <Cell value={colTotals.dials.toLocaleString('en-US')} muted m />
                <Cell value={colTotals.connections.toLocaleString('en-US')} muted m />
                <Cell value={fmtTalk(colTotals.talkSeconds)} muted />
                <Cell
                  value={colTotals.aiN > 0 ? (colTotals.aiScoreSum / colTotals.aiN).toFixed(1) : '—'}
                  muted
                />
                <Cell value={colTotals.closes.toLocaleString('en-US')} strong m />
                <RateCell n={colTotals.closes} d={colTotals.leadsConnected} muted />
                <RateCell n={colTotals.qualifiedClosed} d={colTotals.qualifiedConnected} muted />
                <RateCell n={colTotals.unqualifiedClosed} d={colTotals.unqualifiedConnected} muted />
                <Cell value={colTotals.units.toLocaleString('en-US')} strong />
                <Cell value={totals.base44Monthly.toLocaleString('en-US')} muted />
                <Cell value={totals.base44Yearly.toLocaleString('en-US')} muted />
                <Cell value={totals.wixMonthly.toLocaleString('en-US')} muted />
                <Cell value={totals.wixYearly.toLocaleString('en-US')} muted />
                <Cell value={fmtCash(colTotals.cash)} strong m />
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
                  {former.map((r) => {
                    const key = r.teamMemberId ?? r.rep
                    const eods = r.teamMemberId ? (eodsByTeamMemberId[r.teamMemberId] ?? []) : undefined
                    const expanded = openRep === key
                    return (
                      <Fragment key={key}>
                        <RepTr
                          r={r}
                          faded
                          eods={eods}
                          expanded={expanded}
                          onToggle={r.teamMemberId ? () => setOpenRep(expanded ? null : key) : undefined}
                        />
                        {expanded ? <EodExpandRow eods={eods ?? []} /> : null}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </details>
          ) : null}
        </div>
      )}

      {/* footnote */}
      <FineNote style={{ padding: '9px 14px', background: 'var(--color-geg-bg-elev)', borderTop: '1px solid var(--color-geg-border)' }}>
        Activity-scoped, not cohort-scoped: what each rep did in the selected dates, regardless of when the
        lead opted in. <b>Dials</b> = outbound calls · <b>Connections</b> = calls ≥90s, counted per CALL
        (a lead reached twice counts twice; inbound pickups count) — so the column sum runs higher than the
        funnel&apos;s Connected, which counts each <i>lead</i> once · <b>Talk time</b> = total time on the
        phone (sum of call durations, all calls both directions) · <b>AI Rep</b> = the rep&apos;s average
        AI execution score (0–10) over their reviewed calls in the window — per call, from the call
        reviews (scored from 2026-08-18; a dash = no reviewed calls yet, not a zero)
        · <b>Closes</b> = DC closes with a plan · <b>Close rate</b> = the rep&apos;s closes ÷ the
        <i> distinct leads</i> they connected with (a lead counts once however many calls it took —
        so the denominator runs lower than Connections) · <b>Q / NonQ close rate</b> = the same
        rate split by the lead&apos;s survey qualification — a lead with no completed survey counts
        as non-qualified, so the Q and NonQ fractions add up to the global one. A close credits the
        closer form&apos;s reps while connects come from calls, so a rate can top 100% on small
        numbers — read the fraction beside each percent. · <b>Units</b> = plan units
        (the B44/Wix columns are their split) · <b>Cash</b> = $300 per unit. A deal with two closers credits
        both; the header totals count each deal once. The main rows are the CURRENT team (DC Setup);
        people deactivated there collapse into the &ldquo;Former reps&rdquo; group, still counted in
        the column totals. Activity from anyone not confirmed on the team is not shown. All rows cover
        DC-ads pool leads only. Click a rep name to see their <b>EOD reports</b> for the selected dates
        (everyone files the setter EOD form since the DC pivot).
      </FineNote>
    </div>
  )
}
