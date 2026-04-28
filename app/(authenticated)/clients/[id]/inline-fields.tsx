'use client'

import { useState, useTransition, useRef, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { updateClientField } from './actions'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

function StatusBadge({ status, error }: { status: SaveStatus; error?: string }) {
  if (status === 'idle') return null
  if (status === 'saving') {
    return <span className="text-xs text-muted-foreground">Saving…</span>
  }
  if (status === 'saved') {
    return <span className="text-xs text-emerald-700">Saved</span>
  }
  return (
    <span className="text-xs text-rose-700" title={error}>
      Error: {error ?? 'failed'}
    </span>
  )
}

// ----------------------------------------------------------------------
// InlineTextField — single-line text or email/tel input. Saves on blur
// when the value differs from the initial. Reverts on save failure.
// ----------------------------------------------------------------------
export function InlineTextField({
  clientId,
  field,
  initialValue,
  type = 'text',
  label,
  placeholder,
}: {
  clientId: string
  field: string
  initialValue: string | null
  type?: 'text' | 'email' | 'tel'
  label: string
  placeholder?: string
}) {
  const [value, setValue] = useState(initialValue ?? '')
  const [savedValue, setSavedValue] = useState(initialValue ?? '')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const savedTimer = useRef<NodeJS.Timeout | null>(null)

  function handleSave() {
    if (value === savedValue) {
      return
    }
    setStatus('saving')
    setError(undefined)
    startTransition(async () => {
      const next = value === '' ? null : value
      const result = await updateClientField(clientId, field, next)
      if (result.success) {
        setSavedValue(value)
        setStatus('saved')
        if (savedTimer.current) clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setStatus('idle'), 1500)
      } else {
        setStatus('error')
        setError(result.error)
        setValue(savedValue) // revert to last successfully-saved value
      }
    })
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor={field}>{label}</Label>
        <StatusBadge status={status} error={error} />
      </div>
      <Input
        id={field}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
        onBlur={handleSave}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            event.currentTarget.blur()
          }
        }}
        disabled={isPending}
      />
    </div>
  )
}

// ----------------------------------------------------------------------
// InlineSelectField — native <select> for enum-style fields. Saves
// immediately on change (no blur dance — there's nothing to "abandon").
// ----------------------------------------------------------------------
export function InlineSelectField({
  clientId,
  field,
  initialValue,
  options,
  label,
}: {
  clientId: string
  field: string
  initialValue: string | null
  options: Array<{ value: string; label: string }>
  label: string
}) {
  const [value, setValue] = useState(initialValue ?? '')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const savedTimer = useRef<NodeJS.Timeout | null>(null)

  function handleChange(newValue: string) {
    const previous = value
    setValue(newValue)
    setStatus('saving')
    setError(undefined)
    startTransition(async () => {
      const next = newValue === '' ? null : newValue
      const result = await updateClientField(clientId, field, next)
      if (result.success) {
        setStatus('saved')
        if (savedTimer.current) clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setStatus('idle'), 1500)
      } else {
        setStatus('error')
        setError(result.error)
        setValue(previous)
      }
    })
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor={field}>{label}</Label>
        <StatusBadge status={status} error={error} />
      </div>
      <select
        id={field}
        value={value}
        onChange={(event) => handleChange(event.target.value)}
        disabled={isPending}
        className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
      >
        <option value="">—</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

// ----------------------------------------------------------------------
// InlineDateField — same surface as InlineTextField, type="date".
// Stored as ISO date string (YYYY-MM-DD) per migration 0001 for
// clients.start_date.
// ----------------------------------------------------------------------
export function InlineDateField({
  clientId,
  field,
  initialValue,
  label,
}: {
  clientId: string
  field: string
  initialValue: string | null
  label: string
}) {
  const [value, setValue] = useState(initialValue ?? '')
  const [savedValue, setSavedValue] = useState(initialValue ?? '')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const savedTimer = useRef<NodeJS.Timeout | null>(null)

  function handleSave() {
    if (value === savedValue) return
    setStatus('saving')
    setError(undefined)
    startTransition(async () => {
      const next = value === '' ? null : value
      const result = await updateClientField(clientId, field, next)
      if (result.success) {
        setSavedValue(value)
        setStatus('saved')
        if (savedTimer.current) clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setStatus('idle'), 1500)
      } else {
        setStatus('error')
        setError(result.error)
        setValue(savedValue)
      }
    })
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor={field}>{label}</Label>
        <StatusBadge status={status} error={error} />
      </div>
      <Input
        id={field}
        type="date"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={handleSave}
        disabled={isPending}
      />
    </div>
  )
}

