'use client'

// DC Ads · Connected Calls — the AI call-intelligence surface (0150/0151).
//
// Renders the dc_ads_call_reviews() payload: a summary strip, the
// "Why aren't DC leads closing?" distribution, missed-sales / great-saves
// queues, archetype mix, voice-of-customer quotes, and the filterable
// connected-calls feed. Every lead links to its lifecycle page and every
// call to its full review page (middleware-allowlisted deep links).
// All numbers are dc_ads-rubric reviews only — scoring starts 2026-08-18
// (forward-only); pre-rubric calls never appear here.

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

function leadHref(id: string): string {
  return `/sales-dashboard/leads/${encodeURIComponent(id)}`
}

function callHref(c: DcAdsReviewedCall): string {
  return `/sales-dashboard/calls/${encodeURIComponent(c.callId)}?lead=${encodeURIComponent(c.leadId)}`
}

// One compact call line — shared by the flag queues and the feed.
function CallLine({ c }: { c: DcAdsReviewedCall }) {
  return (
    <div
      className="geg-mono"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 10,
        alignItems: 'baseline',
        fontSize: 10.5,
        padding: '7px 0',
        borderBottom: '1px dashed var(--color-geg-border)',
      }}
    >
      <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 86 }}>{fmtAt(c.at)}</span>
      <a
        href={leadHref(c.leadId)}
        className="geg-serif"
        style={{ fontSize: 13, color: 'var(--color-geg-text)', textDecoration: 'none' }}
      >
        {c.leadName}
      </a>
      <span style={{ color: 'var(--color-geg-text-3)' }}>{c.repName ?? '—'}</span>
      <span style={{ color: 'var(--color-geg-text-faint)' }}>{fmtDur(c.durationS)}</span>
      <span style={{ color: 'var(--color-geg-text-2)' }}>
        L {c.leadScore} · I {c.intent} · O {c.offerUnderstanding} · R {c.repScore}
      </span>
      <span style={{ color: c.closed ? 'var(--color-geg-pos)' : 'var(--color-geg-text-3)' }}>
        {c.closed ? 'Closed' : (c.whyNotClosed ? (WHY_LABELS[c.whyNotClosed] ?? c.whyNotClosed) : 'Lost')}
      </span>
      {c.missed ? <span title="Likely missed sale">🔴</span> : null}
      {c.save ? <span title="Great save">🟢</span> : null}
      {c.recoverable && !c.closed ? (
        <span style={{ color: 'var(--color-geg-warn)' }} title="AI judges this lead still closeable with a follow-up">
          recoverable
        </span>
      ) : null}
      <a href={callHref(c)} style={{ color: 'var(--color-geg-accent)', textDecoration: 'none', marginLeft: 'auto' }}>
        review →
      </a>
    </div>
  )
}

