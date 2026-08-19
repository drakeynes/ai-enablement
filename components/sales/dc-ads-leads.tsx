'use client'

import { useMemo, useState } from 'react'

import type { DcAdsLeadRow } from '@/lib/db/dc-ads'

import { FineNote } from './fine-note'

// DC ads — the embedded lead roster (boss 2026-08-14): the Leads page's list
// scoped to DC ad leads, living INSIDE the DC Ads page. Search and the
// toggles narrow the list in place — no navigation, ever. All rows render
// inside one fixed-height scrollable box (header pinned) so the page never
// grows with the cohort.
//
// Toggles are CUMULATIVE (Nabeel 2026-08-14): "Connected" shows every lead
// that connected — including those who went on to close — so the toggle
// counts equal the stage row's numbers. Since the 2026-08-15 boss batch they
// are also STACKABLE, in two groups: stage (SMS/Connected/HVC/Closed) and
// qualification (Qualified/Non-qualified/Partial). Within a group selections
// ADD together (union — Connected + HVC changes nothing, HVC ⊆ Connected);
// across the groups they COMBINE (Qualified + Connected = qualified leads who
// connected). Toggle state lives in the parent wrapper so the speed boxes
// above recompute over the same subset; search stays list-only. Each ROW
// still shows one disposition badge, the lead's furthest stage:
// Closed > HVC > Connected > SMS > Opt-in. Connected = a call ≥90s ONLY
// (0140 — no form fallback, no SMS); HVC = connected AND (qualified OR
// texted us) ⊆ Connected.

const ACCENT = '#b48ead'

export type Disposition = 'closed' | 'hvc' | 'connected' | 'sms' | 'optin'
export type QualKey = DcAdsLeadRow['qualState']

const DISPOSITIONS: { key: Disposition; label: string }[] = [
  { key: 'sms', label: 'SMS' },
  { key: 'connected', label: 'Connected' },
  { key: 'hvc', label: 'HVC' },
  { key: 'closed', label: 'Closed' },
]

const QUAL_TOGGLES: { key: QualKey; label: string }[] = [
  { key: 'qualified', label: 'Qualified' },
  { key: 'unqualified', label: 'Non-qualified' },
  { key: 'partial', label: 'Partial' },
]

// A toggle matches every lead that REACHED that stage (cumulative), so the
// counts line up with the stage row above.
function hasStage(r: DcAdsLeadRow, d: Disposition): boolean {
  return d === 'closed' ? r.closed : d === 'hvc' ? r.hvc : d === 'connected' ? r.connected : d === 'sms' ? r.sms : true
}

// The stacked-toggle predicate — union within a group, AND across the two
// groups; an empty group is no constraint. Shared with the speed-box wrapper
// so the boxes and the list can never disagree on the subset.
export function matchesToggles(
  r: DcAdsLeadRow,
  dispSel: ReadonlySet<Disposition>,
  qualSel: ReadonlySet<QualKey>,
): boolean {
  if (dispSel.size > 0 && !Array.from(dispSel).some((d) => hasStage(r, d))) return false
  if (qualSel.size > 0 && !qualSel.has(r.qualState)) return false
  return true
}

const DISP_LABEL: Record<Disposition, string> = {
  closed: 'Closed',
  hvc: 'HVC',
  connected: 'Connected',
  sms: 'SMS',
  optin: 'Opt-in',
}

function dispositionOf(r: DcAdsLeadRow): Disposition {
  if (r.closed) return 'closed'
  if (r.hvc) return 'hvc'
  if (r.connected) return 'connected'
  if (r.sms) return 'sms'
  return 'optin'
}

// ET "Mon D" for the opt-in stamp.
function fmtAnchor(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    month: 'short',
    day: 'numeric',
  }).format(new Date(iso))
}

// Business-clock seconds (12p–12a ET, same clock as the speed boxes) →
// "45s" / "12m" / "3h 05m" / "—" (never dialed).
function fmtDialTime(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  return `${Math.floor(sec / 3600)}h ${String(Math.floor((sec % 3600) / 60)).padStart(2, '0')}m`
}

// The boss's 3-state vocabulary (0144): Yes = qualified, No = answered the
// question but missed, Partial = never answered it (no completed survey).
const QUAL_LABEL: Record<DcAdsLeadRow['qualState'], string> = {
  qualified: 'Yes',
  unqualified: 'No',
  partial: 'Partial',
}

