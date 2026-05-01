'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type ChipDef = {
  paramKey: string
  paramValue: string
  label: string
  className?: string
}

// V1 filter chips. status + journey_stage are toggle-on-single-value;
// has_open_action_items and needs_review are boolean toggles. The
// needs_review chip is the M2.3c hook for the auto-created review
// queue — visually distinct so reviewers can find it at a glance.
const STATUS_CHIPS: ChipDef[] = [
  { paramKey: 'status', paramValue: 'active', label: 'Active' },
  { paramKey: 'status', paramValue: 'paused', label: 'Paused' },
  { paramKey: 'status', paramValue: 'ghost', label: 'Ghost' },
  { paramKey: 'status', paramValue: 'leave', label: 'Leave' },
  { paramKey: 'status', paramValue: 'churned', label: 'Churned' },
]

const JOURNEY_CHIPS: ChipDef[] = [
  { paramKey: 'journey_stage', paramValue: 'onboarding', label: 'Onboarding' },
  { paramKey: 'journey_stage', paramValue: 'active', label: 'Journey: active' },
  { paramKey: 'journey_stage', paramValue: 'churning', label: 'Churning' },
  { paramKey: 'journey_stage', paramValue: 'churned', label: 'Journey: churned' },
  { paramKey: 'journey_stage', paramValue: 'alumni', label: 'Alumni' },
]

const BOOLEAN_CHIPS: ChipDef[] = [
  {
    paramKey: 'has_open_action_items',
    paramValue: '1',
    label: 'Has open action items',
  },
  {
    paramKey: 'needs_review',
    paramValue: '1',
    label: 'Auto-created (needs review)',
    className: 'bg-amber-100 text-amber-900 border-amber-200',
  },
  {
    paramKey: 'show_archived',
    paramValue: '1',
    label: 'Show churned & leave',
  },
]

export function FilterBar({
  primaryCsmOptions,
}: {
  primaryCsmOptions: Array<{ id: string; label: string }>
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  // Search input is debounced separately from the URL state; otherwise
  // every keystroke would refetch the page.
  const [searchValue, setSearchValue] = useState(searchParams.get('q') ?? '')
  const debounceRef = useRef<NodeJS.Timeout | null>(null)
  const initialMount = useRef(true)

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

  function setPrimaryCsm(value: string) {
    const params = new URLSearchParams(searchParams.toString())
    if (value === 'all') params.delete('primary_csm_id')
    else params.set('primary_csm_id', value)
    router.replace(`${pathname}?${params.toString()}`)
  }

  function clearAll() {
    setSearchValue('')
    router.replace(pathname)
  }

  const hasAnyFilter =
    Array.from(searchParams.entries()).some(
      ([key]) => !['sort', 'dir'].includes(key),
    )

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Search by name or email…"
          value={searchValue}
          onChange={(event) => setSearchValue(event.target.value)}
          className="max-w-sm"
        />
        <select
          className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
          value={searchParams.get('primary_csm_id') ?? 'all'}
          onChange={(event) => setPrimaryCsm(event.target.value)}
        >
          <option value="all">All CSMs</option>
          {primaryCsmOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        {hasAnyFilter ? (
          <Button variant="outline" size="sm" onClick={clearAll}>
            Clear filters
          </Button>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {STATUS_CHIPS.concat(JOURNEY_CHIPS, BOOLEAN_CHIPS).map((chip) => {
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
    </div>
  )
}
