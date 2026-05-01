'use client'

// Tags chip input. Add via type + Enter (or comma); remove via X on
// chip; backspace on empty draft removes the last chip. Saves on every
// add/remove. Reverts to the initial set on save failure.
//
// Pattern carried over from the old inline-fields.tsx TagsField; lives
// here now so the new section components import from a stable
// components/client-detail/ home.

import { useEffect, useRef, useState, useTransition } from 'react'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export function EditableTagsField({
  initialTags,
  onSave,
}: {
  initialTags: string[]
  onSave: (
    nextTags: string[],
  ) => Promise<{ success: true } | { success: false; error: string }>
}) {
  const [tags, setTags] = useState<string[]>(initialTags)
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setTags(initialTags)
  }, [initialTags])

  function persist(nextTags: string[], priorTags: string[]) {
    setStatus('saving')
    setError(undefined)
    startTransition(async () => {
      const result = await onSave(nextTags)
      if (result.success) {
        setStatus('saved')
        if (savedTimer.current) clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setStatus('idle'), 1500)
      } else {
        setStatus('error')
        setError(result.error)
        setTags(priorTags)
      }
    })
  }

  function addTag(raw: string) {
    // Support comma-separated entry: "tag1, tag2" → 2 tags.
    const parts = raw
      .split(',')
      .map((p) => p.trim())
      .filter((p) => p !== '')
    if (parts.length === 0) return
    const lower = new Set(tags.map((t) => t.toLowerCase()))
    const additions: string[] = []
    for (const p of parts) {
      const l = p.toLowerCase()
      if (lower.has(l)) continue
      lower.add(l)
      additions.push(p)
    }
    if (additions.length === 0) return
    const next = [...tags, ...additions]
    const prior = tags
    setTags(next)
    setDraft('')
    persist(next, prior)
  }

  function removeTag(tag: string) {
    const prior = tags
    const next = tags.filter((t) => t !== tag)
    setTags(next)
    persist(next, prior)
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label>Tags</Label>
        {status === 'saving' ? (
          <span className="text-xs text-muted-foreground">Saving…</span>
        ) : status === 'saved' ? (
          <span className="text-xs text-emerald-700">Saved</span>
        ) : status === 'error' ? (
          <span className="text-xs text-rose-700" title={error}>
            Error: {error ?? 'failed'}
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-1.5 rounded-md border border-input p-2 min-h-9">
        {tags.map((tag) => {
          const isReview = tag === 'needs_review'
          return (
            <Badge
              key={tag}
              className={cn(
                'border font-normal',
                isReview
                  ? 'bg-amber-100 text-amber-900 border-amber-200'
                  : 'bg-zinc-100 text-zinc-700 border-zinc-200',
              )}
            >
              {tag}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                disabled={isPending}
                className="ml-1 hover:text-rose-700"
                aria-label={`Remove tag ${tag}`}
              >
                ×
              </button>
            </Badge>
          )
        })}
        <input
          type="text"
          value={draft}
          placeholder={tags.length === 0 ? 'Add tag…' : '+'}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault()
              addTag(draft)
            } else if (
              e.key === 'Backspace' &&
              draft === '' &&
              tags.length > 0
            ) {
              e.preventDefault()
              removeTag(tags[tags.length - 1])
            }
          }}
          onBlur={() => {
            if (draft.trim() !== '') addTag(draft)
          }}
          disabled={isPending}
          className="bg-transparent outline-none text-sm flex-1 min-w-20"
        />
      </div>
    </div>
  )
}
