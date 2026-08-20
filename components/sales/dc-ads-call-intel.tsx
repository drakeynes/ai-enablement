'use client'

// DC Ads · Connected Calls — the AI call-intelligence surface (0150/0151).
//
// Structure (boss feedback 2026-08-18): the CALLS FEED leads the page as a
// real table with labeled columns (Time / Lead / Rep / …), the pattern
// blocks (why-not-closing, flag queues, archetypes, VoC) follow. Renders
// the dc_ads_call_reviews() payload; every lead links to its lifecycle
// page and every call to its full review page. dc_ads-rubric reviews only
// — scoring started 2026-08-18 (+ the same-day backfill of the cohort's
// earlier calls).

import { useMemo, useState } from 'react'
import type { DcAdsCallIntel, DcAdsReviewedCall, DcAdsVocQuote } from '@/lib/db/dc-ads'
import { FineNote } from './fine-note'

const WHY_LABELS: Record<string, string> = {
  didnt_understand_offer: "Didn't understand offer",
  low_intent: 'Low intent',
  price_platform_objection: 'Price/platform objection',
  rep_execution: 'Rep execution',
  bad_timing: 'Busy / bad timing',
  skepticism: 'Skepticism',
  cant_pay_today: "Can't pay today",
  spouse_partner: 'Spouse/partner',
  other: 'Other',
}

const ARCHETYPE_LABELS: Record<string, string> = {
  high_intent_entrepreneur: 'High-intent entrepreneur',
  curious_ai_learner: 'Curious AI learner',
  broke_opportunity_seeker: 'Broke opportunity seeker',
  skeptic: 'Skeptic',
  existing_business_owner: 'Existing business owner',
  other: 'Other',
}

// rep_execution sub-dataset (0155, prompt v4): the specific gap that lost
// the call. 'unclassified' = pre-v4 reviews the backfill hasn't re-graded.
const GAP_LABELS: Record<string, string> = {
  no_close_attempt: 'Never asked for the sale',
  gave_up_at_objection: 'Gave up at first objection',
  no_urgency: 'Built no urgency',
  weak_discovery: 'Weak discovery',
  offer_not_explained: "Didn't explain the offer",
  talked_over_lead: 'Talked over the lead',
  deferred_to_followup: 'Punted to a follow-up',
  other: 'Other',
  unclassified: 'Not yet re-graded',
}

const TOPIC_LABELS: Record<string, string> = {
  goal: 'Goals',
  fear: 'Fears',
  objection: 'Objections',
  why_applied: 'Why they applied',
  other: 'Other',
}

const AT_FMT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

function fmtAt(iso: string): string {
  return AT_FMT.format(new Date(iso))
}

function fmtDur(s: number): string {
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.floor(s - m * 60)).padStart(2, '0')}`
}

const sectionTitle: React.CSSProperties = {
  fontSize: 10,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
  color: 'var(--color-geg-text-3)',
  marginBottom: 8,
}

const card: React.CSSProperties = {
  border: '1px solid var(--color-geg-border)',
  borderRadius: 8,
  padding: 14,
}

function ScoreChip({ label, value }: { label: string; value: number | null }) {
  return (
    <span className="geg-mono" style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--color-geg-text-2)' }}>
      {label}{' '}
      <span className="geg-numeric-serif" style={{ fontSize: 15, color: 'var(--color-geg-text)' }}>
        {value !== null ? value.toFixed(1) : '—'}
      </span>
    </span>
  )
}

// The lead's CLOSE profile (boss 2026-08-18: clicking a lead opens Close,
// where reps actually work — the in-app lifecycle page lost its links).
function leadHref(id: string): string {
  return `https://app.close.com/lead/${encodeURIComponent(id)}/`
}

function callHref(c: DcAdsReviewedCall): string {
  return `/sales-dashboard/calls/${encodeURIComponent(c.callId)}?lead=${encodeURIComponent(c.leadId)}`
}

// Score cell tone: 0-3 weak, 7-10 strong (mirror of the Slack emoji contract).
function scoreColor(v: number): string {
  if (v <= 3) return 'var(--color-geg-warn)'
  if (v >= 7) return 'var(--color-geg-pos)'
  return 'var(--color-geg-text-2)'
}

