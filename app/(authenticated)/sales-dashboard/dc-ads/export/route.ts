import { NextResponse, type NextRequest } from 'next/server'

import { createClient } from '@/lib/supabase/server'
import {
  getDcAdsTranscriptExportIds,
  getDcAdsTranscriptSections,
  type DcAdsTranscriptSection,
} from '@/lib/db/dc-ads'

// DC Calls transcript export (0156, Nabeel 2026-08-19: raw transcripts to
// feed into an AI). Returns ONE markdown file — per call: the review
// verdict header + the conversation as speaker-labelled turns (built in
// SQL; see migration 0156).
//
//   POST {}                      → everything (every dc_ads-reviewed call)
//   POST { callIds: [...] }      → exactly those calls ("Export this view" —
//                                  the feed sends what it currently lists)
//   GET  ?call=<close_call_id>   → one call (the review page's plain link)
//
// Auth: the dashboard session (same Supabase check the layout runs — this
// is a route handler, so the layout's gate doesn't cover it). Lives under
// /sales-dashboard/dc-ads so the middleware allowlist admits it. The file
// contains PII by nature — it goes only to a logged-in browser, same as
// the pages that already display it.
//
// scripts/export_dc_transcripts.py is the offline sibling (same format).

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const ET_FMT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

function fmtDur(s: number): string {
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.floor(s - m * 60)).padStart(2, '0')}`
}

function section(s: DcAdsTranscriptSection): string {
  let outcome = s.closed ? 'CLOSED on this call' : `not closed — ${s.whyNotClosed ?? 'unknown'}`
  if (s.repGap) outcome += ` (rep gap: ${s.repGap})`
  const meta =
    `Outcome: ${outcome} · archetype ${s.archetype ?? '—'} · AI scores: ` +
    `lead ${s.leadScore} / intent ${s.intent} / offer understanding ${s.offerUnderstanding} / ` +
    `rep execution ${s.repScore}`
  const body = s.turns?.trim() || '_(no transcript text)_'
  return `## ${ET_FMT.format(new Date(s.at))} ET — ${s.leadName} × rep ${s.repName ?? '—'} (${fmtDur(s.durationS)})\n\n${meta}\n\n${body}\n`
}

function buildMarkdown(sections: DcAdsTranscriptSection[], scope: string): string {
  const first = sections[0] ? ET_FMT.format(new Date(sections[0].at)) : ''
  const last = sections.at(-1) ? ET_FMT.format(new Date(sections.at(-1)!.at)) : ''
  const header =
    `# Digital College — ad-lead call transcripts (${scope})\n\n` +
    `${sections.length} connected call${sections.length === 1 ? '' : 's'}` +
    (first ? ` (${first} → ${last} ET)` : '') +
    ', transcribed by Deepgram, each headed by the AI call review’s verdict ' +
    '(outcome, archetype, 0-10 scores for lead quality / buying intent / offer ' +
    'understanding / rep execution). Speaker labels come from automatic diarization ' +
    'and don’t say who the rep is — the header names the rep. CONTAINS PII — do not publish.\n'
  return header + '\n---\n\n' + sections.map(section).join('\n---\n\n')
}

async function authed(): Promise<boolean> {
  // Same preview bypass the layout honors — Playwright verification only.
  if (process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true') return true
  const supabase = createClient()
  const { data } = await supabase.auth.getUser()
  return !!data.user
}

function fileResponse(md: string, scope: string): NextResponse {
  const day = new Date().toISOString().slice(0, 10)
  return new NextResponse(md, {
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
      'Content-Disposition': `attachment; filename="dc-call-transcripts-${scope}-${day}.md"`,
      'Cache-Control': 'no-store',
    },
  })
}

export async function GET(req: NextRequest) {
  if (!(await authed())) return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  const callId = req.nextUrl.searchParams.get('call')?.trim()
  if (!callId) return NextResponse.json({ error: 'call_required' }, { status: 400 })
  const sections = await getDcAdsTranscriptSections([callId])
  if (sections.length === 0) {
    return NextResponse.json({ error: 'no_dc_transcript_for_call' }, { status: 404 })
  }
  return fileResponse(buildMarkdown(sections, 'one-call'), 'call')
}

export async function POST(req: NextRequest) {
  if (!(await authed())) return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  let callIds: string[] | undefined
  try {
    const body = (await req.json()) as { callIds?: unknown }
    if (Array.isArray(body.callIds)) {
      callIds = body.callIds.filter((v): v is string => typeof v === 'string').slice(0, 5000)
    }
  } catch {
    // empty/absent body = export all
  }
  const scope = callIds ? 'view' : 'all'
  const ids = callIds ?? (await getDcAdsTranscriptExportIds())
  if (ids.length === 0) return NextResponse.json({ error: 'nothing_to_export' }, { status: 404 })
  const sections = await getDcAdsTranscriptSections(ids)
  return fileResponse(buildMarkdown(sections, scope === 'all' ? 'everything' : 'current view'), scope)
}
