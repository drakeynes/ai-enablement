// Visual treatment for clients.nps_standing.
//
// Renders the lowercase DB value as a capitalized Airtable-form pill:
//   'promoter' → 'Strong / Promoter'  (indigo)
//   'neutral'  → 'Neutral'            (slate)
//   'at_risk'  → 'At Risk'            (orange)
// null / unrecognized → em-dash placeholder.
//
// Color scheme deliberately distinct from the status pills in
// app/(authenticated)/clients/pills.tsx (emerald / amber / zinc / slate /
// rose) so a row carrying both csm_standing context and an NPS Standing
// pill in close visual proximity (Section 2 of the client detail page)
// stays readable.
//
// Display strings track docs/agents/gregory.md § Airtable NPS integration.
// If the receiver's segment normalization ever expands beyond the three
// known forms, update both here and the receiver's _SEGMENT_NORMALIZATION.

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const NPS_STANDING_DISPLAY: Record<string, string> = {
  promoter: 'Strong / Promoter',
  neutral: 'Neutral',
  at_risk: 'At Risk',
}

const NPS_STANDING_CLASSES: Record<string, string> = {
  promoter: 'bg-indigo-100 text-indigo-900 border-indigo-200',
  neutral: 'bg-slate-100 text-slate-800 border-slate-300',
  at_risk: 'bg-orange-100 text-orange-900 border-orange-200',
}

export function NpsStandingPill({ value }: { value: string | null }) {
  if (!value) {
    return <span className="text-sm text-muted-foreground">—</span>
  }
  const label = NPS_STANDING_DISPLAY[value] ?? value
  const cls =
    NPS_STANDING_CLASSES[value] ??
    'bg-zinc-100 text-zinc-700 border-zinc-200'
  return <Badge className={cn('border font-normal', cls)}>{label}</Badge>
}
