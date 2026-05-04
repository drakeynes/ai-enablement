'use client'

// Section 6 — Adoption & Programs.
//
// Two enum fields, two three-state booleans, plus the Upsells list
// (read-only display; editing upsells is a future feature). Enums and
// booleans both edit via the generic EditableField → updateClientField
// path with type-narrowing in the Server Action.

import type { ClientDetail } from '@/lib/db/clients'
import { TRUSTPILOT_OPTIONS } from '@/lib/client-vocab'
import { Section, Subsection } from './section'
import { EditableField } from './editable-field'
import { updateClientField } from '@/app/(authenticated)/clients/[id]/actions'

const GHL_OPTIONS = [
  { value: 'never_adopted', label: 'Never adopted' },
  { value: 'affiliate', label: 'Affiliate' },
  { value: 'saas', label: 'SaaS' },
  { value: 'inactive', label: 'Inactive' },
]

type Upsell = ClientDetail['upsells'][number]

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
            <span className="text-sm tabular-nums">{amount ?? '—'}</span>
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
        <EditableField
          label="Trustpilot status"
          value={client.trustpilot_status}
          variant="enum"
          options={TRUSTPILOT_OPTIONS}
          onSave={(v) =>
            updateClientField(
              client.id,
              'trustpilot_status',
              v as string | null,
            )
          }
        />
        <EditableField
          label="GHL adoption"
          value={client.ghl_adoption}
          variant="enum"
          options={GHL_OPTIONS}
          onSave={(v) =>
            updateClientField(
              client.id,
              'ghl_adoption',
              v as string | null,
            )
          }
        />
        <EditableField
          label="Sales group candidate"
          value={client.sales_group_candidate}
          variant="three_state_bool"
          onSave={(v) =>
            updateClientField(
              client.id,
              'sales_group_candidate',
              v as boolean | null,
            )
          }
        />
        <EditableField
          label="DFY setting"
          value={client.dfy_setting}
          variant="three_state_bool"
          onSave={(v) =>
            updateClientField(
              client.id,
              'dfy_setting',
              v as boolean | null,
            )
          }
        />
      </div>

      <Subsection title={`Upsells (${client.upsells.length})`}>
        <UpsellsList upsells={client.upsells} />
      </Subsection>
    </Section>
  )
}
