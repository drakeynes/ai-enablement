'use client'

import { useMemo, useState } from 'react'

import type { DcAdsLeadRow } from '@/lib/db/dc-ads'

// DC ads — the embedded lead roster (boss 2026-08-14): the Leads page's list
// scoped to DC ad leads, living INSIDE the DC Ads page. Search and the stage
// toggles narrow the list in place — no navigation, ever. All rows render
// inside one fixed-height scrollable box (header pinned) so the page never
// grows with the cohort.
//
// Toggles are CUMULATIVE (Nabeel 2026-08-14): "Connected" shows every lead
// that connected — including those who went on to close — so the toggle
// counts equal the stage row's numbers. Each ROW still shows one disposition
// badge, the lead's furthest stage: Closed > HVC > Connected > SMS > Opt-in.
// Connected = a call ≥90s ONLY (0140 — no form fallback, no SMS);
// HVC = connected AND (qualified OR texted us) ⊆ Connected.

const ACCENT = '#b48ead'

type Disposition = 'closed' | 'hvc' | 'connected' | 'sms' | 'optin'

const DISPOSITIONS: { key: Disposition; label: string }[] = [
  { key: 'sms', label: 'SMS' },
  { key: 'connected', label: 'Connected' },
  { key: 'hvc', label: 'HVC' },
  { key: 'closed', label: 'Closed' },
]

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

const SCROLL_MAX_HEIGHT = 480

export function DcAdsLeadsSection({
  rows,
  lpLabels,
}: {
  rows: DcAdsLeadRow[]
  // slug → short display label ('join/training'), from the page's registry read.
  lpLabels: Record<string, string>
}) {
  const [query, setQuery] = useState('')
  const [disp, setDisp] = useState<Disposition | null>(null)

  const withDisposition = useMemo(
    () => rows.map((r) => ({ ...r, disposition: dispositionOf(r) })),
    [rows],
  )

  // A toggle matches every lead that REACHED that stage (cumulative), so the
  // counts line up with the stage row above.
  const hasStage = (r: DcAdsLeadRow, d: Disposition): boolean =>
    d === 'closed' ? r.closed : d === 'hvc' ? r.hvc : d === 'connected' ? r.connected : d === 'sms' ? r.sms : true

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const qDigits = q.replace(/[^0-9]/g, '')
    return withDisposition.filter((r) => {
      if (disp && !hasStage(r, disp)) return false
      if (!q) return true
      if (r.name.toLowerCase().includes(q)) return true
      if (r.email && r.email.toLowerCase().includes(q)) return true
      if (qDigits.length >= 3 && r.phone && r.phone.replace(/[^0-9]/g, '').includes(qDigits))
        return true
      return false
    })
  }, [withDisposition, query, disp])

  const counts = useMemo(() => {
    const c: Record<Disposition, number> = { closed: 0, hvc: 0, connected: 0, sms: 0, optin: 0 }
    for (const r of withDisposition) {
      if (r.sms) c.sms += 1
      if (r.connected) c.connected += 1
      if (r.hvc) c.hvc += 1
      if (r.closed) c.closed += 1
    }
    return c
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
          const active = disp === d.key
          return (
            <button
              key={d.key}
              type="button"
              onClick={() => setDisp(active ? null : d.key)}
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
              {d.label} {counts[d.key]}
            </button>
          )
        })}
      </div>

      {/* Header — outside the scroll box so it stays pinned. */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: COLS,
          gap: 10,
          padding: '6px 10px 10px',
          borderBottom: '1px solid var(--color-geg-border)',
          scrollbarGutter: 'stable',
          overflowY: 'hidden',
        }}
      >
        <ColH label="Lead" align="left" />
        <ColH label="Opt-in" />
        <ColH label="Landing page" align="left" />
        <ColH label="Dials" />
        <ColH label="Qualified" />
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
              style={{
                display: 'grid',
                gridTemplateColumns: COLS,
                gap: 10,
                padding: '9px 10px',
                borderBottom: '1px dashed var(--color-geg-border)',
                alignItems: 'baseline',
              }}
            >
              <span style={{ minWidth: 0 }}>
                <span
                  className="geg-serif"
                  style={{ display: 'block', fontSize: 13.5, color: 'var(--color-geg-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                >
                  {r.name}
                </span>
                <span
                  className="geg-mono"
                  style={{ display: 'block', fontSize: 9.5, color: 'var(--color-geg-text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                >
                  {[r.phone, r.email].filter(Boolean).join(' · ') || '—'}
                </span>
              </span>
              <Num value={fmtAnchor(r.anchor)} />
              <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.lpSlug ? (lpLabels[r.lpSlug] ?? r.lpSlug) : '—'}
              </span>
              <Num value={r.dials.toLocaleString('en-US')} />
              <Num value={r.qualified ? 'Yes' : '—'} />
              <span style={{ textAlign: 'right' }}>
                <DispositionBadge d={r.disposition} />
              </span>
            </div>
          ))
        )}
      </div>

      <div
        className="geg-mono"
        style={{ marginTop: 10, fontSize: 9, letterSpacing: '0.05em', color: 'var(--color-geg-text-faint)', lineHeight: 1.7 }}
      >
        Every DC ad lead in the selected dates (follows the campaign chooser + landing-page dropdown).
        Search and the toggles narrow this list in place — they never leave the page. Toggles are{' '}
        <b>cumulative</b>: each shows every lead that reached that stage (a closed lead appears under
        all of its stages), so the counts match the stage row above. The badge on each row is the
        lead&apos;s furthest stage. <b>SMS</b> = texted us back · <b>Connected</b> = a <b>call ≥90s
        only</b> — no form or text evidence counts · <b>HVC</b> = connected <i>and</i> (qualified or
        texted us) · <b>Closed</b> = DC close with a plan · Opt-in = none of those yet.
      </div>
    </div>
  )
}

const COLS = 'minmax(180px, 1.6fr) 0.6fr minmax(110px, 1fr) 0.5fr 0.6fr 0.8fr'

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

function Num({ value }: { value: string }) {
  return (
    <span
      className="geg-numeric-serif"
      style={{ fontSize: 13, color: 'var(--color-geg-text-2)', textAlign: 'right', whiteSpace: 'nowrap' }}
    >
      {value}
    </span>
  )
}