// One compact call line — the flag queues' row shape (the feed itself is a
// labeled table below). Rep is explicitly labeled after the boss couldn't
// tell whose name was whose.
function CallLine({ c }: { c: DcAdsReviewedCall }) {
  return (
    <div
      className="geg-mono"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
        alignItems: 'baseline',
        fontSize: 10.5,
        padding: '7px 0',
        borderBottom: '1px dashed var(--color-geg-border)',
      }}
    >
      <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 86 }}>{fmtAt(c.at)}</span>
      <a
        href={leadHref(c.leadId)}
        target="_blank"
        rel="noreferrer"
        className="geg-serif"
        style={{ fontSize: 13, color: 'var(--color-geg-text)', textDecoration: 'none' }}
      >
        {c.leadName}
      </a>
      <span style={{ color: 'var(--color-geg-text-3)' }}>
        rep <b>{c.repName ?? '—'}</b>
      </span>
      <span style={{ color: 'var(--color-geg-text-2)' }}>
        lead {c.leadScore} · intent {c.intent} · rep exec {c.repScore}
      </span>
      <a href={callHref(c)} style={{ color: 'var(--color-geg-accent)', textDecoration: 'none', marginLeft: 'auto' }}>
        review →
      </a>
    </div>
  )
}

type FeedFilter = 'all' | 'closed' | 'lost' | 'recoverable' | 'missed' | 'save'

// Sticky inside the feed's fixed-height scroll box — solid background so
// rows never bleed through while scrolling.
const TH_STYLE: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 9,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: 'var(--color-geg-text-3)',
  textAlign: 'left',
  whiteSpace: 'nowrap',
  borderBottom: '1px solid var(--color-geg-border)',
  position: 'sticky',
  top: 0,
  zIndex: 1,
  background: 'var(--color-geg-bg)',
}

function Td({
  children,
  right,
  faint,
}: {
  children: React.ReactNode
  right?: boolean
  faint?: boolean
}) {
  return (
    <td
      style={{
        padding: '8px 10px',
        whiteSpace: 'nowrap',
        textAlign: right ? 'right' : 'left',
        color: faint ? 'var(--color-geg-text-faint)' : 'var(--color-geg-text-2)',
        borderBottom: '1px dashed var(--color-geg-border)',
        verticalAlign: 'middle',
      }}
    >
      {children}
    </td>
  )
}