// ----------------------------------------------------------------------
// InlineTextarea — Notes section. Saves on blur OR Cmd/Ctrl+S. Plain
// text in V1 — markdown rendering is a V1.1 polish per gregory.md.
// ----------------------------------------------------------------------
export function InlineTextarea({
  clientId,
  field,
  initialValue,
  label,
  placeholder,
}: {
  clientId: string
  field: string
  initialValue: string | null
  label: string
  placeholder?: string
}) {
  const [value, setValue] = useState(initialValue ?? '')
  const [savedValue, setSavedValue] = useState(initialValue ?? '')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const savedTimer = useRef<NodeJS.Timeout | null>(null)

  function handleSave() {
    if (value === savedValue) return
    setStatus('saving')
    setError(undefined)
    startTransition(async () => {
      const next = value === '' ? null : value
      const result = await updateClientField(clientId, field, next)
      if (result.success) {
        setSavedValue(value)
        setStatus('saved')
        if (savedTimer.current) clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setStatus('idle'), 1500)
      } else {
        setStatus('error')
        setError(result.error)
        setValue(savedValue)
      }
    })
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor={field}>{label}</Label>
        <StatusBadge status={status} error={error} />
      </div>
      <Textarea
        id={field}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
        onBlur={handleSave}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === 's') {
            event.preventDefault()
            handleSave()
          }
        }}
        disabled={isPending}
        rows={6}
        className="font-mono text-sm whitespace-pre-wrap"
      />
    </div>
  )
}

// ----------------------------------------------------------------------
// TagsField — chip input. Add tag = type + Enter; remove = X on chip.
// Saves on every add/remove. needs_review tag is just a string like
// any other; Zain may want to clear it after merging via M2.3c or
// after manually verifying a client is legit.
// ----------------------------------------------------------------------
export function TagsField({
  clientId,
  initialTags,
}: {
  clientId: string
  initialTags: string[]
}) {
  const [tags, setTags] = useState<string[]>(initialTags)
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const savedTimer = useRef<NodeJS.Timeout | null>(null)

  // Keep state in sync if the parent re-renders with new tags (e.g.,
  // after a server-side revalidation).
  useEffect(() => {
    setTags(initialTags)
  }, [initialTags])

  function persist(nextTags: string[]) {
    setStatus('saving')
    setError(undefined)
    startTransition(async () => {
      const result = await updateClientField(clientId, 'tags', nextTags)
      if (result.success) {
        setStatus('saved')
        if (savedTimer.current) clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setStatus('idle'), 1500)
      } else {
        setStatus('error')
        setError(result.error)
        setTags(initialTags) // revert
      }
    })
  }

  function addTag(tag: string) {
    const t = tag.trim()
    if (!t || tags.includes(t)) return
    const next = [...tags, t]
    setTags(next)
    persist(next)
  }
  function removeTag(tag: string) {
    const next = tags.filter((t) => t !== tag)
    setTags(next)
    persist(next)
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label>Tags</Label>
        <StatusBadge status={status} error={error} />
      </div>
      <div className="flex flex-wrap gap-1.5 rounded-md border border-input p-2">
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
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addTag(draft)
              setDraft('')
            } else if (event.key === 'Backspace' && draft === '' && tags.length > 0) {
              event.preventDefault()
              removeTag(tags[tags.length - 1])
            }
          }}
          disabled={isPending}
          className="bg-transparent outline-none text-sm flex-1 min-w-20"
        />
      </div>
    </div>
  )
}
