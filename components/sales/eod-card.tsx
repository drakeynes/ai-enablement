import type { RepEod } from '@/lib/db/funnel-eods'

// One EOD report card — the Talent Roster's EodCard extracted for reuse on the
// DC Ads by-rep dropdown (boss batch 2026-08-15). Presentational only (safe in
// server AND client trees): renders the labeled Airtable fields straight from
// `fields`, so new EOD-form fields show up with no code change.

// Field keys not shown as metrics (the rep link, the date — in the header — and
// Airtable formula/meta fields).
const EOD_HIDDEN_FIELDS = new Set([
  'Sales Person',
  'Closer',
  'Name',
  'Record ID',
  'Date',
  'Submitted At',
])
// Long-form text fields rendered full-width below the metric tiles.
const EOD_TEXT_FIELDS = new Set([
  'Notes',
  'How were leads/calls today? (feedback for marketing)',
  'Biggest blocker you’re facing? if any',
  'How are you feeling overall?',
])

export function EodCard({ eod }: { eod: RepEod }) {
  const metricEntries = Object.entries(eod.fields).filter(
    ([k, v]) =>
      !EOD_HIDDEN_FIELDS.has(k) &&
      !EOD_TEXT_FIELDS.has(k) &&
      v !== null &&
      v !== '' &&
      typeof v !== 'object',
  )
  const textEntries = Object.entries(eod.fields).filter(
    ([k, v]) => EOD_TEXT_FIELDS.has(k) && typeof v === 'string' && v.trim() !== '',
  )
  return (
    <div
      style={{
        border: '1px solid var(--color-geg-border)',
        borderRadius: 8,
        background: 'var(--color-geg-bg-elev)',
        padding: '14px 16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 10,
        }}
      >
        <span className="geg-serif" style={{ fontSize: 14, color: 'var(--color-geg-text)' }}>
          {eod.eodDate ?? '(no date)'}
        </span>
        <span
          className="geg-mono"
          style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)' }}
        >
          {eod.kind} EOD
        </span>
      </div>
      {metricEntries.length ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
          {metricEntries.map(([k, v]) => (
            <div key={k}>
              <div
                className="geg-mono"
                style={{ fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', marginBottom: 2 }}
              >
                {k}
              </div>
              <div className="geg-numeric-serif" style={{ fontSize: 16, color: 'var(--color-geg-text)' }}>
                {String(v)}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {textEntries.map(([k, v]) => (
        <div key={k} style={{ marginTop: 10 }}>
          <div
            className="geg-mono"
            style={{ fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', marginBottom: 3 }}
          >
            {k}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--color-geg-text-2)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
            {String(v)}
          </div>
        </div>
      ))}
    </div>
  )
}
