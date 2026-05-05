// Section 4 — Activity & Action Items.
//
// System-derived activity metrics + recent calls + the canonical
// action-items list (all statuses, grouped). The "Show all calls"
// expansion reveals calls beyond the first five from the same query
// (no extra round trip — the data layer already returns the full list
// in client.all_calls). Action items collapse when more than 10 exist.
//
// Pipeline-pending placeholders for accountability submissions and
// course content — those data sources don't exist yet.

import Link from 'next/link'
import type { ClientDetail } from '@/lib/db/clients'
import { Section, Subsection } from './section'

type ActionItem = ClientDetail['all_action_items'][number]
type CallSummary = ClientDetail['all_calls'][number]

function StatBlock({
  label,
  value,
  note,
  submeasure,
}: {
  label: string
  value: string | number | null
  note?: string
  // M5.7 — submeasure renders below the headline value as a real sub-line
  // (not italicized like `note`, which is reserved for the "Pipeline pending"
  // placeholder treatment). Used by Total calls to render "X this month".
  submeasure?: string
}) {
  const isEmpty = value === null || value === undefined || value === ''
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`text-2xl font-semibold tabular-nums ${
          isEmpty ? 'text-muted-foreground' : ''
        }`}
      >
        {isEmpty ? '—' : value}
      </p>
      {submeasure ? (
        <p className="text-xs text-muted-foreground tabular-nums">{submeasure}</p>
      ) : null}
      {note ? (
        <p className="text-xs text-muted-foreground italic">{note}</p>
      ) : null}
    </div>
  )
}

function CallsList({ calls }: { calls: CallSummary[] }) {
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

function ActionItemRow({ item }: { item: ActionItem }) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const overdue =
    item.status === 'open' &&
    item.due_date !== null &&
    new Date(item.due_date) < today

  const statusCls =
    item.status === 'open'
      ? 'bg-zinc-100 text-zinc-700'
      : item.status === 'done'
        ? 'bg-emerald-100 text-emerald-900'
        : 'bg-zinc-200 text-zinc-500 line-through'

  return (
    <li className="text-sm space-y-0.5">
      <div className="flex items-start gap-3">
        <span
          className={`shrink-0 rounded-full border px-1.5 py-0.5 text-xs capitalize ${statusCls}`}
        >
          {item.status === 'cancelled' ? 'dropped' : item.status}
        </span>
        <span className={`flex-1 ${item.status !== 'open' ? 'text-muted-foreground' : ''}`}>
          {item.description}
        </span>
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
      <p className="text-xs text-muted-foreground pl-1">
        Owner: {item.owner_type}
        {item.completed_at && item.status === 'done'
          ? ` · completed ${new Date(item.completed_at).toLocaleDateString()}`
          : ''}
      </p>
    </li>
  )
}

function ActionItemsList({ items }: { items: ActionItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No action items for this client.</p>
    )
  }

  // Group by status: open → done → cancelled. Within each group keep
  // the extracted_at desc order from the query.
  const open = items.filter((i) => i.status === 'open')
  const done = items.filter((i) => i.status === 'done')
  const cancelled = items.filter((i) => i.status === 'cancelled')
  const ordered = [...open, ...done, ...cancelled]

  if (ordered.length <= 10) {
    return (
      <ul className="space-y-3">
        {ordered.map((item) => (
          <ActionItemRow key={item.id} item={item} />
        ))}
      </ul>
    )
  }

  // > 10 items: show first 10, hide the rest behind a <details> toggle
  // (default closed for less visual noise).
  const head = ordered.slice(0, 10)
  const tail = ordered.slice(10)
  return (
    <div className="space-y-3">
      <ul className="space-y-3">
        {head.map((item) => (
          <ActionItemRow key={item.id} item={item} />
        ))}
      </ul>
      <details className="group space-y-3">
        <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
          Show {tail.length} older action item{tail.length === 1 ? '' : 's'}
        </summary>
        <ul className="space-y-3 pt-3">
          {tail.map((item) => (
            <ActionItemRow key={item.id} item={item} />
          ))}
        </ul>
      </details>
    </div>
  )
}

export function ActivitySection({ client }: { client: ClientDetail }) {
  const recentCalls = client.all_calls.slice(0, 5)
  const olderCalls = client.all_calls.slice(5)
  const slackMessagesDisplay =
    client.slack_user_id === null ? null : client.total_slack_messages

  return (
    <Section title="Activity & Action Items">
      <div className="grid grid-cols-3 gap-3">
        <StatBlock
          label="Total calls"
          value={client.total_calls}
          submeasure={`${client.meetings_this_month} this month`}
        />
        <StatBlock label="Total Slack messages" value={slackMessagesDisplay} />
        <StatBlock label="Total NPS submissions" value={client.total_nps_submissions} />
        <StatBlock
          label="Total accountability submissions"
          value={null}
          note="Pipeline pending"
        />
        <StatBlock
          label="Course content consumption"
          value={null}
          note="Pipeline pending"
        />
      </div>

      <div className="space-y-2 pt-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-muted-foreground">Recent calls</h3>
          {client.inactive ? (
            <span
              className="inline-flex items-center rounded-full border border-amber-200 bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900"
              title="No calls in the last 30 days"
            >
              Inactive
            </span>
          ) : null}
        </div>
        <CallsList calls={recentCalls} />
        {olderCalls.length > 0 ? (
          <details className="group space-y-2 pt-1">
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
              Show all calls ({client.total_calls} total)
            </summary>
            <div className="pt-2">
              <CallsList calls={olderCalls} />
            </div>
          </details>
        ) : null}
      </div>

      <Subsection title={`Action items (${client.all_action_items.length})`}>
        <ActionItemsList items={client.all_action_items} />
      </Subsection>
    </Section>
  )
}
