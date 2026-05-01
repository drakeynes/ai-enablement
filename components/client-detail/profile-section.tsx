// Section 5 — Profile & Background.
//
// All five fields live in clients.metadata.profile, NOT as columns on
// clients. The schema spec deliberately keeps these in jsonb because
// the value set may evolve (per the metadata column comment in 0001:
// "Long tail of attributes — promote to columns later").
//
// Defensive accessors throughout — metadata may be null, may not have
// the profile sub-object, may have malformed types. Read what's
// readable, render "—" for everything else.

import type { ClientDetail } from '@/lib/db/clients'
import { Section } from './section'
import { ReadOnlyField } from './read-only-field'

type ProfileShape = {
  niche?: unknown
  offer?: unknown
  traffic_strategy?: unknown
  swot?: {
    strengths?: unknown
    weaknesses?: unknown
    opportunities?: unknown
    threats?: unknown
  }
}

function asString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function ProfileSection({ client }: { client: ClientDetail }) {
  const metadata = (client.metadata ?? {}) as Record<string, unknown>
  const profile = (metadata.profile ?? {}) as ProfileShape
  const swot = (profile.swot ?? {}) as ProfileShape['swot']

  return (
    <Section title="Profile & Background">
      <div className="space-y-3">
        <ReadOnlyField label="Niche" value={asString(profile.niche)} />
        <ReadOnlyField label="Offer" value={asString(profile.offer)} />
        <ReadOnlyField
          label="Traffic strategy"
          value={asString(profile.traffic_strategy)}
        />
      </div>

      <div className="space-y-2 pt-2">
        <h3 className="text-sm font-medium text-muted-foreground">SWOT</h3>
        <div className="grid grid-cols-2 gap-3">
          <ReadOnlyField
            label="Strengths"
            value={asString(swot?.strengths)}
          />
          <ReadOnlyField
            label="Weaknesses"
            value={asString(swot?.weaknesses)}
          />
          <ReadOnlyField
            label="Opportunities"
            value={asString(swot?.opportunities)}
          />
          <ReadOnlyField label="Threats" value={asString(swot?.threats)} />
        </div>
      </div>
    </Section>
  )
}