// Tier sort rank (0154): A first, un-tiered last.
const TIER_RANK: Record<string, number> = { A: 0, B: 1, C: 2, D: 3 }

const SCROLL_MAX_HEIGHT = 480

export function DcAdsLeadsSection({
  rows,
  lpLabels,
  dispSel,
  qualSel,
  onToggleDisp,
  onToggleQual,
}: {
  rows: DcAdsLeadRow[]
  // slug → short display label ('join/training'), from the page's registry read.
  lpLabels: Record<string, string>
  // Stacked toggle state — owned by the parent wrapper (dc-ads-speed-leads)
  // so the speed boxes above recompute over the same subset.
  dispSel: ReadonlySet<Disposition>
  qualSel: ReadonlySet<QualKey>
  onToggleDisp: (d: Disposition) => void
  onToggleQual: (q: QualKey) => void
}) {
  const [query, setQuery] = useState('')
  // Sort by tier (0154): A→D then un-tiered, newest-first within a tier —
  // the dial-priority view. Off = the default newest-first list.
  const [tierSort, setTierSort] = useState(false)

  const withDisposition = useMemo(
    () => rows.map((r) => ({ ...r, disposition: dispositionOf(r) })),
    [rows],
  )

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const qDigits = q.replace(/[^0-9]/g, '')
    const filtered = withDisposition.filter((r) => {
      if (!matchesToggles(r, dispSel, qualSel)) return false
      if (!q) return true
      if (r.name.toLowerCase().includes(q)) return true
      if (r.email && r.email.toLowerCase().includes(q)) return true
      if (qDigits.length >= 3 && r.phone && r.phone.replace(/[^0-9]/g, '').includes(qDigits))
        return true
      return false
    })
    if (!tierSort) return filtered
    // Stable sort: rows arrive newest-first, so equal tiers keep that order.
    return [...filtered].sort(
      (a, b) => (TIER_RANK[a.tier ?? ''] ?? 4) - (TIER_RANK[b.tier ?? ''] ?? 4),
    )
  }, [withDisposition, query, dispSel, qualSel, tierSort])

  const counts = useMemo(() => {
    const c: Record<Disposition, number> = { closed: 0, hvc: 0, connected: 0, sms: 0, optin: 0 }
    const q: Record<QualKey, number> = { qualified: 0, unqualified: 0, partial: 0 }
    for (const r of withDisposition) {
      if (r.sms) c.sms += 1
      if (r.connected) c.connected += 1
      if (r.hvc) c.hvc += 1
      if (r.closed) c.closed += 1
      q[r.qualState] += 1
    }
    return { disp: c, qual: q }
  }, [withDisposition])

  return (
    <div style={{ marginTop: 26 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 10 }}
      >
        Leads · {visible.length === rows.length ? rows.length : `${visible.length} of ${rows.length}`} · selected dates
      </div>

      {/* Filter row — search + disposition toggles. Filtering is fully
          client-side: typing or toggling never navigates. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name, email, or phone…"
          aria-label="Search leads"
          className="geg-mono"
          style={{
            fontSize: 12,
            padding: '7px 11px',
            width: 260,
            borderRadius: 6,
            border: '1px solid var(--color-geg-border)',
            background: 'var(--color-geg-bg-elev)',
            color: 'var(--color-geg-text)',
          }}
        />
        {DISPOSITIONS.map((d) => {
          const active = dispSel.has(d.key)
          return (
            <ToggleButton
              key={d.key}
              label={`${d.label} ${counts.disp[d.key]}`}
              active={active}
              onClick={() => onToggleDisp(d.key)}
            />
          )
        })}
        <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--color-geg-border)' }} />
        {QUAL_TOGGLES.map((t) => {
          const active = qualSel.has(t.key)
          return (
            <ToggleButton
              key={t.key}
              label={`${t.label} ${counts.qual[t.key]}`}
              active={active}
              onClick={() => onToggleQual(t.key)}
            />
          )
        })}
        <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--color-geg-border)' }} />
        <ToggleButton
          label="Sort · Tier"
          active={tierSort}
          onClick={() => setTierSort((s) => !s)}
        />
      </div>

      {/* Mobile (2026-08-15): the phone shows Lead / Qualified / Disposition
          only (the other six columns are desktop-only, `hidden md:block`) so
          the list fits the screen with no sideways scroll; ≥md keeps the full
          nine columns inside the horizontal scroller. */}
      <div style={{ overflowX: 'auto' }}>
      <div className="md:min-w-[900px]">
      {/* Header — outside the vertical scroll box so it stays pinned. */}
      <div
        className={GRID_COLS}
        style={{
          gap: 10,
          padding: '6px 10px 10px',
          borderBottom: '1px solid var(--color-geg-border)',
          scrollbarGutter: 'stable',
          overflowY: 'hidden',
        }}
      >
        <ColH label="Lead" align="left" />
        <ColH label="Opt-in" hideM />
        <ColH label="Landing page" align="left" hideM />
        <ColH label="Dials" hideM />
        <ColH label="Time to dial" hideM />
        <ColH label="Connected" hideM />
        <ColH label="Qualified" />
        <ColH label="Tier" hideM />
        <ColH label="Disposition" />
      </div>

      <div style={{ maxHeight: SCROLL_MAX_HEIGHT, overflowY: 'auto', scrollbarGutter: 'stable' }}>
        {visible.length === 0 ? (
          <div
            className="geg-serif"
            style={{ padding: '22px 0', textAlign: 'center', fontStyle: 'italic', color: 'var(--color-geg-text-3)', fontSize: 14 }}
          >
            No leads match.
          </div>
        ) : (
          visible.map((r) => (
            <div
              key={r.closeId}
              className={GRID_COLS}
              style={{
                gap: 10,
                padding: '9px 10px',
                borderBottom: '1px dashed var(--color-geg-border)',
                alignItems: 'baseline',
              }}
            >
              <span style={{ minWidth: 0 }}>
                {/* → the lead's CLOSE profile (boss 2026-08-18: reps live in
                    Close — the in-app lifecycle page lost its link, still
                    reachable by URL). */}
                <a
                  href={`https://app.close.com/lead/${encodeURIComponent(r.closeId)}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="geg-serif"
                  style={{ display: 'block', fontSize: 13.5, color: 'var(--color-geg-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textDecoration: 'none' }}
                  onMouseEnter={(e) => { e.currentTarget.style.textDecoration = 'underline' }}
                  onMouseLeave={(e) => { e.currentTarget.style.textDecoration = 'none' }}
                >
                  {r.name}
                </a>
                <span
                  className="geg-mono"
                  style={{ display: 'block', fontSize: 9.5, color: 'var(--color-geg-text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                >
                  {[r.phone, r.email].filter(Boolean).join(' · ') || '—'}
                </span>
              </span>
              <Num value={fmtAnchor(r.anchor)} hideM />
              <span className="geg-mono hidden md:block" style={{ fontSize: 10.5, color: 'var(--color-geg-text-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.lpSlug ? (lpLabels[r.lpSlug] ?? r.lpSlug) : '—'}
              </span>
              <Num value={r.dials.toLocaleString('en-US')} hideM />
              <Num value={fmtDialTime(r.timeToDialSec)} hideM />
              <Num value={r.connected ? 'Yes' : '—'} hideM />
              <span
                className="geg-numeric-serif"
                style={{
                  fontSize: 13,
                  textAlign: 'right',
                  whiteSpace: 'nowrap',
                  color:
                    r.qualState === 'qualified'
                      ? 'var(--color-geg-text)'
                      : r.qualState === 'unqualified'
                        ? 'var(--color-geg-text-2)'
                        : 'var(--color-geg-text-faint)',
                  fontStyle: r.qualState === 'partial' ? 'italic' : 'normal',
                }}
              >
                {QUAL_LABEL[r.qualState]}
              </span>
              <span className="hidden md:block" style={{ textAlign: 'right' }}>
                <TierBadge tier={r.tier} />
              </span>
              <span style={{ textAlign: 'right' }}>
                <DispositionBadge d={r.disposition} />
              </span>
            </div>
          ))
        )}
      </div>
      </div>
      </div>

      <FineNote style={{ marginTop: 10 }}>
        Every DC ad lead in the selected dates (follows the campaign chooser + landing-page dropdown).
        Search and the toggles narrow this list in place — they never leave the page. Toggles are{' '}
        <b>cumulative</b> (each shows every lead that reached that stage, so the counts match the
        stage row above) and <b>stackable</b>: within a group (stage · qualification) selections add
        together; across the groups they combine — e.g. Qualified + Connected = qualified leads who
        connected. The speed boxes above follow the toggles too (search stays list-only). The badge on each row is the
        lead&apos;s furthest stage. <b>Time to dial</b> = opt-in → first outbound call on the same
        12p–12a ET clock as the speed boxes (— = never dialed) · <b>SMS</b> = texted us back ·{' '}
        <b>Connected</b> = a <b>call ≥90s only</b> — no form or text evidence counts ·{' '}
        <b>Qualified</b>: Yes = their Typeform answered &ldquo;Yes I can pay for the AI tools&rdquo;;
        No = they answered the question but not with that; <i>Partial</i> = they never answered it
        (no completed survey) · <b>Tier</b> = the two Typeform answers combined (can-pay × AI
        experience): <b>A</b> = can pay + has used AI beyond dabbling · <b>B</b> = can pay +
        ChatGPT dabbler · <b>C</b> = can&apos;t pay + experienced · <b>D</b> = can&apos;t pay +
        dabbler · — = the survey never produced both answers. Historical close rates run ~8% (A)
        down to ~1% (D) — <b>Sort · Tier</b> puts the A leads first, newest first within a tier ·{' '}
        <b>HVC</b> = connected <i>and</i> (qualified or
        texted us) · <b>Closed</b> = DC close with a plan · Opt-in = none of those yet.
      </FineNote>
    </div>
  )
}

// Responsive grid template (mobile 2026-08-15): three columns on a phone
// (Lead / Qualified / Disposition — the hidden cells don't occupy tracks),
// the full nine (Tier added 0154) from md up. Template lives in classes
// because inline styles can't carry media queries.
const GRID_COLS =
  'grid grid-cols-[minmax(0,1.7fr)_0.6fr_0.9fr] md:grid-cols-[minmax(180px,1.6fr)_0.6fr_minmax(110px,1fr)_0.5fr_0.65fr_0.6fr_0.6fr_0.4fr_0.8fr]'

function ToggleButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="geg-mono"
      style={{
        fontSize: 10.5,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        padding: '6px 12px',
        borderRadius: 6,
        cursor: 'pointer',
        border: `1px solid ${active ? ACCENT : 'var(--color-geg-border)'}`,
        background: active ? ACCENT : 'var(--color-geg-bg-elev)',
        color: active ? '#fff' : 'var(--color-geg-text-2)',
      }}
    >
      {label}
    </button>
  )
}

// Typeform lead tier (0154): A stands out (dial these first), D reads muted,
// un-tiered is a plain dash — the survey never produced both answers.
function TierBadge({ tier }: { tier: DcAdsLeadRow['tier'] }) {
  if (!tier) {
    return (
      <span className="geg-mono" style={{ fontSize: 10, color: 'var(--color-geg-text-faint)' }}>
        —
      </span>
    )
  }
  const strong = tier === 'A'
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 9.5,
        letterSpacing: '0.07em',
        padding: '2px 7px',
        borderRadius: 4,
        border: `1px solid ${strong ? ACCENT : 'var(--color-geg-border)'}`,
        color: strong ? ACCENT : tier === 'D' ? 'var(--color-geg-text-faint)' : 'var(--color-geg-text-2)',
      }}
    >
      {tier}
    </span>
  )
}

function DispositionBadge({ d }: { d: Disposition }) {
  const strong = d === 'closed' || d === 'hvc'
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 9.5,
        letterSpacing: '0.07em',
        textTransform: 'uppercase',
        padding: '2px 8px',
        borderRadius: 4,
        border: `1px solid ${strong ? ACCENT : 'var(--color-geg-border)'}`,
        color: d === 'optin' ? 'var(--color-geg-text-faint)' : strong ? ACCENT : 'var(--color-geg-text-2)',
      }}
    >
      {DISP_LABEL[d]}
    </span>
  )
}

function ColH({ label, align, hideM }: { label: string; align?: 'left' | 'right'; hideM?: boolean }) {
  return (
    <span
      className={hideM ? 'geg-mono hidden md:block' : 'geg-mono'}
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

function Num({ value, hideM }: { value: string; hideM?: boolean }) {
  return (
    <span
      className={hideM ? 'geg-numeric-serif hidden md:block' : 'geg-numeric-serif'}
      style={{ fontSize: 13, color: 'var(--color-geg-text-2)', textAlign: 'right', whiteSpace: 'nowrap' }}
    >
      {value}
    </span>
  )
}
