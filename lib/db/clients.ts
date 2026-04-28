import 'server-only'

import { createClient } from '@/lib/supabase/server'
import type { Database } from '@/lib/supabase/types'

type ClientRow = Database['public']['Tables']['clients']['Row']

// Allowed fields for inline-save on the Clients detail page. The
// dashboard's Identity / Status / Notes sections funnel through
// updateClient; anything outside this list is rejected to keep the
// editing surface tight (no accidental writes to metadata, slack_user_id,
// archived_at, etc.).
const UPDATABLE_FIELDS = [
  'full_name',
  'email',
  'phone',
  'timezone',
  'status',
  'journey_stage',
  'program_type',
  'start_date',
  'tags',
  'notes',
] as const

export type UpdatableField = (typeof UPDATABLE_FIELDS)[number]

export type ClientsListFilters = {
  status?: string
  journey_stage?: string
  primary_csm_id?: string
  has_open_action_items?: boolean
  needs_review_only?: boolean
  search?: string
}

export type ClientsListRow = ClientRow & {
  primary_csm_id: string | null
  primary_csm_name: string | null
  latest_health_score: number | null
  latest_health_tier: string | null
  last_call_date: string | null
  open_action_items_count: number
  overdue_action_items_count: number
}

// ----------------------------------------------------------------------
// getClientsList
// ----------------------------------------------------------------------
//
// Single round trip to PostgREST with nested selects, then JS-side
// derivation of the per-row aggregates the list view needs (latest
// health score, last call date, open / overdue action item counts,
// active primary CSM). DB-side filters cover the cheap ones (status,
// journey_stage, tag membership, search). JS-side filters cover the
// derived ones (primary_csm_id, has_open_action_items).
//
// Volume note: ~134 clients, each with ~10 calls + a handful of action
// items, comfortably fits in one PostgREST round trip. If volume grows
// past ~1000 clients or the join arrays balloon, swap this for a
// Postgres view or RPC — the call sites won't change.
export async function getClientsList(
  filters: ClientsListFilters = {},
): Promise<ClientsListRow[]> {
  const supabase = createClient()

  let query = supabase
    .from('clients')
    .select(
      `
      *,
      client_team_assignments(
        role,
        assigned_at,
        unassigned_at,
        team_members(id, full_name)
      ),
      client_health_scores(score, tier, computed_at),
      calls!calls_primary_client_id_fkey(started_at),
      call_action_items!call_action_items_owner_client_id_fkey(id, status, due_date)
    `,
    )
    .is('archived_at', null)

  if (filters.status) {
    query = query.eq('status', filters.status)
  }
  if (filters.journey_stage) {
    query = query.eq('journey_stage', filters.journey_stage)
  }
  if (filters.needs_review_only) {
    query = query.contains('tags', ['needs_review'])
  }
  if (filters.search) {
    const q = filters.search.replace(/[%,]/g, '')
    query = query.or(`full_name.ilike.%${q}%,email.ilike.%${q}%`)
  }

  const { data, error } = await query
  if (error) throw error
  if (!data) return []

  const today = new Date()
  today.setHours(0, 0, 0, 0)

  let rows: ClientsListRow[] = data.map((row) => {
    const assignments = (row.client_team_assignments ?? []) as Array<{
      role: string
      assigned_at: string
      unassigned_at: string | null
      team_members: { id: string; full_name: string } | null
    }>
    const activePrimaryCsm = assignments.find(
      (a) => a.role === 'primary_csm' && a.unassigned_at === null,
    )

    const scores = (row.client_health_scores ?? []) as Array<{
      score: number
      tier: string
      computed_at: string
    }>
    const latestScore =
      scores.length === 0
        ? null
        : scores.reduce((best, s) =>
            new Date(s.computed_at) > new Date(best.computed_at) ? s : best,
          )

    const calls = (row.calls ?? []) as Array<{ started_at: string }>
    const latestCall =
      calls.length === 0
        ? null
        : calls.reduce((best, c) =>
            new Date(c.started_at) > new Date(best.started_at) ? c : best,
          )

    const actionItems = (row.call_action_items ?? []) as Array<{
      id: string
      status: string
      due_date: string | null
    }>
    const openItems = actionItems.filter((a) => a.status === 'open')
    const overdueItems = openItems.filter(
      (a) => a.due_date !== null && new Date(a.due_date) < today,
    )

    // Strip the nested-select arrays from the row — they're already
    // captured in the derived fields below — and return a clean
    // ClientsListRow.
    const client = row as unknown as ClientRow

    return {
      id: client.id,
      email: client.email,
      full_name: client.full_name,
      slack_user_id: client.slack_user_id,
      phone: client.phone,
      timezone: client.timezone,
      journey_stage: client.journey_stage,
      status: client.status,
      start_date: client.start_date,
      program_type: client.program_type,
      tags: client.tags,
      metadata: client.metadata,
      notes: client.notes,
      created_at: client.created_at,
      updated_at: client.updated_at,
      archived_at: client.archived_at,
      primary_csm_id: activePrimaryCsm?.team_members?.id ?? null,
      primary_csm_name: activePrimaryCsm?.team_members?.full_name ?? null,
      latest_health_score: latestScore?.score ?? null,
      latest_health_tier: latestScore?.tier ?? null,
      last_call_date: latestCall?.started_at ?? null,
      open_action_items_count: openItems.length,
      overdue_action_items_count: overdueItems.length,
    }
  })

  if (filters.primary_csm_id !== undefined) {
    rows = rows.filter((r) => r.primary_csm_id === filters.primary_csm_id)
  }
  if (filters.has_open_action_items === true) {
    rows = rows.filter((r) => r.open_action_items_count > 0)
  }

  return rows
}

