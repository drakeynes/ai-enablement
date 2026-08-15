// Pure speed-to-lead cohort math — NO server-only imports, so client
// components can re-run it over a filtered subset (the DC Ads page's stacked
// lead-list toggles recompute the speed boxes in the browser). Extracted from
// funnel-appointment-setting.ts (which re-exports these for its existing
// consumers) in the 2026-08-15 boss batch.

// 24h outlier cap: speedSec is business-hours-elapsed, so overnight waits are
// already excluded; the cap guards against a multi-day straggler (24 business
// hours ≈ 2 working days un-dialled) dominating the average.
export const SPEED_CAP_SEC = 24 * 60 * 60

export type CohortStats = {
  cohortSize: number
  leadsCalled: number
  leadsConnected: number
  avgSpeedToLeadSec: number | null
  connectedRate: number | null
  avgIntensity: number | null
}

// The stat inputs are a structural subset of the full roster row so sibling
// cohorts (the DC ads pool — lib/db/dc-ads.ts) reuse the same math without
// building full rows.
export type CohortStatRow = {
  speedSec: number | null
  firstCallAt: string | null
  anyCallConnected: boolean
  intensity: number
}

export function summarizeCohortRows(rows: CohortStatRow[]): CohortStats {
  let cappedSum = 0
  let speedN = 0
  let connectedCount = 0
  let calledCount = 0
  let intensitySum = 0
  for (const r of rows) {
    if (r.speedSec !== null) {
      cappedSum += Math.min(r.speedSec, SPEED_CAP_SEC)
      speedN++
    }
    if (r.firstCallAt) {
      calledCount++
      intensitySum += r.intensity // CALLED leads only (uncalled = 0, would drag the mean)
    }
    if (r.anyCallConnected) connectedCount++
  }
  return {
    cohortSize: rows.length,
    leadsCalled: calledCount,
    leadsConnected: connectedCount,
    avgSpeedToLeadSec: speedN > 0 ? cappedSum / speedN : null,
    connectedRate: calledCount > 0 ? connectedCount / calledCount : null,
    avgIntensity: calledCount > 0 ? intensitySum / calledCount : null,
  }
}
