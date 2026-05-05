import Link from 'next/link'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { JourneyStagePill, StatusPill, TagsList } from './pills'
import type { ClientsListRow } from '@/lib/db/clients'

type SortKey =
  | 'full_name'
  | 'status'
  | 'journey_stage'
  | 'primary_csm_name'
  | 'latest_health_score'
  | 'last_call_date'
  | 'open_action_items_count'

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'full_name', label: 'Full name' },
  { key: 'status', label: 'Status' },
  { key: 'journey_stage', label: 'Journey stage' },
  { key: 'primary_csm_name', label: 'Primary CSM' },
  { key: 'latest_health_score', label: 'Health score' },
  { key: 'last_call_date', label: 'Last call' },
  { key: 'open_action_items_count', label: 'Open action items' },
]

function SortableHeader({
  column,
  currentSort,
  currentDir,
  baseSearchParams,
}: {
  column: { key: SortKey; label: string }
  currentSort: string
  currentDir: 'asc' | 'desc'
  baseSearchParams: URLSearchParams
}) {
  const params = new URLSearchParams(baseSearchParams)
  const nextDir =
    currentSort === column.key && currentDir === 'desc' ? 'asc' : 'desc'
  params.set('sort', column.key)
  params.set('dir', nextDir)
  const href = `?${params.toString()}`
  const indicator =
    currentSort === column.key ? (currentDir === 'desc' ? '↓' : '↑') : ''
  return (
    <Link
      href={href}
      className="hover:underline underline-offset-4 inline-flex items-center gap-1"
    >
      {column.label}
      {indicator ? <span className="text-muted-foreground">{indicator}</span> : null}
    </Link>
  )
}

function daysBetween(start: Date, end: Date) {
  const ms = end.getTime() - start.getTime()
  return Math.floor(ms / (1000 * 60 * 60 * 24))
}

function LastCall({
  value,
  meetingsThisMonth,
  inactive,
}: {
  value: string | null
  meetingsThisMonth: number
  inactive: boolean
}) {
  // M5.7 — same primary label as before. Adds two visually-subordinate
  // signals on the same line: "X this mo" (Chunk 3) and an Inactive pill
  // (Chunk 4) when the flag is true. Inactive renders only on flag=true so
  // the cell stays clean by default.
  if (!value) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="text-sm text-muted-foreground">No calls yet</span>
        {inactive ? <InactivePill /> : null}
      </span>
    )
  }
  const days = daysBetween(new Date(value), new Date())
  const cls =
    days < 14
      ? 'text-emerald-700'
      : days < 30
        ? 'text-amber-700'
        : 'text-rose-700'
  const label =
    days === 0 ? 'Today' : days === 1 ? '1 day ago' : `${days} days ago`
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn('text-sm font-medium', cls)}>{label}</span>
      <span className="text-xs text-muted-foreground tabular-nums">
        · {meetingsThisMonth} this mo
      </span>
      {inactive ? <InactivePill /> : null}
    </span>
  )
}

function InactivePill() {
  return (
    <span
      className="inline-flex items-center rounded-full border border-amber-200 bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900"
      title="No calls in the last 30 days"
    >
      Inactive
    </span>
  )
}

function HealthScoreCell({
  score,
  tier,
}: {
  score: number | null
  tier: string | null
}) {
  if (score === null) {
    return (
      <span className="text-muted-foreground text-sm">—</span>
    )
  }
  const tierCls =
    tier === 'green'
      ? 'bg-emerald-100 text-emerald-900 border-emerald-200'
      : tier === 'yellow'
        ? 'bg-amber-100 text-amber-900 border-amber-200'
        : tier === 'red'
          ? 'bg-rose-100 text-rose-900 border-rose-200'
          : 'bg-zinc-100 text-zinc-700 border-zinc-200'
  return (
    <span className="inline-flex items-center gap-2">
      <span className="font-medium">{score}</span>
      <span className={cn('rounded-full border px-2 py-0.5 text-xs', tierCls)}>
        {tier ?? '—'}
      </span>
    </span>
  )
}

function ActionItemsCell({
  open,
  overdue,
}: {
  open: number
  overdue: number
}) {
  if (open === 0) {
    return <span className="text-muted-foreground text-sm">—</span>
  }
  return (
    <span className="text-sm">
      {open} open
      {overdue > 0 ? (
        <span className="text-rose-700 font-medium"> ({overdue} overdue)</span>
      ) : null}
    </span>
  )
}

export function ClientsTable({
  rows,
  sort,
  dir,
  baseSearchParams,
}: {
  rows: ClientsListRow[]
  sort: SortKey
  dir: 'asc' | 'desc'
  baseSearchParams: URLSearchParams
}) {
  if (rows.length === 0) {
    return (
      <div className="border rounded-md p-8 text-center text-muted-foreground">
        No clients match your filters.
      </div>
    )
  }

  return (
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            {SORTABLE_COLUMNS.map((col) => (
              <TableHead key={col.key}>
                <SortableHeader
                  column={col}
                  currentSort={sort}
                  currentDir={dir}
                  baseSearchParams={baseSearchParams}
                />
              </TableHead>
            ))}
            <TableHead>Tags</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id} className="cursor-pointer hover:bg-muted/50">
              <TableCell>
                <Link
                  href={`/clients/${row.id}`}
                  className="font-medium hover:underline underline-offset-4 block"
                >
                  {row.full_name}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  <StatusPill status={row.status} />
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  <JourneyStagePill stage={row.journey_stage} />
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  {row.primary_csm_name ?? (
                    <span className="text-muted-foreground">Unassigned</span>
                  )}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  <HealthScoreCell
                    score={row.latest_health_score}
                    tier={row.latest_health_tier}
                  />
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  <LastCall
                    value={row.last_call_date}
                    meetingsThisMonth={row.meetings_this_month}
                    inactive={row.inactive}
                  />
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  <ActionItemsCell
                    open={row.open_action_items_count}
                    overdue={row.overdue_action_items_count}
                  />
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/clients/${row.id}`} className="block">
                  <TagsList tags={row.tags} />
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
