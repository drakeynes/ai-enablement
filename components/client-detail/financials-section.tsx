// Section 3 — Financials.
//
// Dollar amounts render as $X,XXX.XX. Arrears renders as $0.00 when the
// column is at its default — that's correct (the migration set
// not null default 0). Distinguishing "0 because we set it" from "0
// because we never imported a value" is not a V1 concern; if it ever
// becomes one, we'd switch arrears to nullable and re-derive the import
// rule.

import type { ClientDetail } from '@/lib/db/clients'
import { Section } from './section'
import { ReadOnlyField } from './read-only-field'

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

export function FinancialsSection({ client }: { client: ClientDetail }) {
  return (
    <Section title="Financials">
      <div className="grid grid-cols-2 gap-4">
        <ReadOnlyField
          label="Contracted revenue"
          value={formatDollars(client.contracted_revenue)}
        />
        <ReadOnlyField
          label="Upfront cash collected"
          value={formatDollars(client.upfront_cash_collected)}
        />

        <ReadOnlyField
          label="Arrears"
          value={formatDollars(client.arrears)}
        />
        <ReadOnlyField label="Arrears note" value={client.arrears_note} />
      </div>
    </Section>
  )
}
