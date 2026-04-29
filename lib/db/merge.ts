import 'server-only'

import { createAdminClient } from '@/lib/supabase/admin'

// Returned by the merge_clients RPC (migration 0015). Mirrors the
// jsonb structure the function builds; cast at the boundary so callers
// get a typed shape.
export type MergeResult = {
  source_id: string
  target_id: string
  already_merged: boolean
  participants_reattributed: number
  calls_reattributed: number
  transcript_chunks_reactivated: number
}

// Lightweight client shape for the merge target dropdown. id + name +
// email is enough to disambiguate (two "Robert Traffie"s wouldn't be
// ambiguous because their emails differ).
export type CandidateClient = {
  id: string
  full_name: string
  email: string
}

// Eligible merge targets: every active (not archived) client other
// than the source. Powers the "Merge into…" searchable dropdown on
// the Clients detail page. ~134 rows today; fetch-all-on-mount is
// fine until growth or perceived latency forces a server-filtered
// approach (followup logged).
export async function listMergeCandidates(
  excludeClientId: string,
): Promise<CandidateClient[]> {
  const supabase = createAdminClient()
  const { data, error } = await supabase
    .from('clients')
    .select('id, full_name, email')
    .is('archived_at', null)
    .neq('id', excludeClientId)
    .order('full_name', { ascending: true })

  if (error) throw error
  return (data ?? []) as CandidateClient[]
}

// Atomic merge via the merge_clients Postgres function (migration
// 0015). All 5 steps execute in a single transaction; partial failure
// rolls back. Idempotent on source.metadata.merged_into — re-running
// after success is a no-op for the merge body and re-syncs alternates.
//
// The plpgsql function raises on validation failures (source/target
// missing, target archived, source not tagged needs_review, source ==
// target). Those surface as Supabase RPC errors; we narrow them into
// the dashboard's success/error result type instead of letting raw
// Postgres messages reach the dialog.
export async function mergeClient(
  sourceClientId: string,
  targetClientId: string,
): Promise<
  | { success: true; result: MergeResult }
  | { success: false; error: string }
> {
  const supabase = createAdminClient()
  const { data, error } = await supabase.rpc('merge_clients', {
    p_source_id: sourceClientId,
    p_target_id: targetClientId,
  })

  if (error) return { success: false, error: error.message }
  return { success: true, result: data as unknown as MergeResult }
}
