'use client'

import { useEffect, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { SearchableClientSelect } from '@/components/searchable-client-select'
import type { CandidateClient } from '@/lib/db/merge'
import { cn } from '@/lib/utils'

type ChipDef = {
  paramKey: string
  paramValue: string
  label: string
  className?: string
}

const CATEGORY_CHIPS: ChipDef[] = [
  { paramKey: 'category', paramValue: 'client', label: 'Client' },
  { paramKey: 'category', paramValue: 'internal', label: 'Internal' },
  { paramKey: 'category', paramValue: 'external', label: 'External' },
  { paramKey: 'category', paramValue: 'unclassified', label: 'Unclassified' },
  { paramKey: 'category', paramValue: 'excluded', label: 'Excluded' },
]

const REVIEW_CHIP: ChipDef = {
  paramKey: 'needs_review',
  paramValue: '1',
  label: 'Needs review',
  className: 'bg-amber-100 text-amber-900 border-amber-200',
}

export function CallsFilterBar({
  clientOptions,
}: {
  clientOptions: CandidateClient[]
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [searchValue, setSearchValue] = useState(searchParams.get('q') ?? '')
  const debounceRef = useRef<NodeJS.Timeout | null>(null)
  const initialMount = useRef(true)

  // Client picker dialog state. Local — only the URL holds the
  // applied filter.
  const [clientDialogOpen, setClientDialogOpen] = useState(false)
  const [pendingClientId, setPendingClientId] = useState<string | null>(null)

  useEffect(() => {
    if (initialMount.current) {
      initialMount.current = false
      return
    }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      const params = new URLSearchParams(searchParams.toString())
      if (searchValue) params.set('q', searchValue)
      else params.delete('q')
      router.replace(`${pathname}?${params.toString()}`)
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchValue])

  function toggleChip(chip: ChipDef) {
    const params = new URLSearchParams(searchParams.toString())
    if (params.get(chip.paramKey) === chip.paramValue) {
      params.delete(chip.paramKey)
    } else {
      params.set(chip.paramKey, chip.paramValue)
    }
    router.replace(`${pathname}?${params.toString()}`)
  }

  function clearAll() {
    setSearchValue('')
    router.replace(pathname)
  }

  function openClientPicker() {
    setPendingClientId(searchParams.get('client'))
    setClientDialogOpen(true)
  }

  function applyClientFilter() {
    const params = new URLSearchParams(searchParams.toString())
    if (pendingClientId) params.set('client', pendingClientId)
    else params.delete('client')
    router.replace(`${pathname}?${params.toString()}`)
    setClientDialogOpen(false)
  }

  function clearClientFilter() {
    const params = new URLSearchParams(searchParams.toString())
    params.delete('client')
    router.replace(`${pathname}?${params.toString()}`)
  }

  const activeClientId = searchParams.get('client')
  const activeClient = activeClientId
    ? clientOptions.find((option) => option.id === activeClientId) ?? null
    : null

  const hasAnyFilter = Array.from(searchParams.entries()).some(
    ([key]) => !['sort', 'dir'].includes(key),
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search by participant or title…"
          value={searchValue}
          onChange={(event) => setSearchValue(event.target.value)}
          className="max-w-sm"
        />
        <Button variant="outline" size="sm" onClick={openClientPicker}>
          {activeClient
            ? `Client: ${activeClient.full_name}`
            : 'Filter by client…'}
        </Button>
        {activeClient ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearClientFilter}
            className="text-muted-foreground"
          >
            ✕
          </Button>
        ) : null}
        {hasAnyFilter ? (
          <Button variant="outline" size="sm" onClick={clearAll}>
            Clear filters
          </Button>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {[...CATEGORY_CHIPS, REVIEW_CHIP].map((chip) => {
          const active = searchParams.get(chip.paramKey) === chip.paramValue
          return (
            <button
              key={`${chip.paramKey}=${chip.paramValue}`}
              onClick={() => toggleChip(chip)}
              className="cursor-pointer"
              type="button"
            >
              <Badge
                className={cn(
                  'border font-normal',
                  active
                    ? chip.className ??
                        'bg-primary text-primary-foreground border-primary'
                    : 'bg-zinc-50 text-zinc-700 border-zinc-200 hover:bg-zinc-100',
                )}
              >
                {chip.label}
              </Badge>
            </button>
          )
        })}
      </div>

      <Dialog
        open={clientDialogOpen}
        onOpenChange={(open) => {
          if (!open) setClientDialogOpen(false)
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Filter calls by client</DialogTitle>
            <DialogDescription>
              Pick a client to show only calls where they are the primary
              client. Clear the selection to remove the filter.
            </DialogDescription>
          </DialogHeader>
          <SearchableClientSelect
            candidates={clientOptions}
            value={pendingClientId}
            onChange={setPendingClientId}
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setClientDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button onClick={applyClientFilter}>
              {pendingClientId ? 'Apply filter' : 'Clear filter'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
