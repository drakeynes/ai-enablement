import { getClientsList, type ClientsListFilters, type ClientsListRow } from '@/lib/db/clients'
import { createClient } from '@/lib/supabase/server'
import { FilterBar } from './filter-bar'
import { ClientsTable } from './clients-table'

type SortKey =
  | 'full_name'
  | 'status'
  | 'journey_stage'
  | 'primary_csm_name'
  | 'latest_health_score'
  | 'last_call_date'
  | 'open_action_items_count'

const VALID_SORT_KEYS: SortKey[] = [
  'full_name',
  'status',
  'journey_stage',
  'primary_csm_name',
  'latest_health_score',
  'last_call_date',
  'open_action_items_count',
]

function readFilters(searchParams: Record<string, string | string[] | undefined>): ClientsListFilters {
  const get = (key: string): string | undefined => {
    const v = searchParams[key]
    return Array.isArray(v) ? v[0] : v
  }
  return {
    status: get('status'),
    journey_stage: get('journey_stage'),
    primary_csm_id: get('primary_csm_id'),
    has_open_action_items: get('has_open_action_items') === '1',
    needs_review_only: get('needs_review') === '1',
    search: get('q'),
  }
}

function sortRows(
  rows: ClientsListRow[],
  sort: SortKey,
  dir: 'asc' | 'desc',
): ClientsListRow[] {
  // NULLs always sort to the bottom regardless of direction — matches
  // SQL's NULLS LAST idiom and the gregory.md spec for V1 default
  // (last_call_date desc, NULLs last).
  const sortVal = (row: ClientsListRow): string | number | null => {
    const value = row[sort]
    if (value === null || value === undefined) return null
    return value as string | number
  }
  const cmp = (a: ClientsListRow, b: ClientsListRow) => {
    const va = sortVal(a)
    const vb = sortVal(b)
    if (va === null && vb === null) return 0
    if (va === null) return 1 // a goes after b regardless of dir
    if (vb === null) return -1
    if (va < vb) return dir === 'asc' ? -1 : 1
    if (va > vb) return dir === 'asc' ? 1 : -1
    return 0
  }
  return [...rows].sort(cmp)
}

export default async function ClientsPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const filters = readFilters(searchParams)
  const rows = await getClientsList(filters)

  const sortRaw = (Array.isArray(searchParams.sort) ? searchParams.sort[0] : searchParams.sort) ?? 'last_call_date'
  const dirRaw = (Array.isArray(searchParams.dir) ? searchParams.dir[0] : searchParams.dir) ?? 'desc'
  const sort: SortKey = (VALID_SORT_KEYS as string[]).includes(sortRaw)
    ? (sortRaw as SortKey)
    : 'last_call_date'
  const dir: 'asc' | 'desc' = dirRaw === 'asc' ? 'asc' : 'desc'

  const sorted = sortRows(rows, sort, dir)

  // Build the list of CSMs that have at least one active assignment so
  // the filter dropdown only shows real options. Also fetch the full
  // active team_members list as a fallback.
  const supabase = createClient()
  const { data: teamMembers } = await supabase
    .from('team_members')
    .select('id, full_name')
    .eq('is_active', true)
    .is('archived_at', null)
    .order('full_name')

  const primaryCsmOptions = (teamMembers ?? []).map((member) => ({
    id: member.id,
    label: member.full_name,
  }))

  // Filter bar reads URL params directly via useSearchParams; we just
  // need to pass it the list of CSM options.
  // Pass the un-prefixed search params object as JSON so the table can
  // generate hrefs that preserve all current filters when sort changes.
  const baseSearchParamsObj: Record<string, string> = {}
  for (const [key, value] of Object.entries(searchParams)) {
    if (key === 'sort' || key === 'dir') continue
    if (Array.isArray(value)) {
      if (value[0] !== undefined) baseSearchParamsObj[key] = value[0]
    } else if (value !== undefined) {
      baseSearchParamsObj[key] = value
    }
  }
  const baseSearchParams = new URLSearchParams(baseSearchParamsObj)

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Clients</h1>
        <span className="text-sm text-muted-foreground">
          {sorted.length} {sorted.length === 1 ? 'client' : 'clients'}
        </span>
      </div>

      <FilterBar primaryCsmOptions={primaryCsmOptions} />

      <ClientsTable
        rows={sorted}
        sort={sort}
        dir={dir}
        baseSearchParams={baseSearchParams}
      />
    </div>
  )
}
