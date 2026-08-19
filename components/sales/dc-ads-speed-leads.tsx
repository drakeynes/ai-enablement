'use client'

import { useEffect, useMemo, useState } from 'react'

import type { DcAdsLeadRow } from '@/lib/db/dc-ads'
import { summarizeCohortRows } from '@/lib/db/cohort-stats'
import { SpeedToLeadBoxes } from './speed-to-lead-boxes'
import { DcAdsSpeedExtras } from './dc-ads-speed-extras'
import {
  DcAdsLeadsSection,
  matchesToggles,
  type Disposition,
  type QualKey,
} from './dc-ads-leads'

// DC ads — the speed-to-lead boxes + the embedded lead roster under ONE
// client wrapper (boss batch 2026-08-15, item 4): the stacked lead-list
// toggles filter a single per-lead row set (dc_ads_lead_roster, 0145), and
// every speed number above recomputes over the same filtered subset — the
// boxes and the list can never disagree. With no toggles active the numbers
// equal the old whole-window ones (same rows, same 12p–12a ET clock math —
// timeToDialSec is computed server-side in lib/db/dc-ads.ts with the same
// businessHoursElapsedSec the retired dc_ads_speed_cohort() path used).
//
// Spend is the one exception: it has no per-lead attribution, so CPU's
// numerator stays the whole-window adspend while its units denominator
// follows the toggles — footnoted below the boxes.

export function DcAdsSpeedLeadsSection({
  rows,
  lpLabels,
  spendUsd,
  clockLabel,
  initialDispSel,
  initialQualSel,
}: {
  rows: DcAdsLeadRow[]
  lpLabels: Record<string, string>
  spendUsd: number
  clockLabel: string
  // Deep-link presets (?ld= / ?lq=, parsed by the page) — the daily/ad
  // tables' stage counts link here with the matching toggles lit.
  initialDispSel?: Disposition[]
  initialQualSel?: QualKey[]
}) {
  const [dispSel, setDispSel] = useState<ReadonlySet<Disposition>>(new Set(initialDispSel ?? []))
  const [qualSel, setQualSel] = useState<ReadonlySet<QualKey>>(new Set(initialQualSel ?? []))

  // Stage-drill landing: the page STREAMS (loading skeleton first), so the
  // browser evaluates #leads before this section exists and silently gives
  // up. Re-scroll once we're actually mounted.
  useEffect(() => {
    if (window.location.hash === '#leads') {
      document.getElementById('leads')?.scrollIntoView({ block: 'start' })
    }
  }, [])

  const toggleIn = <T,>(set: ReadonlySet<T>, key: T): ReadonlySet<T> => {
    const next = new Set(set)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  }

  const filtered = useMemo(
    () => rows.filter((r) => matchesToggles(r, dispSel, qualSel)),
    [rows, dispSel, qualSel],
  )
  const filterActive = dispSel.size > 0 || qualSel.size > 0

  const stats = useMemo(() => {
    const cohort = summarizeCohortRows(
      filtered.map((r) => ({
        speedSec: r.timeToDialSec,
        firstCallAt: r.firstDial,
        anyCallConnected: r.connected,
        intensity: r.dials,
      })),
    )
    const speeds = filtered
      .map((r) => r.timeToDialSec)
      .filter((s): s is number => s !== null)
      .sort((a, b) => a - b)
    const under = (min: number) => speeds.filter((s) => s < min * 60).length
    const medianSec =
      speeds.length === 0
        ? null
        : speeds.length % 2
          ? speeds[(speeds.length - 1) / 2]
          : (speeds[speeds.length / 2 - 1] + speeds[speeds.length / 2]) / 2
    const count = (p: (r: DcAdsLeadRow) => boolean) => filtered.filter(p).length
    return {
      cohort,
      connectedBroad: count((r) => r.connected),
      dialedOrConnected: count((r) => r.firstDial != null || r.connected),
      smsEngaged: count((r) => r.sms),
      smsTexted: count((r) => r.smsOut || r.sms),
      under1: under(1),
      under5: under(5),
      under10: under(10),
      under30: under(30),
      over30: speeds.length - under(30),
      never: filtered.length - speeds.length,
      medianSec,
      closed: count((r) => r.closed),
      qualified: count((r) => r.qualState === 'qualified'),
      unqualified: count((r) => r.qualState === 'unqualified'),
      unqualifiedClosed: count((r) => r.qualState === 'unqualified' && r.closed),
      hvc: count((r) => r.hvc),
      units: filtered.reduce((a, r) => a + (r.units ?? 0), 0),
    }
  }, [filtered])

  return (
    <>
      <div id="leads" style={{ marginTop: 26, scrollMarginTop: 80 }}>
        <div
          className="geg-mono"
          style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 10 }}
        >
          Speed to lead · DC ad opt-ins · selected dates
          {filterActive ? ` · filtered by toggles (${filtered.length} of ${rows.length} leads)` : ''}
        </div>
        <SpeedToLeadBoxes
          cohort={stats.cohort}
          connectedLeads={stats.connectedBroad}
          connectedDenominator={stats.dialedOrConnected}
          clockLabel={clockLabel}
          sms={{ engaged: stats.smsEngaged, texted: stats.smsTexted }}
          connectedHint="of leads dialed · calls ≥90s only"
        />
        <DcAdsSpeedExtras
          cohort={filtered.length}
          under1={stats.under1}
          under5={stats.under5}
          under10={stats.under10}
          under30={stats.under30}
          over30={stats.over30}
          never={stats.never}
          medianSec={stats.medianSec}
          closed={stats.closed}
          qualified={stats.qualified}
          unqualified={stats.unqualified}
          unqualifiedClosed={stats.unqualifiedClosed}
          hvc={stats.hvc}
          connected={stats.connectedBroad}
          units={stats.units}
          spendUsd={spendUsd}
        />
        {filterActive ? (
          <div
            className="geg-mono"
            style={{ marginTop: 8, fontSize: 9, letterSpacing: '0.05em', color: 'var(--color-geg-text-faint)', lineHeight: 1.6 }}
          >
            Every box recomputes over the toggled subset. CPU is the exception: adspend can&apos;t be
            attributed per lead, so its numerator stays the whole window while the units follow the
            toggles — read it as an upper bound under a filter.
          </div>
        ) : null}
      </div>

      <DcAdsLeadsSection
        rows={rows}
        lpLabels={lpLabels}
        dispSel={dispSel}
        qualSel={qualSel}
        onToggleDisp={(d) => setDispSel((s) => toggleIn(s, d))}
        onToggleQual={(q) => setQualSel((s) => toggleIn(s, q))}
      />
    </>
  )
}
