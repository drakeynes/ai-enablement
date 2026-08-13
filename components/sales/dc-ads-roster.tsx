'use client'

import { useMemo, useState } from 'react'

import type { DcAdsRepRow } from '@/lib/db/dc-ads'
import type { DcTeamMember } from '@/lib/db/dc-setup'

// DC ads roster — the Talent Roster's card grid scoped to the DC ad cohort
// (boss item 8, 2026-08-13). One card per human: every ACTIVE team member
// (zero-activity cards included — a new hire shows before their first dial)
// merged with the window's per-rep activity rows. A "Show inactive" toggle
// reveals offboarded people who still had window activity. Rows the identity
// bridge can't attach to a team member yet render as their own card with a
// NOT LINKED tag — the cue to link them in DC Setup.

const ACCENT = '#b48ead' // purple — the DC accent

type Card = {
  key: string
  name: string
  role: string | null
  active: boolean
  linked: boolean
  dials: number
  connections: number
  shows: number
  closes: number
  units: number
  cash: number
}

const ROLE_LABEL: Record<string, string> = {
  setter: 'Setter',
  closer: 'Closer',
  dc_closer: 'DC Closer',
}

function buildCards(team: DcTeamMember[], reps: DcAdsRepRow[]): Card[] {
  const byTm = new Map<string, DcAdsRepRow[]>()
  const unlinked: DcAdsRepRow[] = []
  for (const r of reps) {
    if (r.teamMemberId) byTm.set(r.teamMemberId, [...(byTm.get(r.teamMemberId) ?? []), r])
    else unlinked.push(r)
  }
  const zero = { dials: 0, connections: 0, shows: 0, closes: 0, units: 0, cash: 0 }
  const sum = (rows: DcAdsRepRow[]) =>
    rows.reduce(
      (a, r) => ({
        dials: a.dials + r.dials,
        connections: a.connections + r.connections,
        shows: a.shows + r.shows,
        closes: a.closes + r.closes,
        units: a.units + r.units,
        cash: a.cash + r.cash,
      }),
      { ...zero },
    )

  const cards: Card[] = team.map((m) => ({
    key: m.id,
    name: m.fullName,
    role: m.salesRole ? (ROLE_LABEL[m.salesRole] ?? m.salesRole) : null,
    active: m.isActive,
    linked: true,
    ...sum(byTm.get(m.id) ?? []),
  }))
  for (const r of unlinked) {
    cards.push({
      key: `raw:${r.rep}`,
      name: r.rep,
      role: null,
      active: true,
      linked: false,
      dials: r.dials,
      connections: r.connections,
      shows: r.shows,
      closes: r.closes,
      units: r.units,
      cash: r.cash,
    })
  }
  const score = (c: Card) => c.dials + c.connections + 5 * c.shows + 10 * c.closes
  return cards.sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1
    return score(b) - score(a) || a.name.localeCompare(b.name)
  })
}

export function DcAdsRosterSection({ team, reps }: { team: DcTeamMember[]; reps: DcAdsRepRow[] }) {
  const [showInactive, setShowInactive] = useState(false)
  const cards = useMemo(() => buildCards(team, reps), [team, reps])
  // Inactive cards hide by default UNLESS they still had window activity worth
  // seeing? No — hidden entirely; the toggle reveals them (Talent Roster rule).
  const visible = cards.filter((c) => c.active || showInactive)
  const inactiveCount = cards.filter((c) => !c.active).length

  return (
    <div style={{ marginTop: 26 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
        <span
          className="geg-mono"
          style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}
        >
          Roster · DC ad activity · selected dates
        </span>
        {inactiveCount > 0 ? (
          <button
            type="button"
            onClick={() => setShowInactive((v) => !v)}
            className="geg-mono"
            style={{
              fontSize: 10,
              letterSpacing: '0.08em',
              color: 'var(--color-geg-text-faint)',
              background: 'none',
              border: '1px solid var(--color-geg-border)',
              borderRadius: 4,
              padding: '2px 8px',
              cursor: 'pointer',
            }}
          >
            {showInactive ? 'Hide' : 'Show'} inactive ({inactiveCount})
          </button>
        ) : null}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
          gridAutoRows: '1fr',
          gap: 10,
        }}
      >
        {visible.map((c) => (
          <RepCard key={c.key} card={c} />
        ))}
      </div>

      <div
        className="geg-mono"
        style={{ marginTop: 10, fontSize: 9, letterSpacing: '0.05em', color: 'var(--color-geg-text-faint)', lineHeight: 1.7 }}
      >
        One card per person on the team (managed in DC Setup — new hires appear once verified, leavers
        once deactivated), stats = their DC-ad activity in the selected dates. A card with no team link
        means the person&apos;s identities aren&apos;t connected yet; until then their dialing and closing
        can show as two cards.
      </div>
    </div>
  )
}

function RepCard({ card: c }: { card: Card }) {
  const initials = c.name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <div
      style={{
        border: '1px solid var(--color-geg-border)',
        background: 'var(--color-geg-bg-elev)',
        borderRadius: 10,
        padding: '14px 16px',
        opacity: c.active ? 1 : 0.65,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span
          className="geg-mono"
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 11,
            letterSpacing: '0.04em',
            color: 'var(--color-geg-text)',
            background: 'var(--color-geg-bg)',
            border: `1px solid ${c.closes > 0 ? ACCENT : 'var(--color-geg-border)'}`,
            flexShrink: 0,
          }}
        >
          {initials || '?'}
        </span>
        <span style={{ minWidth: 0 }}>
          <span
            className="geg-serif"
            style={{ display: 'block', fontSize: 14.5, color: 'var(--color-geg-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
          >
            {c.name}
          </span>
          <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}>
            {c.role ?? (c.linked ? '—' : 'not linked')}
            {!c.active ? ' · inactive' : ''}
          </span>
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
        <Stat label="Dials" value={c.dials.toLocaleString('en-US')} />
        <Stat label="Connects" value={c.connections.toLocaleString('en-US')} />
        <Stat label="Shows" value={c.shows.toLocaleString('en-US')} />
        <Stat label="Closes" value={c.closes.toLocaleString('en-US')} accent={c.closes > 0} />
        <Stat label="Units" value={c.units.toLocaleString('en-US')} />
        <Stat label="Cash" value={`$${c.cash.toLocaleString('en-US')}`} accent={c.cash > 0} />
      </div>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <span>
      <span
        className="geg-numeric-serif"
        style={{ display: 'block', fontSize: 16, lineHeight: 1.1, color: value === '0' || value === '$0' ? 'var(--color-geg-text-faint)' : accent ? ACCENT : 'var(--color-geg-text)' }}
      >
        {value}
      </span>
      <span className="geg-mono" style={{ fontSize: 8.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}>
        {label}
      </span>
    </span>
  )
}
