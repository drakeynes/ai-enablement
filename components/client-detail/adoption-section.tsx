// Section 6 — Adoption & Programs.
//
// Trustpilot status, GHL adoption, sales group candidate, DFY setting,
// and the upsells list. All four enum / boolean fields render
// read-only-with-affordance; B2 wires up edit. Upsells list comes from
// client.upsells (sorted sold_at desc nulls last by the data layer).

import type { ClientDetail } from '@/lib/db/clients'
import { Section, Subsection } from './section'
import { ReadOnlyField } from './read-only-field'

type Upsell = ClientDetail['upsells'][number]

function formatThreeStateBoolean(value: boolean | null): string | null {
  if (value === null || value === undefined) return null
  return value ? 'Yes' : 'No'
}

function formatDollars(value: number | string | null): string | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (Number.isNaN(n)) return null
  return n.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function UpsellsList({ upsells }: { upsells: Upsell[] }) {
  if (upsells.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No upsells recorded.</p>
    )
  }
  return (
    <ul className="space-y-2">
      {upsells.map((upsell) => {
        const amount = formatDollars(upsell.amount)
        const soldAt = upsell.sold_at
          ? new Date(upsell.sold_at).toLocaleDateString()
          : null
        return (
          <li key={upsell.id} className="flex items-baseline gap-3 text-sm">
            <span className="text-muted-foreground tabular-nums w-28 shrink-0">
              {soldAt ?? '—'}
            </span>
            <span className="flex-1">
              {upsell.product ?? upsell.notes ?? '(unspecified)'}
            </span>
            <span className="text-sm tabular-nums">
              {amount ?? '—'}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

export function AdoptionSection({ client }: { client: ClientDetail }) {
  return (
    <Section title="Adoption & Programs">
      <div className="grid grid-cols-2 gap-4">
        <ReadOnlyField
          label="Trustpilot status"
          value={client.trustpilot_status}
        />
        <ReadOnlyField
          label="GHL adoption"
          value={client.ghl_adoption}
        />
        <ReadOnlyField
          label="Sales group candidate"
          value={formatThreeStateBoolean(client.sales_group_candidate)}
        />
        <ReadOnlyField
          label="DFY setting"
          value={formatThreeStateBoolean(client.dfy_setting)}
        />
      </div>

      <Subsection title={`Upsells (${client.upsells.length})`}>
        <UpsellsList upsells={client.upsells} />
      </Subsection>
    </Section>
  )
}
