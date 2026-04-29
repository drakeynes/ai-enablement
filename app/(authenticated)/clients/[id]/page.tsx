import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getClientById, type ClientDetail } from '@/lib/db/clients'
import { listMergeCandidates } from '@/lib/db/merge'
import { Separator } from '@/components/ui/separator'
import { Label } from '@/components/ui/label'
import {
  StatusPill,
  JourneyStagePill,
  NeedsReviewPill,
} from '../pills'
import {
  InlineTextField,
  InlineSelectField,
  InlineDateField,
  InlineTextarea,
  TagsField,
} from './inline-fields'
import { PrimaryCsmField } from './primary-csm-field'
import { MergeClientButton } from './merge-client-button'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'ghost', label: 'Ghost' },
  { value: 'churned', label: 'Churned' },
]

const JOURNEY_STAGE_OPTIONS = [
  { value: 'onboarding', label: 'Onboarding' },
  { value: 'active', label: 'Active' },
  { value: 'churning', label: 'Churning' },
  { value: 'churned', label: 'Churned' },
  { value: 'alumni', label: 'Alumni' },
]

function SectionHeader({ title }: { title: string }) {
  return <h2 className="text-lg font-semibold">{title}</h2>
}

function daysSince(iso: string | null): number | null {
  if (!iso) return null
  const ms = Date.now() - new Date(iso).getTime()
  return Math.floor(ms / (1000 * 60 * 60 * 24))
}

// ----------------------------------------------------------------------
// Indicators (Section 4)
// ----------------------------------------------------------------------
function IndicatorCard({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="border rounded-md p-4 space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      <div>{children}</div>
    </div>
  )
}

