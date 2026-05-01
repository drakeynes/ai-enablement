// Section 1 — Identity & Contact.
//
// Read-only-with-affordance for fields that B2 will wire up to edit.
// Truly read-only (no affordance) for the three system-derived
// references: Slack channel id, Slack user id, signup date.
//
// Alternate emails come from clients.metadata->'alternate_emails' —
// populated by the merge feature (M3.2) and the Fathom client resolver.
// Render as a comma-separated list; null/empty handled at the field
// level.

import type { ClientDetail } from '@/lib/db/clients'
import { Section } from './section'
import { ReadOnlyField } from './read-only-field'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export function IdentitySection({ client }: { client: ClientDetail }) {
  const metadata = (client.metadata ?? {}) as Record<string, unknown>
  const alternateEmails = Array.isArray(metadata.alternate_emails)
    ? (metadata.alternate_emails as string[])
    : []
  const altEmailsDisplay = alternateEmails.length === 0 ? null : alternateEmails.join(', ')

  const birthYearDisplay = client.birth_year ? `Born ${client.birth_year}` : null

  const startDateDisplay = client.start_date
    ? new Date(client.start_date).toLocaleDateString()
    : null

  return (
    <Section title="Identity & Contact">
      <div className="grid grid-cols-2 gap-4">
        <ReadOnlyField label="Full name" value={client.full_name} />
        <ReadOnlyField label="Status" value={client.status} />

        <ReadOnlyField
          label="Primary CSM"
          value={client.active_primary_csm?.team_member_name ?? null}
        />
        <ReadOnlyField
          label="Email"
          value={client.email}
          mono
        />

        <ReadOnlyField
          label="Alternate emails"
          value={altEmailsDisplay}
          mono
        />
        <ReadOnlyField label="Phone" value={client.phone} />

        <ReadOnlyField label="Country" value={client.country} />
        <ReadOnlyField label="Time zone" value={client.timezone} />

        <ReadOnlyField label="Birth year" value={birthYearDisplay} />
        <ReadOnlyField label="Location" value={client.location} />

        <ReadOnlyField label="Occupation" value={client.occupation} />

        {/* Truly read-only — system-sourced references */}
        <ReadOnlyField
          label="Slack channel id"
          value={client.slack_channel_id}
          editable={false}
          mono
        />
        <ReadOnlyField
          label="Slack user id"
          value={client.slack_user_id}
          editable={false}
          mono
        />
        <ReadOnlyField
          label="Signup date"
          value={startDateDisplay}
          editable={false}
        />

        <div className="col-span-2">
          <ReadOnlyField label="Tags">
            {client.tags.length === 0 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {client.tags.map((tag) => {
                  const isReview = tag === 'needs_review'
                  return (
                    <Badge
                      key={tag}
                      className={cn(
                        'border font-normal',
                        isReview
                          ? 'bg-amber-100 text-amber-900 border-amber-200'
                          : 'bg-zinc-100 text-zinc-700 border-zinc-200',
                      )}
                    >
                      {tag}
                    </Badge>
                  )
                })}
              </div>
            )}
          </ReadOnlyField>
        </div>
      </div>
    </Section>
  )
}
