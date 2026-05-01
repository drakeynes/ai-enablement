// Read-only field display with empty-state affordance.
//
// Renders a label + value. When value is null/empty:
// - editable=true (default) → "—" with cursor:pointer + hover background
//   (signals "click to edit" — the cue for B2's inline editor)
// - editable=false           → "—" with no affordance (true read-only)
//
// In B1 the click does nothing; B2 wires up edit mode.

import type { ReactNode } from 'react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

const EMPTY_PLACEHOLDER = '—'

export function ReadOnlyField({
  label,
  value,
  editable = true,
  mono = false,
  children,
  className,
}: {
  label: string
  value?: string | number | null
  editable?: boolean
  mono?: boolean
  // Use children for richer rendering (links, lists, multi-value etc.).
  // When children is set, value is ignored.
  children?: ReactNode
  className?: string
}) {
  const isEmpty =
    children === undefined && (value === null || value === undefined || value === '')
  const display: ReactNode =
    children ??
    (value === null || value === undefined || value === ''
      ? EMPTY_PLACEHOLDER
      : String(value))

  return (
    <div className={cn('space-y-1.5', className)}>
      <Label>{label}</Label>
      <div
        className={cn(
          'min-h-9 rounded-md px-2 py-1.5 text-sm',
          mono && 'font-mono',
          editable
            ? 'cursor-pointer hover:bg-muted/50 border border-transparent hover:border-input transition-colors'
            : '',
          isEmpty && 'text-muted-foreground',
        )}
        title={editable ? 'Editing wires up in B2' : undefined}
      >
        {display}
      </div>
    </div>
  )
}
