import { getClientsList, type ClientsListFilters, type ClientsListRow } from '@/lib/db/clients'
import { createAdminClient } from '@/lib/supabase/admin'
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

// Mirror of FilterBar's STATUS_DEFAULT_SELECTED. Kept duplicated rather
// than imported because the file boundary between Server Component
// (page) and Client Component (filter-bar) crosses a 'use client'
// boundary; keeping the constant local avoids accidentally pulling
// client-only code into the server bundle. Drift risk is low — both
// values are tested at the smoke checkpoint.
const STATUS_DEFAULT_SELECTED = ['active', 'paused', 'ghost']

function parseMulti(raw: string | undefined): string[] {
  if (raw === undefined || raw === '') return []
  return raw.split(',').filter(Boolean)
}

function readFilters(searchParams: Record<string, string | string[] | undefined>): ClientsListFilters {
  const get = (key: string): string | undefined => {
    const v = searchParams[key]
    return Array.isArray(v) ? v[0] : v
  }

  // Status sentinel: absent → default trio; explicit-empty → no filter
  // (show all statuses including churned/leave); else parse.
  const statusRaw = get('status')
  const status: string[] =
    statusRaw === undefined
      ? STATUS_DEFAULT_SELECTED
      : statusRaw === ''
        ? []
        : statusRaw.split(',').filter(Boolean)

  return {
    status,
    primary_csm_ids: parseMulti(get('primary_csm')),
    csm_standing: parseMulti(get('csm_standing')),
    nps_standing: parseMulti(get('nps_standing')),
    trustpilot_status: parseMulti(get('trustpilot')),
    needs_review: get('needs_review') === '1',
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
  const supabase = createAdminClient()
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
