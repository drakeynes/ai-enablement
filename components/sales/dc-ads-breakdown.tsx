'use client'

// DC Ads header — the "Data breakdown" button + popover (migration 0149).
//
// Pre-answers the recurring validation question: a hand pull in Close with
// the date filter (created OR latest-opt-in in window) reads HIGHER on leads
// than the page — membership — and its same-day activity filters read LOWER
// on SMS/Connects/HVC — time basis. The popover shows the full Close-style
// reference count vs what the funnel counts, names every gap lead with the
// reason it isn't counted (grouped, Close-linked), and carries the
// cohort-scope note for the stage metrics. Always the org-wide, whole-window
// view — the cascade/LP facets don't apply (a hand pull has no facets).

import { useEffect, useRef, useState } from 'react'
import type { DcAdsBreakdown, DcAdsBreakdownLead } from '@/lib/db/dc-ads'

// Display order = most interesting first; not_ad_lead last (on wide windows
// it is the rest of Close — imports, outbound pools, manual adds).
const REASONS: Array<{ code: string; label: string; hint: string }> = [
  {
    code: 'stale_campaign',
    label: 'Stale ad tag',
    hint: 'Re-opted through an ad whose campaign is not in the DC registry — an ad lead we cannot attribute.',
  },
  {
    code: 'pre_floor_reopt',
    label: 'Re-opt of a pre-July lead',
    hint: 'Campaign-less re-opt whose original Close lead predates the Jul 1 floor, so the Non-attributed branch does not admit it.',
  },
  {
    code: 'inactive_campaign',
    label: 'Retired campaign',
    hint: 'Tagged to a campaign deactivated in DC Setup (e.g. the instant-form era) — excluded on purpose.',
  },
  {
    code: 'no_optin_stamp',
    label: 'No opt-in stamp',
    hint: 'Campaign-less and never bridge-stamped with an opt-in time — cannot be tied to a DC form submit.',
  },
  {
    code: 'manually_excluded',
    label: 'Manually excluded',
    hint: 'Excluded from analytics in our mirror (test/duplicate cleanup).',
  },
  {
    code: 'non_attributed_off',
    label: 'Non-attributed switched off',
    hint: 'The Non-attributed registry row is deactivated (the DC Setup kill switch).',
  },
  {
    code: 'pending_refresh',
    label: 'Awaiting refresh',
    hint: 'Meets membership — appears at the next facts refresh (≤15 min).',
  },
  {
    code: 'not_ad_lead',
    label: 'Not an ad lead',
    hint: 'No DC funnel tag — the rest of Close: imports, outbound pools, manual adds.',
  },
]

// YYYY-MM-DD (ET) → "Aug 17".
function monthDay(ymd: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })
    .format(new Date(`${ymd}T12:00:00Z`))
}

function MqBadge() {
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 8,
        letterSpacing: '0.08em',
        padding: '1px 4px',
        borderRadius: 3,
        border: '1px solid var(--color-geg-pos)',
        color: 'var(--color-geg-pos)',
      }}
      title="Marketing qualified in Close"
    >
      MQ
    </span>
  )
}

function LeadLine({
  closeId,
  name,
  day,
  mq,
}: {
  closeId: string
  name: string
  day: string
  mq: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, lineHeight: 1.9 }}>
      <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 44 }}>{monthDay(day)}</span>
      <a
        href={`https://app.close.com/lead/${closeId}/`}
        target="_blank"
        rel="noreferrer"
        style={{ color: 'var(--color-geg-text-2)', textDecoration: 'underline', textUnderlineOffset: 2 }}
      >
        {name}
      </a>
      {mq ? <MqBadge /> : null}
    </div>
  )
}

