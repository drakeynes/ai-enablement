import Link from 'next/link'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { CallsListRow } from '@/lib/db/calls'

type SortKey =
  | 'started_at'
  | 'title'
  | 'call_category'
  | 'primary_client_name'
  | 'duration_seconds'
  | 'classification_confidence'

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'started_at', label: 'Date' },
  { key: 'title', label: 'Title' },
  { key: 'call_category', label: 'Category' },
  { key: 'primary_client_name', label: 'Primary client' },
  { key: 'duration_seconds', label: 'Duration' },
  { key: 'classification_confidence', label: 'Confidence' },
]

const CATEGORY_CLASSES: Record<string, string> = {
  client: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  internal: 'bg-sky-100 text-sky-900 border-sky-200',
  external: 'bg-zinc-100 text-zinc-700 border-zinc-200',
  unclassified: 'bg-amber-100 text-amber-900 border-amber-200',
  excluded: 'bg-rose-100 text-rose-900 border-rose-200',
}

function CategoryPill({ category }: { category: string }) {
  const cls =
    CATEGORY_CLASSES[category] ?? 'bg-zinc-100 text-zinc-700 border-zinc-200'
  return <Badge className={cn('border font-normal', cls)}>{category}</Badge>
}

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
      {indicator ? (
        <span className="text-muted-foreground">{indicator}</span>
      ) : null}
    </Link>
  )
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const mm = Math.floor(seconds / 60)
  const ss = seconds % 60
  return `${mm}:${ss.toString().padStart(2, '0')}`
}

function ConfidenceCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground">—</span>
  const cls =
    value < 0.5
      ? 'text-rose-700'
      : value < 0.7
        ? 'text-amber-700'
        : 'text-emerald-700'
  return (
    <span className={cn('tabular-nums font-medium', cls)}>
      {value.toFixed(2)}
    </span>
  )
}

function ParticipantsCell({
  participants,
}: {
  participants: CallsListRow['participants']
}) {
  if (participants.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }
  const first = participants[0]
  const firstLabel = first.display_name ?? first.email
  if (participants.length === 1) {
    return <span className="text-sm">{firstLabel}</span>
  }
  return (
    <span className="text-sm">
      {firstLabel}{' '}
      <span className="text-muted-foreground">
        + {participants.length - 1} other
        {participants.length - 1 === 1 ? '' : 's'}
      </span>
    </span>
  )
}

export function CallsTable({
  rows,
  sort,
  dir,
  baseSearchParams,
}: {
  rows: CallsListRow[]
  sort: SortKey
  dir: 'asc' | 'desc'
  baseSearchParams: URLSearchParams
}) {
  if (rows.length === 0) {
    return (
      <div className="border rounded-md p-12 text-center text-muted-foreground text-sm">
        No calls match the current filters.
      </div>
    )
  }
  return (
    <div className="border rounded-md overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            {SORTABLE_COLUMNS.map((column) => (
              <TableHead key={column.key}>
                <SortableHeader
                  column={column}
                  currentSort={sort}
                  currentDir={dir}
                  baseSearchParams={baseSearchParams}
                />
              </TableHead>
            ))}
            <TableHead>Participants</TableHead>
            <TableHead>Retrievable</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              <TableCell className="text-sm tabular-nums whitespace-nowrap text-muted-foreground">
                {new Date(row.started_at).toLocaleDateString()}
              </TableCell>
              <TableCell>
                <Link
                  href={`/calls/${row.id}`}
                  className="text-sm hover:underline underline-offset-4 truncate inline-block max-w-md"
                >
                  {row.title ?? 'Untitled call'}
                </Link>
              </TableCell>
              <TableCell>
                <CategoryPill category={row.call_category} />
              </TableCell>
              <TableCell className="text-sm">
                {row.primary_client_id && row.primary_client_name ? (
                  <Link
                    href={`/clients/${row.primary_client_id}`}
                    className="hover:underline underline-offset-4"
                  >
                    {row.primary_client_name}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-sm tabular-nums">
                {formatDuration(row.duration_seconds)}
              </TableCell>
              <TableCell>
                <ConfidenceCell value={row.classification_confidence} />
              </TableCell>
              <TableCell>
                <ParticipantsCell participants={row.participants} />
              </TableCell>
              <TableCell>
                {row.is_retrievable_by_client_agents ? (
                  <span title="Retrievable by client-facing agents" className="text-emerald-700">
                    ✓
                  </span>
                ) : (
                  <span title="Not retrievable" className="text-muted-foreground">
                    —
                  </span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
