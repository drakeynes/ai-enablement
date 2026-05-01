// Section 7 — Notes.
//
// Free-text notes per client (clients.notes, added in 0012). Renders
// the saved text or a "click to add" affordance when empty. B1 is
// read-only; B2 wires up the inline textarea-on-blur save (the
// existing InlineTextarea component in inline-fields.tsx handles this).

import type { ClientDetail } from '@/lib/db/clients'
import { Section } from './section'

export function NotesSection({ client }: { client: ClientDetail }) {
  const notes = client.notes?.trim() ?? ''
  const isEmpty = notes === ''

  return (
    <Section title="Notes">
      <div
        className={`min-h-24 rounded-md border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50 transition-colors ${
          isEmpty ? 'text-muted-foreground italic border-dashed' : 'whitespace-pre-wrap font-mono'
        }`}
        title="Editing wires up in B2"
      >
        {isEmpty ? 'No notes yet — click to add' : notes}
      </div>
    </Section>
  )
}