export function DcAdsCallIntelSection({ intel }: { intel: DcAdsCallIntel }) {
  const [feedFilter, setFeedFilter] = useState<FeedFilter>('all')
  const [repFilter, setRepFilter] = useState<string>('')
  const [q, setQ] = useState('')

  const reps = useMemo(
    () => Array.from(new Set(intel.calls.map((c) => c.repName).filter((v): v is string => !!v))).sort(),
    [intel.calls],
  )

  const feed = useMemo(() => {
    let rows = intel.calls
    if (feedFilter === 'closed') rows = rows.filter((c) => c.closed)
    if (feedFilter === 'lost') rows = rows.filter((c) => !c.closed)
    if (feedFilter === 'recoverable') rows = rows.filter((c) => c.recoverable && !c.closed)
    if (feedFilter === 'missed') rows = rows.filter((c) => c.missed)
    if (feedFilter === 'save') rows = rows.filter((c) => c.save)
    if (repFilter) rows = rows.filter((c) => c.repName === repFilter)
    const needle = q.trim().toLowerCase()
    if (needle) rows = rows.filter((c) => c.leadName.toLowerCase().includes(needle))
    return rows
  }, [intel.calls, feedFilter, repFilter, q])

  const lostReasons = Object.entries(intel.whyNotClosed).sort((a, b) => b[1] - a[1])
  // Gap sub-rows, biggest first, the unclassified backlog always last.
  const repGaps = Object.entries(intel.repGaps ?? {}).sort((a, b) =>
    a[0] === 'unclassified' ? 1 : b[0] === 'unclassified' ? -1 : b[1] - a[1],
  )
  // Top quotes only (boss 2026-08-18 — the full list was verbose): ranked by
  // the source call's lead-quality + intent, so the box illustrates what the
  // BEST prospects say, capped at 8.
  const topVoc = useMemo(() => {
    const rankByCall = new Map(intel.calls.map((c) => [c.callId, c.leadScore + c.intent]))
    return intel.voc
      .map((v): DcAdsVocQuote & { rank: number } => ({ ...v, rank: rankByCall.get(v.callId) ?? 0 }))
      .sort((a, b) => b.rank - a.rank)
      .slice(0, 8)
  }, [intel.voc, intel.calls])

  if (intel.avg.n === 0) {
    return (
      <div className="geg-mono" style={{ marginTop: 24, fontSize: 11, letterSpacing: '0.05em', color: 'var(--color-geg-text-3)', lineHeight: 1.8 }}>
        No AI-reviewed connected calls in the selected dates yet. Every new connected call (≥90s,
        recorded) is reviewed within ~15 minutes, and rows appear here as reps dial.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginTop: 20 }}>
      {/* ------------------------------------------------ THE FEED (top) */}
      <div>
        <div style={{ ...sectionTitle, display: 'flex', gap: 12, alignItems: 'baseline', flexWrap: 'wrap' }}>
          <span>Connected calls · {intel.callsTotal.toLocaleString('en-US')}</span>
          {intel.callsTotal > intel.calls.length ? (
            <span style={{ textTransform: 'none', letterSpacing: '0.04em' }}>
              newest {intel.calls.length} listed — narrow the dates for the rest
            </span>
          ) : null}
        </div>

        <div className="geg-mono" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10, fontSize: 10 }}>
          {(
            [
              ['all', 'All'],
              ['closed', 'Closed'],
              ['lost', 'Lost'],
              ['recoverable', 'Recoverable'],
              ['missed', '🔴 Missed'],
              ['save', '🟢 Saves'],
            ] as Array<[FeedFilter, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFeedFilter(key)}
              className="geg-mono"
              style={{
                padding: '4px 10px',
                borderRadius: 5,
                border: '1px solid var(--color-geg-border-strong)',
                background: feedFilter === key ? 'var(--color-geg-bg-elev)' : 'transparent',
                color: feedFilter === key ? 'var(--color-geg-text)' : 'var(--color-geg-text-3)',
                fontSize: 10,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
          <select
            value={repFilter}
            onChange={(e) => setRepFilter(e.target.value)}
            className="geg-mono"
            style={{
              padding: '4px 8px',
              borderRadius: 5,
              border: '1px solid var(--color-geg-border-strong)',
              // Solid dark background + colorScheme so the NATIVE option
              // popup renders dark too (transparent left it white — boss
              // couldn't read the names).
              background: 'var(--color-geg-bg-elev)',
              color: 'var(--color-geg-text)',
              colorScheme: 'dark',
              fontSize: 10,
            }}
          >
            <option value="">All reps</option>
            {reps.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search lead…"
            className="geg-mono"
            style={{
              padding: '4px 8px',
              borderRadius: 5,
              border: '1px solid var(--color-geg-border-strong)',
              background: 'transparent',
              color: 'var(--color-geg-text)',
              fontSize: 10,
              minWidth: 140,
            }}
          />
        </div>

        {feed.length === 0 ? (
          <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}>
            No calls match.
          </span>
        ) : (
          // Fixed-height scroll box (boss 2026-08-18) — the backfilled
          // history makes this hundreds of rows; header stays pinned.
          <div style={{ overflowX: 'auto', overflowY: 'auto', maxHeight: 540, border: '1px solid var(--color-geg-border)', borderRadius: 8 }}>
            <table className="geg-mono" style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
              <thead>
                <tr>
                  {['Time (ET)', 'Lead', 'Rep', 'Dur', 'Lead Q', 'Intent', 'Offer', 'Rep exec', 'Outcome', 'Flags', ''].map(
                    (h, i) => (
                      <th key={i} style={{ ...TH_STYLE, textAlign: i >= 3 && i <= 7 ? 'right' : 'left' }}>
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {feed.map((c) => (
                  <tr key={c.callId}>
                    <Td faint>{fmtAt(c.at)}</Td>
                    <Td>
                      <a
                        href={leadHref(c.leadId)}
                        target="_blank"
                        rel="noreferrer"
                        className="geg-serif"
                        style={{ fontSize: 13, color: 'var(--color-geg-text)', textDecoration: 'none' }}
                      >
                        {c.leadName}
                      </a>
                      {/* The AI read at a glance (0155, boss ask): archetype +
                          the review's own sentence on the blocker — no click
                          needed; hover holds the full text. */}
                      <span
                        title={[c.noCloseReason, c.recoverableNote ? `Follow-up: ${c.recoverableNote}` : null]
                          .filter(Boolean)
                          .join(' · ') || undefined}
                        style={{
                          display: 'block',
                          fontSize: 9,
                          letterSpacing: '0.03em',
                          color: 'var(--color-geg-text-faint)',
                          maxWidth: 360,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {ARCHETYPE_LABELS[c.archetype] ?? c.archetype}
                        {c.closed ? ' · closed on this call' : c.noCloseReason ? ` · ${c.noCloseReason}` : ''}
                      </span>
                    </Td>
                    <Td>{c.repName ?? '—'}</Td>
                    <Td right faint>{fmtDur(c.durationS)}</Td>
                    <Td right><span style={{ color: scoreColor(c.leadScore) }}>{c.leadScore}</span></Td>
                    <Td right><span style={{ color: scoreColor(c.intent) }}>{c.intent}</span></Td>
                    <Td right><span style={{ color: scoreColor(c.offerUnderstanding) }}>{c.offerUnderstanding}</span></Td>
                    <Td right><span style={{ color: scoreColor(c.repScore) }}>{c.repScore}</span></Td>
                    <Td>
                      {c.closed ? (
                        <span style={{ color: 'var(--color-geg-pos)' }}>Closed</span>
                      ) : (
                        <span title={c.mainObjection ?? undefined}>
                          {c.whyNotClosed ? (WHY_LABELS[c.whyNotClosed] ?? c.whyNotClosed) : 'Lost'}
                        </span>
                      )}
                    </Td>
                    <Td>
                      {c.missed ? <span title="Likely missed sale">🔴</span> : null}
                      {c.save ? <span title="Great save">🟢</span> : null}
                      {c.recoverable && !c.closed ? (
                        <span style={{ color: 'var(--color-geg-warn)' }} title="AI judges this lead still closeable with a follow-up">
                          {' '}recov
                        </span>
                      ) : null}
                      {c.dq ? <span title="Advisory DQ flag"> 🚫</span> : null}
                    </Td>
                    <Td>
                      <a href={callHref(c)} style={{ color: 'var(--color-geg-accent)', textDecoration: 'none' }}>
                        review →
                      </a>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* -------------------------------------------- window averages */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'baseline' }}>
        <span className="geg-mono" style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}>
          {intel.avg.n.toLocaleString('en-US')} reviewed calls · window averages
        </span>
        <ScoreChip label="Lead quality" value={intel.avg.leadScore} />
        <ScoreChip label="Intent" value={intel.avg.intent} />
        <ScoreChip label="Offer understanding" value={intel.avg.offerUnderstanding} />
        <ScoreChip label="Rep execution" value={intel.avg.repScore} />
      </div>

      {/* ---------------- why aren't DC leads closing? + archetypes ----
          One box, two halves side by side (boss 2026-08-18 round 4: the
          reasons only used half the width — archetypes fill the other
          half as a matching vertical list). Stacks on narrow screens. */}
      <div style={card}>
        <div style={{ display: 'grid', gap: 28, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
          <div>
            <div style={sectionTitle}>Why aren&apos;t DC leads closing?</div>
            {lostReasons.length === 0 ? (
              <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}>
                No lost reviewed calls in the window.
              </span>
            ) : (
              <div>
                {lostReasons.map(([reason, n]) => (
                  <div key={reason}>
                    <div
                      className="geg-mono"
                      style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderBottom: '1px dashed var(--color-geg-border)', fontSize: 11 }}
                    >
                      <span style={{ flex: 1, color: 'var(--color-geg-text-2)' }}>{WHY_LABELS[reason] ?? reason}</span>
                      <span className="geg-numeric-serif" style={{ fontSize: 14, color: 'var(--color-geg-text)' }}>
                        {intel.lostTotal > 0 ? `${Math.round((n / intel.lostTotal) * 100)}%` : '—'}
                      </span>
                      <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 34, textAlign: 'right' }}>{n}</span>
                    </div>
                    {/* The rep_execution sub-dataset (0155, boss ask: "what
                        are the gaps specifically") — % of the rep-execution
                        losses, indented under their parent row. */}
                    {reason === 'rep_execution' && repGaps.length > 0
                      ? repGaps.map(([gap, gn]) => (
                          <div
                            key={gap}
                            className="geg-mono"
                            style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '4px 0 4px 16px', borderBottom: '1px dotted var(--color-geg-border)', fontSize: 10 }}
                          >
                            <span style={{ flex: 1, color: gap === 'unclassified' ? 'var(--color-geg-text-faint)' : 'var(--color-geg-text-3)' }}>
                              ↳ {GAP_LABELS[gap] ?? gap}
                            </span>
                            <span className="geg-numeric-serif" style={{ fontSize: 12, color: 'var(--color-geg-text-2)' }}>
                              {n > 0 ? `${Math.round((gn / n) * 100)}%` : '—'}
                            </span>
                            <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 34, textAlign: 'right' }}>{gn}</span>
                          </div>
                        ))
                      : null}
                  </div>
                ))}
                <div className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)', marginTop: 6 }}>
                  % of {intel.lostTotal} lost reviewed calls — primary reason per call, judged by the AI
                  review. The indented rows split the rep-execution losses by the specific gap
                  (&ldquo;not yet re-graded&rdquo; clears as the v4 backfill runs).
                </div>
              </div>
            )}
          </div>
          {intel.archetypes.length > 0 ? (
            <div>
              <div style={sectionTitle}>Lead archetypes</div>
              {intel.archetypes.map((a) => (
                <div
                  key={a.archetype}
                  className="geg-mono"
                  style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderBottom: '1px dashed var(--color-geg-border)', fontSize: 11 }}
                >
                  <span style={{ flex: 1, color: 'var(--color-geg-text-2)' }}>{ARCHETYPE_LABELS[a.archetype] ?? a.archetype}</span>
                  <span className="geg-numeric-serif" style={{ fontSize: 14, color: 'var(--color-geg-text)' }}>
                    {a.n}
                  </span>
                  <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 64, textAlign: 'right' }}>
                    {a.n > 0 ? Math.round((a.closes / a.n) * 100) : 0}% closed
                  </span>
                </div>
              ))}
              <div className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)', marginTop: 6 }}>
                Each lead counted once (its newest review names the type); closed = the lead&apos;s
                eventual DC close, not just on reviewed calls — only {intel.onCallCloses} sale
                {intel.onCallCloses === 1 ? '' : 's'} closed live on a reviewed call.
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* ------------------------------------------------- flag queues */}
      <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        <div style={card}>
          <div style={sectionTitle}>
            🔴 Likely missed sales · {intel.missedTotal.toLocaleString('en-US')}
          </div>
          <div className="geg-mono" style={{ fontSize: 9.5, color: 'var(--color-geg-text-faint)', marginBottom: 6, lineHeight: 1.6 }}>
            Good lead (≥7), real intent (≥7), low rep execution (≤5), no close — the calls a sales
            manager should replay first.
          </div>
          {intel.missed.length === 0 ? (
            <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}>None in the window.</span>
          ) : (
            // Scroll box (boss round 4) — these stack up over a long window.
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {intel.missed.map((c) => <CallLine key={c.callId} c={c} />)}
            </div>
          )}
        </div>
        <div style={card}>
          <div style={sectionTitle}>
            🟢 Great saves · {intel.savesTotal.toLocaleString('en-US')}
          </div>
          <div className="geg-mono" style={{ fontSize: 9.5, color: 'var(--color-geg-text-faint)', marginBottom: 6, lineHeight: 1.6 }}>
            Weak or low-intent lead (≤4) the rep closed anyway — winning behaviors worth copying.
          </div>
          {intel.saves.length === 0 ? (
            <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}>None in the window.</span>
          ) : (
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {intel.saves.map((c) => <CallLine key={c.callId} c={c} />)}
            </div>
          )}
        </div>
      </div>

      {/* --------------------------------------------- voice of customer */}
      {topVoc.length > 0 ? (
        <div style={card}>
          <div style={sectionTitle}>
            Voice of customer · top quotes
            <span style={{ textTransform: 'none', letterSpacing: '0.04em' }}>
              {' '}— from the highest-quality prospects · {intel.voc.length.toLocaleString('en-US')} collected in window
            </span>
          </div>
          {topVoc.map((v, i) => (
            <div key={`${v.callId}-${i}`} className="geg-serif" style={{ fontSize: 12.5, lineHeight: 1.55, padding: '4px 0', color: 'var(--color-geg-text-2)' }}>
              &ldquo;{v.quote}&rdquo;{' '}
              <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}>
                {TOPIC_LABELS[v.topic] ?? v.topic} — {v.leadName}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <FineNote style={{ letterSpacing: '0.05em', lineHeight: 1.8 }} summary="How to read this page">
        Every <b>connected call</b> (≥90s, recorded) on a DC-ads cohort lead is transcribed and
        AI-reviewed within ~15 minutes, under the DC dial-up rubric. <b>Lead Q / Intent / Offer /
        Rep exec</b> are each 0–10, judged from the transcript: lead quality and buying intent
        describe the PROSPECT, offer understanding is how well they grasped what DC is by call end,
        and rep execution grades the REP&apos;s discovery/pitch/objection-handling/close attempts —
        deliberately separate, so a great rep on a weak lead (or the reverse) reads honestly.{' '}
        <b>Closed</b> = committed to enroll/pay on the call itself. A lost call&apos;s Outcome shows
        the AI&apos;s judgment of the PRIMARY blocker (hover for the main objection verbatim).{' '}
        <b>recov</b> = a follow-up could still realistically close it. 🔴/🟢 flags are computed
        from the scores (thresholds in the database, not the model). This page is activity-scoped:
        calls that HAPPENED in the selected dates, whatever day the lead opted in. Lead names open
        the lead&apos;s lifecycle page; &ldquo;review →&rdquo; opens the full call review with
        transcript.
      </FineNote>
    </div>
  )
}