export function DcAdsBreakdownButton({
  data,
  startEtDate,
  endEtDate,
}: {
  data: DcAdsBreakdown
  startEtDate: string
  endEtDate: string
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const byReason = new Map<string, DcAdsBreakdownLead[]>()
  for (const lead of data.excluded) {
    const list = byReason.get(lead.reason) ?? []
    list.push(lead)
    byReason.set(lead.reason, list)
  }
  const knownCodes = new Set(REASONS.map((r) => r.code))
  const extraCodes = Object.keys(data.excludedByReason).filter((c) => !knownCodes.has(c))

  const groups = [
    ...REASONS,
    ...extraCodes.map((code) => ({ code, label: code, hint: '' })),
  ].filter((r) => (data.excludedByReason[r.code] ?? 0) > 0)

  const sectionTitle: React.CSSProperties = {
    fontSize: 9,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    color: 'var(--color-geg-text-3)',
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="geg-mono"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 12px',
          background: open ? 'var(--color-geg-bg-elev)' : 'transparent',
          border: '1px solid var(--color-geg-border-strong)',
          borderRadius: 6,
          fontSize: 11,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: 'var(--color-geg-text-2)',
          cursor: 'pointer',
        }}
      >
        Data breakdown
      </button>

      {open ? (
        <div
          className="geg-mono"
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            zIndex: 60,
            width: 'min(92vw, 560px)',
            maxHeight: '70vh',
            overflowY: 'auto',
            background: 'var(--color-geg-bg-elev)',
            border: '1px solid var(--color-geg-border-strong)',
            borderRadius: 8,
            boxShadow: '0 12px 32px rgba(0,0,0,0.35)',
            padding: 16,
            fontSize: 10,
            letterSpacing: '0.04em',
            color: 'var(--color-geg-text-2)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ ...sectionTitle, fontSize: 10 }}>
              Data breakdown · {monthDay(startEtDate)} – {monthDay(endEtDate)} ET
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--color-geg-text-3)',
                fontSize: 14,
                lineHeight: 1,
                padding: 2,
              }}
              aria-label="Close"
            >
              ×
            </button>
          </div>

          {/* The two headline numbers: the hand-pull view vs the funnel's. */}
          <div style={{ marginTop: 12, display: 'grid', gap: 4, lineHeight: 1.7 }}>
            <div>
              <span style={sectionTitle}>Close date pull</span>{' '}
              <b>{data.reference.toLocaleString('en-US')}</b> leads ·{' '}
              {data.referenceMq.toLocaleString('en-US')} MQ
              <span style={{ color: 'var(--color-geg-text-faint)' }}>
                {' '}
                — created or re-opted in window, any lead source (org-wide)
              </span>
            </div>
            <div>
              <span style={sectionTitle}>Counted here</span>{' '}
              <b>{data.counted.toLocaleString('en-US')}</b> ·{' '}
              {data.countedMq.toLocaleString('en-US')} MQ
              <span style={{ color: 'var(--color-geg-text-faint)' }}> — the DC ad cohort</span>
            </div>
            <div>
              <span style={sectionTitle}>Not counted</span>{' '}
              <b>{data.excludedTotal.toLocaleString('en-US')}</b>
              {data.movedTotal > 0 ? (
                <span style={{ color: 'var(--color-geg-text-faint)' }}>
                  {' '}
                  + {data.movedTotal.toLocaleString('en-US')} counted on another day
                </span>
              ) : null}
            </div>
          </div>

          {groups.map((g) => {
            const rows = byReason.get(g.code) ?? []
            const total = data.excludedByReason[g.code] ?? 0
            return (
              <div key={g.code} style={{ marginTop: 14 }}>
                <div style={sectionTitle}>
                  {g.label} · {total.toLocaleString('en-US')}
                </div>
                {g.hint ? (
                  <div style={{ color: 'var(--color-geg-text-faint)', marginTop: 2, lineHeight: 1.5 }}>
                    {g.hint}
                  </div>
                ) : null}
                <div style={{ marginTop: 4 }}>
                  {rows.map((lead) => (
                    <LeadLine
                      key={lead.closeId}
                      closeId={lead.closeId}
                      name={lead.name}
                      day={lead.day}
                      mq={lead.mq}
                    />
                  ))}
                  {total > rows.length ? (
                    <div style={{ color: 'var(--color-geg-text-faint)', marginTop: 2 }}>
                      +{(total - rows.length).toLocaleString('en-US')} more
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}

          {data.movedTotal > 0 ? (
            <div style={{ marginTop: 14 }}>
              <div style={sectionTitle}>
                Counted on another day · {data.movedTotal.toLocaleString('en-US')}
              </div>
              <div style={{ color: 'var(--color-geg-text-faint)', marginTop: 2, lineHeight: 1.5 }}>
                In the funnel, but a re-opt moved the cohort day outside this window — a Close date
                pull double-counts these on both days; the funnel counts them once, on the newest
                opt-in.
              </div>
              <div style={{ marginTop: 4 }}>
                {data.moved.map((lead) => (
                  <LeadLine
                    key={lead.closeId}
                    closeId={lead.closeId}
                    name={lead.name}
                    day={lead.anchorDay}
                    mq={lead.mq}
                  />
                ))}
              </div>
            </div>
          ) : null}

          <div
            style={{
              marginTop: 16,
              paddingTop: 10,
              borderTop: '1px solid var(--color-geg-border-strong)',
              color: 'var(--color-geg-text-faint)',
              fontSize: 9,
              lineHeight: 1.7,
            }}
          >
            Stage counts are <b>cohort-scope</b>: SMS, Connects and HVC count events any time after
            the opt-in — a Close pull filtered to same-day activity reads lower; the daily
            table&apos;s D0/D3/D7 columns are the day-of view. · MQ = Close&apos;s &ldquo;marketing
            qualified&rdquo; field (what a hand pull filters on); the funnel&apos;s Qualified stage
            reads the lead&apos;s Typeform answer — in practice they agree. · This breakdown ignores
            the campaign / ad / landing-page filters: the reference is an org-wide date pull.
          </div>
        </div>
      ) : null}
    </div>
  )
}
