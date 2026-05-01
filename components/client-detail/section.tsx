// Collapsible section wrapper for the client detail page. Default
// expanded; click the heading to toggle. Uses native <details>/<summary>
// so it works without a client component — server components only.
//
// B2 will likely wrap edit-state inside individual sections; the
// boundary stays identical so swapping in a client component for one
// section doesn't ripple through the page.

import type { ReactNode } from 'react'

export function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details open={defaultOpen} className="group space-y-3">
      <summary className="cursor-pointer text-lg font-semibold list-none flex items-center gap-2 select-none">
        <span className="inline-block w-3 text-muted-foreground transition-transform group-open:rotate-90">
          ▶
        </span>
        {title}
      </summary>
      <div className="space-y-3 pt-2 pl-5">{children}</div>
    </details>
  )
}

export function Subsection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details open={defaultOpen} className="group space-y-2">
      <summary className="cursor-pointer text-sm font-medium text-muted-foreground list-none flex items-center gap-2 select-none">
        <span className="inline-block w-3 text-muted-foreground transition-transform group-open:rotate-90">
          ▶
        </span>
        {title}
      </summary>
      <div className="space-y-2 pt-1 pl-5">{children}</div>
    </details>
  )
}
