// Section 2 — Lifecycle & Standing.
//
// CSM-judgment fields (journey_stage, csm_standing, archetype) plus
// system-derived signals (latest NPS, Health Score, Concerns).
//
// HealthScoreIndicator and ConcernsIndicator preserve the rendering
// from the previous detail page — they were carefully designed against
// the locked client_health_scores.factors jsonb shape and shouldn't
// be rewritten.
//
// Concerns is a collapsible sub-section under Health Score. Empty
// states distinguish "no health record" (not yet evaluated) from
// "health record exists but no concerns" (either the flag is off
// or this client had nothing to flag) — per the warning in the B1
// prompt.

import Link from 'next/link'
import type { ClientDetail } from '@/lib/db/clients'
import { Section, Subsection } from './section'
import { ReadOnlyField } from './read-only-field'

type ConcernShape = {
  text: string
  severity?: 'low' | 'medium' | 'high'
  source_call_ids?: string[]
}

function HealthScoreIndicator({
  health,
}: {
  health: ClientDetail['latest_health']
}) {
  if (!health) {
    return (
      <p className="text-sm text-muted-foreground">
        No score yet — Gregory writes scores on the weekly cron run; new
        clients land here after their first sweep.
      </p>
    )
  }
  const tierCls =
    health.tier === 'green'
      ? 'bg-emerald-100 text-emerald-900'
      : health.tier === 'yellow'
        ? 'bg-amber-100 text-amber-900'
        : 'bg-rose-100 text-rose-900'
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className="text-3xl font-semibold">{health.score}</span>
        <span
          className={`rounded-full border px-2 py-0.5 text-xs font-medium ${tierCls}`}
        >
          {health.tier}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        Last computed {new Date(health.computed_at).toLocaleString()}
      </p>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          Why this score
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted/50 p-2 text-xs">
          {JSON.stringify(health.factors, null, 2)}
        </pre>
      </details>
    </div>
  )
}

function ConcernsBlock({ health }: { health: ClientDetail['latest_health'] }) {
  // No health record at all — Gregory hasn't run for this client.
  if (!health) {
    return (
      <p className="text-sm text-muted-foreground">
        Gregory has not yet evaluated this client.
      </p>
    )
  }

  // Health record exists; pull the concerns array from factors. Empty
  // when the flag is off OR when Gregory ran but surfaced none.
  const factorsObj =
    typeof health.factors === 'object' && health.factors
      ? (health.factors as { concerns?: ConcernShape[] })
      : null
  const concerns = factorsObj?.concerns ?? []

  if (concerns.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No concerns currently surfaced.
      </p>
    )
  }

  return (
    <ul className="space-y-2 text-sm">
      {concerns.map((concern, idx) => {
        const sevCls =
          concern.severity === 'high'
            ? 'bg-rose-100 text-rose-900'
            : concern.severity === 'medium'
              ? 'bg-amber-100 text-amber-900'
              : 'bg-zinc-100 text-zinc-700'
        return (
          <li key={idx} className="space-y-1">
            <div className="flex items-start gap-2">
              {concern.severity ? (
                <span
                  className={`shrink-0 rounded-full border px-1.5 py-0.5 text-xs ${sevCls}`}
                >
                  {concern.severity}
                </span>
              ) : null}
              <span>{concern.text}</span>
            </div>
            {concern.source_call_ids && concern.source_call_ids.length > 0 ? (
              <div className="text-xs text-muted-foreground pl-1">
                Source:{' '}
                {concern.source_call_ids.map((callId, i) => (
                  <span key={callId}>
                    <Link
                      href={`/calls/${callId}`}
                      className="hover:underline underline-offset-4"
                    >
                      call {i + 1}
                    </Link>
                    {i < (concern.source_call_ids?.length ?? 0) - 1 ? ', ' : ''}
                  </span>
                ))}
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

export function LifecycleSection({ client }: { client: ClientDetail }) {
  return (
    <Section title="Lifecycle & Standing">
      <div className="grid grid-cols-2 gap-4">
        <ReadOnlyField
          label="Journey stage"
          value={client.journey_stage}
        >
          {client.journey_stage ?? (
            <span className="text-muted-foreground">
              — <span className="text-xs">(stage taxonomy in design — free-text for now)</span>
            </span>
          )}
        </ReadOnlyField>
        <ReadOnlyField label="CSM standing" value={client.csm_standing} />

        <ReadOnlyField
          label="Latest NPS"
          value={client.latest_nps?.score ?? null}
        />
        <ReadOnlyField label="Archetype" value={client.archetype} />
      </div>

      <div className="space-y-2 pt-2">
        <h3 className="text-sm font-medium text-muted-foreground">Health score</h3>
        <HealthScoreIndicator health={client.latest_health} />
      </div>

      <Subsection title="Concerns">
        <ConcernsBlock health={client.latest_health} />
      </Subsection>
    </Section>
  )
}
