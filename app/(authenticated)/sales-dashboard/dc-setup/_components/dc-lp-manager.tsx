'use client'

import { useState, useTransition } from 'react'

import type { WistiaVideoOption, TypeformOption, TypeformField } from '@/lib/db/landing-page-assets'
import type { AdminDcLandingPage } from '@/lib/db/dc-setup'
import { saveDcLandingPage, setDcLandingPageActive, loadDcTypeformFields, type DcLpInput } from '../actions'
import { Field, inputStyle, primaryBtn, secondaryBtn, dangerBtn, SectionNote } from './ui'

// DC Setup · Landing pages — the dc_landing_pages registry (0132). Rows are
// mostly AUTO-CREATED by ingestion when a campaign's ads point at a new
// digitalcollege.ai URL; this editor is where a human renames them, attaches
// the Typeform / videos / qualification rule, and retires old ones. Videos
// also auto-attach when Wistia sees them play on a registered page — editing
// here is for corrections and for pages Wistia can't see yet.

export function DcLpManager({
  pages,
  wistia,
  typeforms,
}: {
  pages: AdminDcLandingPage[]
  wistia: WistiaVideoOption[]
  typeforms: TypeformOption[]
}) {
  const [adding, setAdding] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {pages.map((p) => (
        <LpCard key={p.slug} page={p} wistia={wistia} typeforms={typeforms} />
      ))}
      {adding ? (
        <LpEditor
          page={null}
          wistia={wistia}
          typeforms={typeforms}
          onDone={() => setAdding(false)}
        />
      ) : (
        <div>
          <button type="button" style={secondaryBtn(false)} onClick={() => setAdding(true)}>
            + Add landing page
          </button>
          <SectionNote text="Usually not needed — a new funnel registers itself here as soon as its ads run. Add manually only for a page that has no campaign yet." />
        </div>
      )}
    </div>
  )
}

function LpCard({
  page,
  wistia,
  typeforms,
}: {
  page: AdminDcLandingPage
  wistia: WistiaVideoOption[]
  typeforms: TypeformOption[]
}) {
  const [editing, setEditing] = useState(false)
  const [pending, startTransition] = useTransition()
  const [msg, setMsg] = useState<string | null>(null)
  const tfTitle = typeforms.find((t) => t.formId === page.typeformId)?.title

  if (editing) {
    return (
      <LpEditor page={page} wistia={wistia} typeforms={typeforms} onDone={() => setEditing(false)} />
    )
  }
  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="geg-serif" style={{ fontSize: 16, color: 'var(--color-geg-text)' }}>
          {page.label}
        </span>
        <span className="geg-mono" style={{ fontSize: 10.5, color: 'var(--color-geg-text-faint)' }}>
          {page.lpUrl}
        </span>
        {page.autoCreated ? <Tag text="auto-detected" /> : null}
        {!page.active ? <Tag text="Inactive" /> : null}
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button type="button" disabled={pending} style={secondaryBtn(pending)} onClick={() => setEditing(true)}>
            Edit
          </button>
          <button
            type="button"
            disabled={pending}
            style={page.active ? dangerBtn(pending) : primaryBtn(pending)}
            onClick={() => {
              if (
                page.active &&
                !window.confirm(`Retire "${page.label}"? It disappears from the DC Ads dropdown; history stays counted.`)
              )
                return
              setMsg(null)
              startTransition(async () => {
                const res = await setDcLandingPageActive(page.slug, !page.active)
                setMsg(res.ok ? (page.active ? 'Retired.' : 'Restored.') : `Error: ${res.error}`)
              })
            }}
          >
            {page.active ? 'Retire' : 'Restore'}
          </button>
        </span>
      </div>
      <div className="geg-mono" style={{ marginTop: 8, fontSize: 11, color: 'var(--color-geg-text-2)', lineHeight: 1.9 }}>
        Typeform: {tfTitle ?? page.typeformId ?? '— none —'}
        {' · '}Videos: {page.vsl.length ? page.vsl.map((v) => v.label).join(', ') : '— none —'}
        {' · '}Qualifies on: {page.qualifyAnswers.length ? `“${page.qualifyAnswers.join('” / “')}”` : '— not set —'}
        {page.pageUrls.length ? ` · Extra funnel pages: ${page.pageUrls.join(', ')}` : ''}
      </div>
      {msg ? <div className="geg-mono" style={{ marginTop: 6, fontSize: 11.5, color: msg.startsWith('Error') ? 'var(--color-geg-danger, #c0392b)' : 'var(--color-geg-text-2)' }}>{msg}</div> : null}
    </div>
  )
}

