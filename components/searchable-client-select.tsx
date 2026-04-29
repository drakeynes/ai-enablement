'use client'

import { useId, useMemo, useState } from 'react'
import { Input } from '@/components/ui/input'
import type { CandidateClient } from '@/lib/db/merge'

// Minimal searchable client picker. Server fetches the full candidate
// list (~134 rows today) and passes it in; filtering happens
// client-side as the user types — no DB round-trip per keystroke.
//
// Designed to be reusable: the Calls page (M3.3) needs the same
// shape for primary_client_id editing. If reuse pressure builds we
// can move the type alias somewhere more general; for V1 it lives
// alongside the merge data layer because that's the first caller.
export function SearchableClientSelect({
  candidates,
  value,
  onChange,
  placeholder = 'Search by name or email…',
  emptyMessage = 'No matches.',
}: {
  candidates: CandidateClient[]
  value: string | null
  onChange: (id: string | null) => void
  placeholder?: string
  emptyMessage?: string
}) {
  const [query, setQuery] = useState('')
  const inputId = useId()

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return candidates
    return candidates.filter(
      (c) =>
        c.full_name.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q),
    )
  }, [query, candidates])

  const selected = candidates.find((c) => c.id === value) ?? null

  return (
    <div className="space-y-2">
      <Input
        id={inputId}
        type="text"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
      <div className="max-h-64 overflow-auto rounded-md border">
        {filtered.length === 0 ? (
          <p className="p-3 text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          <ul className="divide-y">
            {filtered.map((candidate) => {
              const isSelected = candidate.id === value
              return (
                <li key={candidate.id}>
                  <button
                    type="button"
                    onClick={() => onChange(isSelected ? null : candidate.id)}
                    className={`flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left hover:bg-muted/50 ${
                      isSelected ? 'bg-muted/70' : ''
                    }`}
                  >
                    <span className="text-sm font-medium">
                      {candidate.full_name}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {candidate.email}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      {selected ? (
        <p className="text-xs text-muted-foreground">
          Selected: <strong>{selected.full_name}</strong> ({selected.email})
        </p>
      ) : null}
    </div>
  )
}
