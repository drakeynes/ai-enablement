'use client'

// DC Ads — the daily AI executive summary card (0152; compact slider
// 2026-08-19, boss: "too much going on" — the four sections now share ONE
// fixed-size box, arrows slide between them, content scrolls if it
// overflows). Sections: going well / going wrong / traffic or sales /
// what changed. Generated nightly by api/dc_exec_summary_cron.py from
// aggregates only. Renders nothing until the first summary lands
// (dashboard-only by decision — this never posts to Slack). Older rows
// (exec-v1) carry an extra test_next[] key in the jsonb; never rendered.

import { useState } from 'react'

import type { DcAdsExecSummary } from '@/lib/db/dc-ads'

// YYYY-MM-DD → "Aug 18".
function monthDay(ymd: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })
    .format(new Date(`${ymd}T12:00:00Z`))
}

type Panel = {
  title: string
  tone?: 'pos' | 'neg'
  items: string[] // one entry = one bullet; a single entry with prose = a paragraph
  empty: string
}

// Full-width box, slightly taller + larger type (boss 2026-08-19 round 2).
const PANEL_HEIGHT = 150

export function DcAdsExecSummaryCard({ exec }: { exec: DcAdsExecSummary | null }) {
  const [idx, setIdx] = useState(0)
  if (!exec) return null
  const s = exec.summary

  const panels: Panel[] = [
    { title: 'Going well', tone: 'pos', items: s.going_well, empty: 'Nothing stood out.' },
    { title: 'Going wrong', tone: 'neg', items: s.going_wrong, empty: 'Nothing stood out.' },
    { title: 'Traffic or sales?', items: s.traffic_or_sales ? [s.traffic_or_sales] : [], empty: 'No verdict.' },
    { title: 'What changed', items: s.changed, empty: 'Nothing moved vs the baseline.' },
  ]
  const step = (d: number) => setIdx((i) => (i + d + panels.length) % panels.length)
  const active = panels[idx]

  return (
    <div
      style={{
        marginTop: 24,
        border: '1px solid var(--color-geg-border-strong)',
        borderRadius: 8,
        padding: '14px 18px 16px',
      }}
    >
      {/* Header: identity + the active section + pager. The grounding note
          lives in the hover title — the visible card stays minimal. */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
        <span
          className="geg-mono"
          title="Generated nightly from the daily table + AI call-review aggregates (never raw transcripts). Small review-n days read as directional."
          style={{ fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', whiteSpace: 'nowrap' }}
        >
          AI summary · {monthDay(exec.forDate)}
        </span>
        <span
          className="geg-mono"
          style={{
            fontSize: 10.5,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color:
              active.tone === 'pos'
                ? 'var(--color-geg-pos)'
                : active.tone === 'neg'
                  ? 'var(--color-geg-warn)'
                  : 'var(--color-geg-text-2)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
            flex: 1,
          }}
        >
          {active.title}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
          <PagerArrow dir="prev" onClick={() => step(-1)} />
          <span className="geg-mono" style={{ fontSize: 9.5, color: 'var(--color-geg-text-faint)', letterSpacing: '0.08em' }}>
            {idx + 1}/{panels.length}
          </span>
          <PagerArrow dir="next" onClick={() => step(1)} />
        </span>
      </div>

      {/* The slider: four fixed-height panels on one track; the transform
          slides the track, each panel scrolls its own overflow. */}
      <div style={{ overflow: 'hidden' }}>
        <div
          style={{
            display: 'flex',
            transform: `translateX(-${idx * 100}%)`,
            transition: 'transform 280ms ease',
          }}
        >
          {panels.map((p) => (
            <div
              key={p.title}
              aria-hidden={p !== active}
              style={{ flex: '0 0 100%', minWidth: 0, height: PANEL_HEIGHT, overflowY: 'auto', paddingRight: 6 }}
            >
              {p.items.length === 0 ? (
                <div className="geg-serif" style={{ fontSize: 13.5, fontStyle: 'italic', color: 'var(--color-geg-text-3)', padding: '2px 0' }}>
                  {p.empty}
                </div>
              ) : (
                p.items.map((item, i) => (
                  <div
                    key={i}
                    className="geg-serif"
                    style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--color-geg-text-2)', padding: '2px 0' }}
                  >
                    {p.items.length > 1 ? '· ' : ''}
                    {item}
                  </div>
                ))
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function PagerArrow({ dir, onClick }: { dir: 'prev' | 'next'; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={dir === 'prev' ? 'Previous section' : 'Next section'}
      className="geg-mono"
      style={{
        fontSize: 12,
        lineHeight: 1,
        padding: '3px 8px',
        borderRadius: 5,
        cursor: 'pointer',
        border: '1px solid var(--color-geg-border)',
        background: 'var(--color-geg-bg-elev)',
        color: 'var(--color-geg-text-2)',
      }}
    >
      {dir === 'prev' ? '‹' : '›'}
    </button>
  )
}
