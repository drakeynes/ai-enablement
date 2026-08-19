// DC Ads — the daily AI executive summary card (0152).
//
// Server-safe pure render of the newest dc_ads_exec_summaries row: what's
// going well / wrong, the traffic-vs-sales verdict, what changed.
// Generated nightly by api/dc_exec_summary_cron.py from aggregates only.
// Renders nothing until the first summary lands (dashboard-only by
// decision — this never posts to Slack). Older rows (exec-v1) carry an
// extra test_next[] key in the jsonb; it is deliberately not rendered.

import type { DcAdsExecSummary } from '@/lib/db/dc-ads'

// YYYY-MM-DD → "Aug 18".
function monthDay(ymd: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })
    .format(new Date(`${ymd}T12:00:00Z`))
}

function Bullets({ title, items, tone }: { title: string; items: string[]; tone?: 'pos' | 'neg' }) {
  if (items.length === 0) return null
  return (
    <div>
      <div
        className="geg-mono"
        style={{
          fontSize: 9.5,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: tone === 'pos' ? 'var(--color-geg-pos)' : tone === 'neg' ? 'var(--color-geg-warn)' : 'var(--color-geg-text-3)',
          marginBottom: 4,
        }}
      >
        {title}
      </div>
      {items.map((item, i) => (
        <div key={i} className="geg-serif" style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--color-geg-text-2)', padding: '2px 0' }}>
          · {item}
        </div>
      ))}
    </div>
  )
}

export function DcAdsExecSummaryCard({ exec }: { exec: DcAdsExecSummary | null }) {
  if (!exec) return null
  const s = exec.summary
  return (
    <div
      style={{
        marginTop: 24,
        border: '1px solid var(--color-geg-border-strong)',
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 12 }}
      >
        AI executive summary · {monthDay(exec.forDate)}
      </div>
      <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
        <Bullets title="Going well" items={s.going_well} tone="pos" />
        <Bullets title="Going wrong" items={s.going_wrong} tone="neg" />
        <div>
          <div className="geg-mono" style={{ fontSize: 9.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}>
            Traffic or sales?
          </div>
          <div className="geg-serif" style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--color-geg-text-2)' }}>
            {s.traffic_or_sales}
          </div>
        </div>
        <Bullets title="What changed" items={s.changed} />
      </div>
      <div className="geg-mono" style={{ marginTop: 12, fontSize: 8.5, letterSpacing: '0.05em', color: 'var(--color-geg-text-faint)', lineHeight: 1.6 }}>
        Generated nightly from the daily table + AI call-review aggregates (never raw transcripts).
        Claims are only as strong as the day&apos;s review coverage — small n days read as
        directional.
      </div>
    </div>
  )
}
