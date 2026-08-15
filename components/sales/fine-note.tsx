// Fine-print/definition blocks (mobile pass 2026-08-15): desktop renders the
// full text as before; on a phone the same content collapses behind a small
// "Definitions & notes" toggle — the walls of 9px mono text were most of the
// scroll on mobile. Server-safe (native <details>, no JS).

export function FineNote({
  children,
  summary = 'Definitions & notes',
  style,
}: {
  children: React.ReactNode
  summary?: string
  style?: React.CSSProperties
}) {
  const base: React.CSSProperties = {
    fontSize: 9,
    letterSpacing: '0.05em',
    color: 'var(--color-geg-text-faint)',
    lineHeight: 1.7,
    ...style,
  }
  return (
    <>
      <div className="hidden md:block geg-mono" style={base}>
        {children}
      </div>
      <details className="md:hidden geg-mono" style={base}>
        <summary
          style={{
            cursor: 'pointer',
            fontSize: 9.5,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--color-geg-text-3)',
          }}
        >
          {summary}
        </summary>
        <div style={{ marginTop: 6 }}>{children}</div>
      </details>
    </>
  )
}