function HealthScoreIndicator({
  health,
}: {
  health: ClientDetail['latest_health']
}) {
  if (!health) {
    return (
      <p className="text-sm text-muted-foreground">
        No score yet — Gregory will populate this in V1.1.
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

function CallCadenceIndicator({ lastCallDate }: { lastCallDate: string | null }) {
  const days = daysSince(lastCallDate)
  if (days === null) {
    return (
      <p className="text-sm text-muted-foreground">No calls yet for this client.</p>
    )
  }
  const cls =
    days < 14
      ? 'text-emerald-700'
      : days < 30
        ? 'text-amber-700'
        : 'text-rose-700'
  const label =
    days === 0 ? 'Today' : days === 1 ? '1 day ago' : `${days} days ago`
  return <p className={`text-2xl font-semibold ${cls}`}>{label}</p>
}

type ConcernShape = {
  text: string
  severity?: 'low' | 'medium' | 'high'
  source_call_ids?: string[]
}

function ConcernsIndicator({
  health,
}: {
  health: ClientDetail['latest_health']
}) {
  const concerns =
    health && typeof health.factors === 'object' && health.factors
      ? ((health.factors as { concerns?: ConcernShape[] }).concerns ?? [])
      : []
  if (concerns.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No concerns surfaced — Gregory will populate this in V1.1.
      </p>
    )
  }
  return (
    <ul className="space-y-1.5 text-sm">
      {concerns.map((concern, idx) => {
        const sevCls =
          concern.severity === 'high'
            ? 'bg-rose-100 text-rose-900'
            : concern.severity === 'medium'
              ? 'bg-amber-100 text-amber-900'
              : 'bg-zinc-100 text-zinc-700'
        return (
          <li key={idx} className="flex items-start gap-2">
            {concern.severity ? (
              <span
                className={`shrink-0 rounded-full border px-1.5 py-0.5 text-xs ${sevCls}`}
              >
                {concern.severity}
              </span>
            ) : null}
            <span>{concern.text}</span>
          </li>
        )
      })}
    </ul>
  )
}

function NpsIndicator({ nps }: { nps: ClientDetail['latest_nps'] }) {
  if (!nps) {
    return <p className="text-sm text-muted-foreground">No NPS data yet.</p>
  }
  const days = daysSince(nps.submitted_at)
  return (
    <div className="space-y-1">
      <span className="text-3xl font-semibold">{nps.score}</span>
      <p className="text-xs text-muted-foreground">
        Submitted {days === 0 ? 'today' : days === 1 ? '1 day ago' : `${days} days ago`}
      </p>
    </div>
  )
}

// ----------------------------------------------------------------------
// Recent calls (Section 5)
// ----------------------------------------------------------------------
function RecentCalls({ calls }: { calls: ClientDetail['recent_calls'] }) {
  if (calls.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No calls yet for this client.</p>
    )
  }
  return (
    <ul className="space-y-2">
      {calls.map((call) => (
        <li key={call.id} className="flex items-baseline gap-3 text-sm">
          <span className="text-muted-foreground tabular-nums w-28 shrink-0">
            {new Date(call.started_at).toLocaleDateString()}
          </span>
          <Link
            href={`/calls/${call.id}`}
            className="flex-1 hover:underline underline-offset-4 truncate"
          >
            {call.title ?? 'Untitled call'}
          </Link>
          <span className="text-xs text-muted-foreground capitalize">
            {call.call_category}
          </span>
          {call.duration_seconds ? (
            <span className="text-xs text-muted-foreground tabular-nums">
              {Math.round(call.duration_seconds / 60)}m
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

// ----------------------------------------------------------------------
// Open action items (Section 6)
// ----------------------------------------------------------------------
function OpenActionItems({
  items,
}: {
  items: ClientDetail['open_action_items']
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No open action items.</p>
  }
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return (
    <ul className="space-y-2">
      {items.map((item) => {
        const overdue =
          item.due_date !== null && new Date(item.due_date) < today
        return (
          <li key={item.id} className="text-sm">
            <div className="flex items-start gap-3">
              <span className="flex-1">{item.description}</span>
              {item.due_date ? (
                <span
                  className={`text-xs tabular-nums ${
                    overdue ? 'text-rose-700 font-medium' : 'text-muted-foreground'
                  }`}
                >
                  {new Date(item.due_date).toLocaleDateString()}
                  {overdue ? ' (overdue)' : ''}
                </span>
              ) : null}
              <Link
                href={`/calls/${item.call_id}`}
                className="text-xs text-muted-foreground hover:underline underline-offset-4"
              >
                source
              </Link>
            </div>
            <p className="text-xs text-muted-foreground">
              Owner: {item.owner_type}
            </p>
          </li>
        )
      })}
    </ul>
  )
}

// ----------------------------------------------------------------------
// Page entry
// ----------------------------------------------------------------------
export default async function ClientDetailPage({
  params,
}: {
  params: { id: string }
}) {
  const client = await getClientById(params.id)
  if (!client) {
    notFound()
  }

  const teamMemberOptions = client.team_members.map((member) => ({
    id: member.id,
    full_name: member.full_name,
  }))

  const hasNeedsReview = client.tags.includes('needs_review')
  const mergeCandidates = hasNeedsReview
    ? await listMergeCandidates(client.id)
    : []

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/clients" className="text-sm text-muted-foreground hover:underline">
          ← Back to Clients
        </Link>
      </div>

      <div className="space-y-1.5">
        <h1 className="text-3xl font-semibold">{client.full_name}</h1>
        <div className="flex flex-wrap gap-2 items-center">
          <StatusPill status={client.status} />
          <JourneyStagePill stage={client.journey_stage} />
          {hasNeedsReview ? (
            <>
              <NeedsReviewPill />
              <MergeClientButton
                sourceId={client.id}
                sourceFullName={client.full_name}
                candidates={mergeCandidates}
              />
            </>
          ) : null}
        </div>
      </div>

      <Separator />

      {/* Section 1 — Identity */}
      <section className="space-y-3">
        <SectionHeader title="Identity" />
        <div className="grid grid-cols-2 gap-4">
          <InlineTextField
            clientId={client.id}
            field="full_name"
            initialValue={client.full_name}
            label="Full name"
          />
          <InlineTextField
            clientId={client.id}
            field="email"
            initialValue={client.email}
            type="email"
            label="Email"
          />
          <InlineTextField
            clientId={client.id}
            field="phone"
            initialValue={client.phone}
            type="tel"
            label="Phone"
          />
          <InlineTextField
            clientId={client.id}
            field="timezone"
            initialValue={client.timezone}
            label="Timezone"
            placeholder="e.g. America/Los_Angeles"
          />
          <div className="space-y-1.5 col-span-2">
            <Label>Slack user ID</Label>
            <p className="text-sm text-muted-foreground font-mono">
              {client.slack_user_id ?? '—'}
            </p>
          </div>
        </div>
      </section>

      <Separator />

      {/* Section 2 — Status */}
      <section className="space-y-3">
        <SectionHeader title="Status" />
        <div className="grid grid-cols-2 gap-4">
          <InlineSelectField
            clientId={client.id}
            field="status"
            initialValue={client.status}
            options={STATUS_OPTIONS}
            label="Status"
          />
          <InlineSelectField
            clientId={client.id}
            field="journey_stage"
            initialValue={client.journey_stage}
            options={JOURNEY_STAGE_OPTIONS}
            label="Journey stage"
          />
          <InlineTextField
            clientId={client.id}
            field="program_type"
            initialValue={client.program_type}
            label="Program type"
            placeholder="e.g. 9k_consumer"
          />
          <InlineDateField
            clientId={client.id}
            field="start_date"
            initialValue={client.start_date}
            label="Start date"
          />
          <div className="col-span-2">
            <TagsField clientId={client.id} initialTags={client.tags} />
          </div>
        </div>
      </section>

      <Separator />

      {/* Section 3 — Primary CSM */}
      <section className="space-y-3">
        <SectionHeader title="Primary CSM" />
        <PrimaryCsmField
          clientId={client.id}
          currentTeamMemberId={client.active_primary_csm?.team_member_id ?? null}
          currentTeamMemberName={
            client.active_primary_csm?.team_member_name ?? null
          }
          assignedAt={client.active_primary_csm?.assigned_at ?? null}
          options={teamMemberOptions}
        />
      </section>

      <Separator />

      {/* Section 4 — Indicators (Gregory's surface) */}
      <section className="space-y-3">
        <SectionHeader title="Indicators" />
        <div className="grid grid-cols-2 gap-3">
          <IndicatorCard title="Health score">
            <HealthScoreIndicator health={client.latest_health} />
          </IndicatorCard>
          <IndicatorCard title="Call cadence">
            <CallCadenceIndicator
              lastCallDate={
                client.recent_calls[0]?.started_at ?? null
              }
            />
          </IndicatorCard>
          <IndicatorCard title="Concerns">
            <ConcernsIndicator health={client.latest_health} />
          </IndicatorCard>
          <IndicatorCard title="NPS">
            <NpsIndicator nps={client.latest_nps} />
          </IndicatorCard>
        </div>
      </section>

      <Separator />

      {/* Section 5 — Recent calls */}
      <section className="space-y-3">
        <SectionHeader title="Recent calls" />
        <RecentCalls calls={client.recent_calls} />
      </section>

      <Separator />

      {/* Section 6 — Open action items */}
      <section className="space-y-3">
        <SectionHeader title="Open action items" />
        <OpenActionItems items={client.open_action_items} />
      </section>

      <Separator />

      {/* Section 7 — Notes */}
      <section className="space-y-3">
        <SectionHeader title="Notes" />
        <InlineTextarea
          clientId={client.id}
          field="notes"
          initialValue={client.notes}
          label="Free-text notes (plain text in V1)"
          placeholder="Anything worth remembering about this client…"
        />
      </section>
    </div>
  )
}
