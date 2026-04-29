'use server'

import { revalidatePath } from 'next/cache'
import {
  changePrimaryCsm,
  updateClient,
  type UpdatableField,
} from '@/lib/db/clients'
import { mergeClient, type MergeResult } from '@/lib/db/merge'

const UPDATABLE_FIELDS: readonly UpdatableField[] = [
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

export async function updateClientField(
  id: string,
  field: string,
  value: unknown,
): Promise<{ success: true } | { success: false; error: string }> {
  if (!(UPDATABLE_FIELDS as readonly string[]).includes(field)) {
    return { success: false, error: `Field not editable: ${field}` }
  }

  // Tags is a string[]; everything else is a string-or-null. Narrow at
  // the boundary so updateClient's typed signature is honored.
  const partial: Partial<Record<UpdatableField, unknown>> = {}
  if (field === 'tags') {
    if (!Array.isArray(value)) {
      return { success: false, error: 'Tags must be an array of strings.' }
    }
    if (!value.every((t) => typeof t === 'string')) {
      return { success: false, error: 'Tags must be strings.' }
    }
    partial.tags = value as string[]
  } else {
    if (value !== null && typeof value !== 'string') {
      return { success: false, error: `${field} must be a string or null.` }
    }
    partial[field as UpdatableField] = value as string | null
  }

  const result = await updateClient(
    id,
    partial as Parameters<typeof updateClient>[1],
  )

  if (result.success) {
    revalidatePath(`/clients/${id}`)
    revalidatePath('/clients')
  }
  return result
}

export async function changeClientPrimaryCsm(
  client_id: string,
  new_team_member_id: string,
): Promise<{ success: true } | { success: false; error: string }> {
  const result = await changePrimaryCsm(client_id, new_team_member_id)
  if (result.success) {
    revalidatePath(`/clients/${client_id}`)
    revalidatePath('/clients')
  }
  return result
}

export async function mergeClientAction(
  source_client_id: string,
  target_client_id: string,
): Promise<
  | { success: true; result: MergeResult }
  | { success: false; error: string }
> {
  const result = await mergeClient(source_client_id, target_client_id)
  if (result.success) {
    revalidatePath(`/clients/${target_client_id}`)
    revalidatePath(`/clients/${source_client_id}`)
    revalidatePath('/clients')
  }
  return result
}
