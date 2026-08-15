import type { DcAdsLpSummary } from '@/lib/db/dc-ads-summary'
import type { VideoMetrics } from '@/lib/db/funnel-lp'

// DC Ads page — inline Ads + Landing-Page summary, the Hub's
// AdsLpSummarySection shaped to the DC funnel (Drake 2026-08-13). Same three
// blocks and visual grammar as components/sales/ads-lp-summary.tsx (the
// presentational helpers are duplicated from there — the two pages must be
// free to drift apart); differences:
//   - no qualified/non-qualified split (the DC forms' qualification rules
//     aren't defined yet — submits only),
//   - the Videos block renders only what the landing-page registry carries
//     (no video on an LP → the block says so instead of faking zeros),
//   - Typeform starts/completion are omitted, not dashed out (Insights API
//     isn't mirrored — same gap as the Hub, less dead ink).

const fmtUsd = (v: number | null): string =>
  v == null ? '—' : v.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmtCount = (v: number | null): string => (v == null ? '—' : Math.round(v).toLocaleString('en-US'))
const fmtPct = (v: number | null): string => (v == null ? '—' : `${v.toFixed(1)}%`)
const fmtDec = (v: number | null): string => (v == null ? '—' : v.toFixed(2))
const fmtFrac = (v: number | null): string => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

function fmtDuration(sec: number | null): string {
  if (sec == null || sec <= 0) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec - m * 60)
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

function fmtWatch(sec: number): string {
  if (sec <= 0) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  const h = Math.floor(sec / 3600)
  const m = Math.round((sec - h * 3600) / 60)
  return `${h}h ${m.toString().padStart(2, '0')}m`
}

export function DcAdsLpSummarySection({ summary }: { summary: DcAdsLpSummary }) {
  const { ads, vsl, confirm } = summary
  const costPer = (n: number | null | undefined): string | undefined =>
    ads.adspend == null || n == null || n <= 0 ? undefined : fmtUsd(ads.adspend / n)
  return (
    <div style={{ marginTop: 28 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 12 }}
      >
        Ads &amp; landing page
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        <Block title="Meta ads">
          <Row label="Adspend" value={fmtUsd(ads.adspend)} />
          <Row label="Impressions" value={fmtCount(ads.impressions)} />
          <Row label="Unique link clicks" value={fmtCount(ads.uniqueClicks)} />
          <Row label="CTR" value={fmtPct(ads.ctr)} />
          <Row label="CPM" value={fmtUsd(ads.cpm)} />
          <Row label="Cost / unique click" value={fmtUsd(ads.cpcUnique)} />
          <Row label="Frequency" value={fmtDec(ads.frequency)} />
        </Block>

        <Block title={`Landing page · ${summary.lpLabel}`}>
          <Row
            label="LP visits"
            value={fmtCount(summary.lpVisits)}
            hint={summary.cascadeScoped ? 'unique link clicks · selected ads' : 'Meta unique link clicks'}
            cost={costPer(summary.lpVisits)}
          />
          <Row label="LP conversion" value={fmtPct(summary.lpConversionPct)} hint="submits ÷ visits" />
          {summary.typeformSubmits != null ? (
            <>
              <Divider label="Typeform" name={summary.typeformLabel ?? undefined} />
              <Row
                label="Submissions"
                value={fmtCount(summary.typeformSubmits)}
                hint={summary.cascadeScoped ? 'attributed to selection' : undefined}
                cost={costPer(summary.typeformSubmits)}
              />
            </>
          ) : (
            <div
              className="geg-mono"
              style={{ marginTop: 10, fontSize: 9.5, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.6 }}
            >
              No Typeform on this path — the Meta instant form is the opt-in.
            </div>
          )}
        </Block>

        <Block title="Videos">
          {vsl ? (
            <>
              <Divider label="VSL on LP" name={vsl.label} />
              <VideoRows v={vsl} />
            </>
          ) : (
            <div
              className="geg-mono"
              style={{ fontSize: 9.5, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.6 }}
            >
              No video registered for this selection — videos attach
              automatically once Wistia sees them play on a registered page.
            </div>
          )}
          {confirm ? (
            <>
              <Divider label="Confirmation video" name={confirm.label} />
              <VideoRows v={confirm} />
            </>
          ) : null}
        </Block>
      </div>

      {summary.cascadeScoped ? (
        <div
          className="geg-mono"
          style={{ marginTop: 8, fontSize: 9, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.7 }}
        >
          Landing-page numbers follow your campaign/ad selection: visits are the selected ads&apos;
          unique link clicks, and submissions count only those carrying the selection&apos;s ad tags —
          roughly 1 in 6 arrives without tags (return visits, rep-sent links) and is excluded here,
          so this reads slightly lower than the whole-page count.
          {summary.lpVariantNote ? (
            <>
              {' '}
              With a landing page also selected, visits stay the selection&apos;s TOTAL clicks — Meta
              can&apos;t split a campaign&apos;s clicks between LP variants (only matters on split
              tests).
            </>
          ) : null}
        </div>
      ) : null}

      {vsl ? (
        <div
          className="geg-mono"
          style={{ marginTop: 8, fontSize: 9, letterSpacing: '0.06em', color: 'var(--color-geg-text-faint)', lineHeight: 1.7 }}
        >
          Video stats are per-video across every page it plays on (Wistia) — the same VSL runs on
          both DC funnels, so a landing-page selection scopes which videos show, not where they were
          watched.
        </div>
      ) : null}
    </div>
  )
}

function VideoRows({ v }: { v: VideoMetrics }) {
  return (
    <>
      <Row label="Visits" value={fmtCount(v.visits)} />
      <Row label="Plays" value={fmtCount(v.totalPlays)} />
      <Row label="Play rate" value={v.playRate != null ? `${(v.playRate * 100).toFixed(1)}%` : '—'} />
      <Row label="Time played" value={fmtWatch(v.timePlayedSec)} />
      <Row label="Engagement" value={fmtFrac(v.engagementRate)} />
      <Row label="Avg view duration" value={fmtDuration(v.avgViewDurationSec)} />
    </>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        background: 'var(--color-geg-bg-elev)',
        border: '1px solid var(--color-geg-border)',
        borderRadius: 10,
        padding: '14px 16px',
      }}
    >
      <div
        className="geg-mono"
        style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-geg-text-faint)', marginBottom: 8 }}
      >
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>{children}</div>
    </div>
  )
}

function Row({ label, value, hint, cost }: { label: string; value: string; hint?: string; cost?: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: 12,
        padding: '6px 0',
        borderBottom: '1px dashed var(--color-geg-border)',
      }}
    >
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
        <span className="geg-serif" style={{ fontSize: 13.5, color: 'var(--color-geg-text-2)' }}>{label}</span>
        {hint ? (
          <span className="geg-mono" style={{ fontSize: 9, letterSpacing: '0.04em', color: 'var(--color-geg-text-faint)' }}>{hint}</span>
        ) : null}
      </span>
      <span className="geg-numeric-serif" style={{ fontSize: 14, color: 'var(--color-geg-text)', letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>
        {value}
        {cost ? (
          <span className="geg-mono" style={{ fontSize: 10, color: 'var(--color-geg-text-faint)', marginLeft: 5 }}>({cost})</span>
        ) : null}
      </span>
    </div>
  )
}

function Divider({ label, name }: { label: string; name?: string }) {
  const showName = name != null && name !== ''
  return (
    <div
      className="geg-mono"
      style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginTop: 10, marginBottom: 2 }}
    >
      {label}
      {showName ? (
        <span style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--color-geg-text-faint)' }}> · {name}</span>
      ) : null}
    </div>
  )
}
