'use client'

// Shared form primitives for the DC Setup sections — the Field/input/button
// helpers the landing-pages + outbound-campaigns managers each carry a copy
// of, extracted once for this page's three managers.

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block' }}>
      <span
        className="geg-mono"
        style={{
          display: 'block',
          fontSize: 10,
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          color: 'var(--color-geg-text-faint)',
          marginBottom: 5,
        }}
      >
        {label}
      </span>
      {children}
    </label>
  )
}

export function SectionNote({ text }: { text: string }) {
  return (
    <div
      style={{
        fontSize: 12.5,
        color: 'var(--color-geg-text-3)',
        lineHeight: 1.55,
        marginTop: 4,
        maxWidth: 720,
      }}
    >
      {text}
    </div>
  )
}

export const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '7px 9px',
  fontSize: 13,
  borderRadius: 5,
  border: '1px solid var(--color-geg-border)',
  background: 'var(--color-geg-bg)',
  color: 'var(--color-geg-text)',
}

function baseBtn(pending: boolean): React.CSSProperties {
  return {
    fontSize: 12.5,
    padding: '7px 16px',
    borderRadius: 5,
    cursor: pending ? 'default' : 'pointer',
    opacity: pending ? 0.55 : 1,
    border: '1px solid var(--color-geg-border)',
    fontFamily: 'var(--font-prom-sans), Inter, system-ui, sans-serif',
  }
}

export function primaryBtn(pending: boolean): React.CSSProperties {
  return {
    ...baseBtn(pending),
    background: 'var(--color-geg-accent)',
    borderColor: 'var(--color-geg-accent)',
    color: '#fff',
    fontWeight: 600,
  }
}

export function secondaryBtn(pending: boolean): React.CSSProperties {
  return {
    ...baseBtn(pending),
    background: 'var(--color-geg-bg-elev)',
    color: 'var(--color-geg-text)',
  }
}

export function dangerBtn(pending: boolean): React.CSSProperties {
  return {
    ...baseBtn(pending),
    background: 'transparent',
    color: 'var(--color-geg-text-faint)',
  }
}