type FeedFilter = 'all' | 'closed' | 'lost' | 'recoverable' | 'missed' | 'save'

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
  const vocByTopic = useMemo(() => {
    const m = new Map<string, DcAdsVocQuote[]>()
    for (const v of intel.voc) {
      const list = m.get(v.topic)
      if (list) list.push(v)
      else m.set(v.topic, [v])
    }
    return Array.from(m.entries()).sort((a, b) => b[1].length - a[1].length)
  }, [intel.voc])

  if (intel.avg.n === 0) {
    return (
      <div className="geg-mono" style={{ marginTop: 24, fontSize: 11, letterSpacing: '0.05em', color: 'var(--color-geg-text-3)', lineHeight: 1.8 }}>
        No AI-reviewed connected calls in the selected dates yet. Scoring under the DC-ads rubric
        started 2026-08-18 — every new connected call (≥90s, recorded) is reviewed within ~15
        minutes, and rows appear here as reps dial.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginTop: 20 }}>
      {/* Summary strip */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'baseline' }}>
        <span className="geg-mono" style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)' }}>
          {intel.avg.n.toLocaleString('en-US')} reviewed calls
        </span>
        <ScoreChip label="Lead quality" value={intel.avg.leadScore} />
        <ScoreChip label="Intent" value={intel.avg.intent} />
        <ScoreChip label="Offer understanding" value={intel.avg.offerUnderstanding} />
        <ScoreChip label="Rep execution" value={intel.avg.repScore} />
      </div>

      {/* Why aren't DC leads closing? */}
      <div style={card}>
        <div style={sectionTitle}>Why aren&apos;t DC leads closing?</div>
        {lostReasons.length === 0 ? (
          <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}>
            No lost reviewed calls in the window.
          </span>
        ) : (
          <div style={{ maxWidth: 480 }}>
            {lostReasons.map(([reason, n]) => (
              <div
                key={reason}
                className="geg-mono"
                style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderBottom: '1px dashed var(--color-geg-border)', fontSize: 11 }}
              >
                <span style={{ flex: 1, color: 'var(--color-geg-text-2)' }}>{WHY_LABELS[reason] ?? reason}</span>
                <span className="geg-numeric-serif" style={{ fontSize: 14, color: 'var(--color-geg-text)' }}>
                  {intel.lostTotal > 0 ? `${Math.round((n / intel.lostTotal) * 100)}%` : '—'}
                </span>
                <span style={{ color: 'var(--color-geg-text-faint)', minWidth: 34, textAlign: 'right' }}>{n}</span>
              </div>
            ))}
            <div className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)', marginTop: 6 }}>
              % of {intel.lostTotal} lost reviewed calls — primary reason per call, judged by the AI review.
            </div>
          </div>
        )}
      </div>

      {/* Flag queues */}
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
            intel.missed.map((c) => <CallLine key={c.callId} c={c} />)
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
            intel.saves.map((c) => <CallLine key={c.callId} c={c} />)
          )}
        </div>
      </div>

      {/* Archetypes */}
      <div style={card}>
        <div style={sectionTitle}>Lead archetypes</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14 }}>
          {intel.archetypes.map((a) => (
            <span key={a.archetype} className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-2)' }}>
              <b>{ARCHETYPE_LABELS[a.archetype] ?? a.archetype}</b> {a.n}
              <span style={{ color: 'var(--color-geg-text-faint)' }}>
                {' '}· {a.n > 0 ? Math.round((a.closes / a.n) * 100) : 0}% closed
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Voice of customer */}
      {intel.voc.length > 0 ? (
        <div style={card}>
          <div style={sectionTitle}>Voice of customer — verbatim quotes for marketing</div>
          <div style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
            {vocByTopic.map(([topic, quotes]) => (
              <div key={topic}>
                <div className="geg-mono" style={{ fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 4 }}>
                  {TOPIC_LABELS[topic] ?? topic} · {quotes.length}
                </div>
                {quotes.slice(0, 8).map((v, i) => (
                  <div key={`${v.callId}-${i}`} className="geg-serif" style={{ fontSize: 12.5, lineHeight: 1.55, padding: '4px 0', color: 'var(--color-geg-text-2)' }}>
                    &ldquo;{v.quote}&rdquo;{' '}
                    <span className="geg-mono" style={{ fontSize: 9, color: 'var(--color-geg-text-faint)' }}>— {v.leadName}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* The feed */}
      <div>
        <div style={sectionTitle}>
          Connected calls · {intel.callsTotal.toLocaleString('en-US')}
          {intel.callsTotal > intel.calls.length ? (
            <span style={{ textTransform: 'none', letterSpacing: '0.04em' }}>
              {' '}(newest {intel.calls.length} listed — narrow the dates for the rest)
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
              background: 'transparent',
              color: 'var(--color-geg-text-2)',
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
          feed.map((c) => <CallLine key={c.callId} c={c} />)
        )}
      </div>

      <FineNote style={{ letterSpacing: '0.05em', lineHeight: 1.8 }} summary="How to read this page">
        Every <b>connected call</b> (≥90s, recorded) on a DC-ads cohort lead is transcribed and
        AI-reviewed within ~15 minutes, under the DC dial-up rubric (scoring started 2026-08-18 —
        earlier calls were graded under a booking rubric and are deliberately not shown).{' '}
        <b>L / I / O / R</b> = lead quality / buying intent / offer understanding / rep execution,
        each 0–10, judged from the transcript. <b>Closed</b> = committed to enroll/pay on the call
        itself. The lost reason is the AI&apos;s judgment of the PRIMARY blocker — one per call.{' '}
        <b>Recoverable</b> = a follow-up could still realistically close it. 🔴/🟢 flags are
        computed from the scores (thresholds in the database, not the model). This page is
        activity-scoped: calls that HAPPENED in the selected dates, whatever day the lead opted in.
        Lead names open the lead&apos;s lifecycle page; &ldquo;review →&rdquo; opens the full call
        review with transcript.
      </FineNote>
    </div>
  )
}
