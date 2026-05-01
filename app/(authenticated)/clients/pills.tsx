// Small server-renderable pill helpers for the Clients table.
// Status / journey-stage / tags / needs-review treatments live here so
// the table and detail page render them identically.

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const STATUS_CLASSES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  paused: 'bg-amber-100 text-amber-900 border-amber-200',
  ghost: 'bg-zinc-100 text-zinc-700 border-zinc-200',
  leave: 'bg-slate-200 text-slate-800 border-slate-300',
  churned: 'bg-rose-100 text-rose-900 border-rose-200',
}

export function StatusPill({ status }: { status: string }) {
  const cls = STATUS_CLASSES[status] ?? 'bg-zinc-100 text-zinc-700 border-zinc-200'
  return <Badge className={cn('border', cls)}>{status}</Badge>
}

export function JourneyStagePill({ stage }: { stage: string | null }) {
  if (!stage) return <span className="text-muted-foreground">—</span>
  return (
    <Badge variant="outline" className="font-normal">
      {stage}
    </Badge>
  )
}

const NEEDS_REVIEW_CLASSES =
  'bg-amber-100 text-amber-900 border-amber-200 font-medium'

export function TagsList({ tags }: { tags: string[] }) {
  if (!tags.length) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((tag) => {
        const isReview = tag === 'needs_review'
        return (
          <Badge
            key={tag}
            className={cn(
              'border font-normal',
              isReview
                ? NEEDS_REVIEW_CLASSES
                : 'bg-zinc-100 text-zinc-700 border-zinc-200',
            )}
          >
            {tag}
          </Badge>
        )
      })}
    </div>
  )
}

// Standalone pill rendered alongside Status / Journey on the detail
// page header for clients carrying the needs_review tag. The list view
// already surfaces this via TagsList; the detail header gives it a
// second, more prominent rendering since reviewers will land here from
// the "Auto-created (needs review)" filter chip.
export function NeedsReviewPill() {
  return (
    <Badge className={cn('border', NEEDS_REVIEW_CLASSES)}>
      needs review
    </Badge>
  )
}