// One editor for add + edit.
function LpEditor({
  page,
  wistia,
  typeforms,
  onDone,
}: {
  page: AdminDcLandingPage | null
  wistia: WistiaVideoOption[]
  typeforms: TypeformOption[]
  onDone: () => void
}) {
  const [state, setState] = useState(() => ({
    label: page?.label ?? '',
    lpUrl: page?.lpUrl ?? '',
    pageUrls: (page?.pageUrls ?? []).join('\n'),
    typeformId: page?.typeformId ?? '',
    vsl: page?.vsl ?? [],
    confirmVideoHashedId: page?.confirmVideoHashedId ?? '',
    qualifyFieldRef: page?.qualifyFieldRef ?? '',
    qualifyAnswers: page?.qualifyAnswers ?? [],
  }))
  const [fields, setFields] = useState<TypeformField[] | null>(null)
  const [pending, startTransition] = useTransition()
  const [msg, setMsg] = useState<string | null>(null)
  const set = (patch: Partial<typeof state>) => setState((prev) => ({ ...prev, ...patch }))

  const addVideo = (hashedId: string) => {
    if (!hashedId || state.vsl.some((v) => v.hashedId === hashedId)) return
    const name = wistia.find((w) => w.hashedId === hashedId)?.name ?? hashedId
    set({ vsl: [...state.vsl, { hashedId, label: name }] })
  }

  const loadFields = (formId: string) => {
    setFields(null)
    if (!formId) return
    startTransition(async () => {
      setFields(await loadDcTypeformFields(formId))
    })
  }

  const chosenField = fields?.find((f) => f.ref === state.qualifyFieldRef) ?? null

  const onSave = () => {
    if (!state.label.trim()) return setMsg('Error: give it a name.')
    if (!state.lpUrl.trim()) return setMsg('Error: the page URL is required.')
    setMsg(null)
    const input: DcLpInput = {
      slug: page?.slug,
      label: state.label,
      lpUrl: state.lpUrl,
      pageUrls: state.pageUrls.split('\n').map((s) => s.trim()).filter(Boolean),
      typeformId: state.typeformId || null,
      vsl: state.vsl,
      confirmVideoHashedId: state.confirmVideoHashedId || null,
      confirmVideoLabel: state.confirmVideoHashedId
        ? (wistia.find((w) => w.hashedId === state.confirmVideoHashedId)?.name ?? null)
        : null,
      qualifyFieldRef: state.qualifyFieldRef || null,
      qualifyAnswers: state.qualifyAnswers,
      active: page?.active ?? true,
    }
    startTransition(async () => {
      const res = await saveDcLandingPage(input)
      if (!res.ok) {
        if (res.error.startsWith('url_already_used_by:')) {
          setMsg(`Error: that URL already belongs to "${res.error.split(':')[1]}".`)
        } else setMsg(`Error: ${res.error}`)
        return
      }
      onDone()
    })
  }

  return (
    <div style={{ ...cardStyle, borderColor: 'var(--color-geg-accent)' }}>
      <div className="geg-mono" style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-geg-text)', marginBottom: 12 }}>
        {page ? `Edit · ${page.label}` : 'Add landing page'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12 }}>
        <Field label="Name (shown in the dropdown)">
          <input style={inputStyle} value={state.label} onChange={(e) => set({ label: e.target.value })} placeholder="join/training" />
        </Field>
        <Field label="Page URL">
          <input
            style={inputStyle}
            value={state.lpUrl}
            onChange={(e) => set({ lpUrl: e.target.value })}
            placeholder="https://join.digitalcollege.ai/training"
            className="geg-mono"
          />
        </Field>
        <Field label="Typeform on this funnel">
          <select
            style={inputStyle}
            value={state.typeformId}
            onChange={(e) => {
              set({ typeformId: e.target.value, qualifyFieldRef: '', qualifyAnswers: [] })
              loadFields(e.target.value)
            }}
          >
            <option value="">— none —</option>
            {typeforms.map((t) => (
              <option key={t.formId} value={t.formId}>{t.title}</option>
            ))}
          </select>
        </Field>
        <Field label="Confirmation-page video (optional)">
          <select style={inputStyle} value={state.confirmVideoHashedId} onChange={(e) => set({ confirmVideoHashedId: e.target.value })}>
            <option value="">— none —</option>
            {wistia.map((w) => (
              <option key={w.hashedId} value={w.hashedId}>{w.name}</option>
            ))}
          </select>
        </Field>
      </div>

      <div style={{ marginTop: 12 }}>
        <Field label="Videos on this funnel">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {state.vsl.map((v) => (
              <span key={v.hashedId} className="geg-mono" style={{ fontSize: 11, border: '1px solid var(--color-geg-border)', borderRadius: 5, padding: '4px 8px', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                {v.label}
                <button
                  type="button"
                  onClick={() => set({ vsl: state.vsl.filter((x) => x.hashedId !== v.hashedId) })}
                  style={{ background: 'none', border: 'none', color: 'var(--color-geg-text-faint)', cursor: 'pointer', padding: 0 }}
                  aria-label={`Remove ${v.label}`}
                >
                  ×
                </button>
              </span>
            ))}
            <select style={{ ...inputStyle, width: 260 }} value="" onChange={(e) => addVideo(e.target.value)}>
              <option value="">+ add a video…</option>
              {wistia.map((w) => (
                <option key={w.hashedId} value={w.hashedId}>{w.name}</option>
              ))}
            </select>
          </div>
        </Field>
        <SectionNote text="Videos usually attach themselves once Wistia sees them play on the page — add manually only when that hasn't happened yet." />
      </div>

      <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12 }}>
        <Field label="Qualification question">
          <select
            style={inputStyle}
            value={state.qualifyFieldRef}
            onFocus={() => { if (!fields && state.typeformId) loadFields(state.typeformId) }}
            onChange={(e) => set({ qualifyFieldRef: e.target.value, qualifyAnswers: [] })}
          >
            <option value="">{state.typeformId ? (fields ? '— pick a question —' : 'loading questions…') : 'pick a Typeform first'}</option>
            {(fields ?? []).filter((f) => f.choices.length > 0).map((f) => (
              <option key={f.ref} value={f.ref}>{f.title}</option>
            ))}
            {state.qualifyFieldRef && !fields ? (
              <option value={state.qualifyFieldRef}>(current question)</option>
            ) : null}
          </select>
        </Field>
        <Field label="Answers that count as QUALIFIED">
          {chosenField ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {chosenField.choices.map((choice) => (
                <label key={choice.label} className="geg-mono" style={{ fontSize: 11.5, color: 'var(--color-geg-text-2)', display: 'flex', gap: 7, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={state.qualifyAnswers.includes(choice.label)}
                    onChange={(e) =>
                      set({
                        qualifyAnswers: e.target.checked
                          ? [...state.qualifyAnswers, choice.label]
                          : state.qualifyAnswers.filter((a) => a !== choice.label),
                      })
                    }
                  />
                  {choice.label}
                </label>
              ))}
            </div>
          ) : (
            <div className="geg-mono" style={{ fontSize: 11, color: 'var(--color-geg-text-faint)', lineHeight: 1.6 }}>
              {state.qualifyAnswers.length
                ? `Currently: “${state.qualifyAnswers.join('” / “')}”`
                : 'Pick the question to see its answers.'}
            </div>
          )}
        </Field>
      </div>

      <div style={{ marginTop: 12 }}>
        <Field label="Extra funnel pages (one URL per line — pages after the opt-in that show this funnel's videos)">
          <textarea
            style={{ ...inputStyle, minHeight: 54, fontFamily: 'inherit' }}
            value={state.pageUrls}
            onChange={(e) => set({ pageUrls: e.target.value })}
            placeholder={'join.digitalcollege.ai/t-2'}
          />
        </Field>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
        <button type="button" disabled={pending} style={primaryBtn(pending)} onClick={onSave}>
          Save
        </button>
        <button type="button" disabled={pending} style={secondaryBtn(pending)} onClick={onDone}>
          Cancel
        </button>
        {msg ? (
          <span className="geg-mono" style={{ fontSize: 11.5, color: 'var(--color-geg-danger, #c0392b)' }}>{msg}</span>
        ) : null}
      </div>
    </div>
  )
}

function Tag({ text }: { text: string }) {
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 9.5,
        letterSpacing: '0.07em',
        textTransform: 'uppercase',
        color: 'var(--color-geg-text-faint)',
        border: '1px solid var(--color-geg-border)',
        borderRadius: 4,
        padding: '2px 7px',
      }}
    >
      {text}
    </span>
  )
}

const cardStyle: React.CSSProperties = {
  border: '1px solid var(--color-geg-border)',
  background: 'var(--color-geg-bg-elev)',
  borderRadius: 8,
  padding: '16px 18px',
}
