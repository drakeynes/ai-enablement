// DC Ads · Connected Calls — the weekly per-rep coaching block (0152).
//
// Server-safe pure render of the newest week's dc_rep_coaching rows: each
// rep's reviewed-call aggregates, the quote-evidenced strengths/weaknesses
// their reviews surfaced, and the AI's 2-3 coaching recommendations.
// Generated Mondays by api/dc_rep_coaching_cron.py; renders nothing until
// the first week lands.

import type { DcRepCoachingRow } from '@/lib/db/dc-ads'

function monthDay(ymd: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })
    .format(new Date(`${ymd}T12:00:00Z`))
}

function ItemList({ title, items }: { title: string; items: Array<{ point: string; evidence: string }> }) {
  if (items.length === 0) return null
  return (
    <div style={{ marginTop: 8 }}>
      <div className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 2 }}>
        {title}
      </div>
      {items.slice(0, 4).map((it, i) => (
        <div key={i} className="geg-serif" style={{ fontSize: 12, lineHeight: 1.55, color: 'var(--color-geg-text-2)', padding: '2px 0' }}>
          · {it.point}
          {it.evidence ? (
            <span className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)' }}> — &ldquo;{it.evidence}&rdquo;</span>
          ) : null}
        </div>
      ))}
    </div>
  )
}

export function DcRepCoachingSection({ rows }: { rows: DcRepCoachingRow[] }) {
  if (rows.length === 0) return null
  return (
    <div style={{ marginTop: 24 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 10 }}
      >
        Rep coaching · week of {monthDay(rows[0].weekStart)}
      </div>
      <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        {rows.map((r) => (
          <div key={r.repName} style={{ border: '1px solid var(--color-geg-border)', borderRadius: 8, padding: 14 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <span className="geg-serif" style={{ fontSize: 15, color: 'var(--color-geg-text)' }}>{r.repName}</span>
              <span className="geg-mono" style={{ fontSize: 9.5, color: 'var(--color-geg-text-faint)' }}>
                {r.callsReviewed} reviewed · avg exec {r.avgRepScore !== null ? r.avgRepScore.toFixed(1) : '—'} · {r.closes} closed
              </span>
            </div>
            <div style={{ marginTop: 10 }}>
              {r.recommendations.map((rec, i) => (
                <div key={i} style={{ padding: '6px 0', borderBottom: i < r.recommendations.length - 1 ? '1px dashed var(--color-geg-border)' : undefined }}>
                  <div className="geg-serif" style={{ fontSize: 12.5, color: 'var(--color-geg-text)' }}>
                    {i + 1}. {rec.focus}
                  </div>
                  {rec.why ? (
                    <div className="geg-serif" style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--color-geg-text-2)', marginTop: 2 }}>
                      {rec.why}
                    </div>
                  ) : null}
                  {rec.drill ? (
                    <div className="geg-mono" style={{ fontSize: 9.5, color: 'var(--color-geg-text-3)', marginTop: 3 }}>
                      DRILL: {rec.drill}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
            <ItemList title="Strengths this week" items={r.strengths} />
            <ItemList title="Weaknesses this week" items={r.weaknesses} />
          </div>
        ))}
      </div>
    </div>
  )
}