// ----------------------------------------------------------------------
// getClientById
// ----------------------------------------------------------------------
//
// Detail view query. Returns null for missing or archived clients.
// Pulls everything the 7-section detail page needs in one round trip;
// the page renders directly from this shape.
export type ClientDetail = ClientRow & {
  recent_calls: Array<{
    id: string
    started_at: string
    title: string | null
    call_category: string
    duration_seconds: number | null
  }>
  open_action_items: Array<{
    id: string
    description: string
    owner_type: string
    owner_team_member_id: string | null
    owner_client_id: string | null
    due_date: string | null
    call_id: string
  }>
  latest_health: {
    score: number
    tier: string
    factors: Database['public']['Tables']['client_health_scores']['Row']['factors']
    computed_at: string
  } | null
  latest_nps: {
    score: number
    submitted_at: string
  } | null
  active_primary_csm: {
    team_member_id: string
    team_member_name: string
    assigned_at: string
  } | null
  team_members: Array<{ id: string; full_name: string; email: string }>
}

export async function getClientById(id: string): Promise<ClientDetail | null> {
  const supabase = createClient()

  const { data: client, error } = await supabase
    .from('clients')
    .select('*')
    .eq('id', id)
    .is('archived_at', null)
    .maybeSingle()
  if (error) throw error
  if (!client) return null

  const [callsRes, actionItemsRes, healthRes, npsRes, assignmentRes, teamRes] =
    await Promise.all([
      supabase
        .from('calls')
        .select('id, started_at, title, call_category, duration_seconds')
        .eq('primary_client_id', id)
        .order('started_at', { ascending: false })
        .limit(5),
      supabase
        .from('call_action_items')
        .select(
          'id, description, owner_type, owner_team_member_id, owner_client_id, due_date, call_id',
        )
        .eq('owner_client_id', id)
        .eq('status', 'open')
        .order('due_date', { ascending: true, nullsFirst: false }),
      supabase
        .from('client_health_scores')
        .select('score, tier, factors, computed_at')
        .eq('client_id', id)
        .order('computed_at', { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from('nps_submissions')
        .select('score, submitted_at')
        .eq('client_id', id)
        .order('submitted_at', { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from('client_team_assignments')
        .select('team_member_id, assigned_at, team_members(full_name)')
        .eq('client_id', id)
        .eq('role', 'primary_csm')
        .is('unassigned_at', null)
        .maybeSingle(),
      supabase
        .from('team_members')
        .select('id, full_name, email')
        .eq('is_active', true)
        .is('archived_at', null)
        .order('full_name'),
    ])

  if (callsRes.error) throw callsRes.error
  if (actionItemsRes.error) throw actionItemsRes.error
  if (healthRes.error) throw healthRes.error
  if (npsRes.error) throw npsRes.error
  if (assignmentRes.error) throw assignmentRes.error
  if (teamRes.error) throw teamRes.error

  const assignment = assignmentRes.data as
    | {
        team_member_id: string
        assigned_at: string
        team_members: { full_name: string } | null
      }
    | null

  return {
    ...client,
    recent_calls: callsRes.data ?? [],
    open_action_items: actionItemsRes.data ?? [],
    latest_health: healthRes.data ?? null,
    latest_nps: npsRes.data ?? null,
    active_primary_csm: assignment
      ? {
          team_member_id: assignment.team_member_id,
          team_member_name: assignment.team_members?.full_name ?? '',
          assigned_at: assignment.assigned_at,
        }
      : null,
    team_members: teamRes.data ?? [],
  }
}

// ----------------------------------------------------------------------
// updateClient
// ----------------------------------------------------------------------
//
// Inline-save target for Identity / Status / Notes sections. The
// allowed-field whitelist is enforced server-side to keep the edit
// surface tight and to prevent stray fields from sneaking in via a
// crafted Server Action call.
export async function updateClient(
  id: string,
  fields: Partial<Pick<ClientRow, UpdatableField>>,
): Promise<{ success: true } | { success: false; error: string }> {
  // Reject any keys outside the whitelist before passing through to
  // Supabase. Types are already constrained by the function signature,
  // but the runtime check defends against a crafted Server Action call.
  for (const key of Object.keys(fields)) {
    if (!(UPDATABLE_FIELDS as readonly string[]).includes(key)) {
      return { success: false, error: `Field not editable: ${key}` }
    }
  }

  if (Object.keys(fields).length === 0) {
    return { success: false, error: 'No valid fields to update.' }
  }

  const supabase = createClient()
  const { error } = await supabase
    .from('clients')
    .update(fields)
    .eq('id', id)

  if (error) return { success: false, error: error.message }
  return { success: true }
}

// ----------------------------------------------------------------------
// changePrimaryCsm
// ----------------------------------------------------------------------
//
// Atomic swap via the change_primary_csm Postgres function (migration
// 0014). The function archives the existing active primary_csm
// assignment for the client (sets unassigned_at = now()) and inserts
// a new active row with the new team_member_id, all in one
// transaction. Preserves history per gregory.md detail-view §3.
//
// `current_user_team_member_id` is reserved for an audit-log column
// in V1.1 — kept in the signature now so callers don't refactor
// later. Not passed to the RPC in V1.
export async function changePrimaryCsm(
  client_id: string,
  new_team_member_id: string,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _current_user_team_member_id?: string,
): Promise<{ success: true } | { success: false; error: string }> {
  const supabase = createClient()
  const { error } = await supabase.rpc('change_primary_csm', {
    p_client_id: client_id,
    p_new_team_member_id: new_team_member_id,
  })
  if (error) return { success: false, error: error.message }
  return { success: true }
}
