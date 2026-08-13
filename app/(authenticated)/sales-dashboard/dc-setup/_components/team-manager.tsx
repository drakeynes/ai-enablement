'use client'

import { useState, useTransition } from 'react'

import type { SalesRole } from '@/lib/db/sales-rep-verify-shared'
import type {
  CloseUserOption,
  DcRepCandidate,
  DcTeamMember,
  DismissedCandidate,
  UnmappedDcCaller,
} from '@/lib/db/dc-setup'
import type { RepDraftInput } from '../../reps/actions'
import {
  dcVerifyRep,
  dcSaveRepDraft,
  dcDismissRepCandidate,
  dcRestoreRepCandidate,
  updateTeamMember,
  setTeamMemberActive,
} from '../actions'
import { Field, inputStyle, primaryBtn, secondaryBtn, dangerBtn, SectionNote } from './ui'

// DC Setup · Team — who shows up on the DC Ads by-rep table and roster.
// Three blocks:
//   1. New reps to verify — the Airtable-sourced queue; confirming one links
//      their form identity (record id) + Close identity (picker, pre-filled
//      with a name-match suggestion) into ONE team_members row.
//   2. Current team — edit / deactivate / reactivate (the turnover path).
//   3. Seen dialing, not on the team — read-only radar; the fix is adding
//      the person to the Airtable Sales Team Member table.

const ROLE_OPTIONS: { value: SalesRole; label: string }[] = [
  { value: 'setter', label: 'Setter' },
  { value: 'closer', label: 'Closer' },
  { value: 'dc_closer', label: 'DC Closer' },
]

type ActionResult = { ok: true } | { ok: false; error: string }

function useAction() {
  const [pending, startTransition] = useTransition()
  const [msg, setMsg] = useState<string | null>(null)
  const run = (fn: () => Promise<ActionResult>, okMsg: string) => {
    setMsg(null)
    startTransition(async () => {
      const res = await fn()
      setMsg(res.ok ? okMsg : `Error: ${friendly(res.error)}`)
    })
  }
  return { pending, msg, setMsg, run }
}

function friendly(code: string): string {
  if (code === 'forbidden') return 'you need admin access for this.'
  if (code === 'full_name_required') return 'full name is required.'
  if (code === 'email_required') return 'email is required.'
  if (code === 'sales_role_required' || code === 'invalid_sales_role') return 'pick a role.'
  if (code === 'close_user_id_required') return 'pick their Close user.'
  if (code === 'duplicate_identity')
    return 'that email or identity already belongs to another team member.'
  return code
}

export function TeamManager({
  candidates,
  closeUsers,
  team,
  unmapped,
  dismissed,
}: {
  candidates: DcRepCandidate[]
  closeUsers: CloseUserOption[]
  team: DcTeamMember[]
  unmapped: UnmappedDcCaller[]
  dismissed: DismissedCandidate[]
}) {
  const activeCount = team.filter((t) => t.isActive).length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div>
        <BlockTitle
          title={`New reps to verify · ${candidates.length}`}
          hint="New people added to the Airtable “Sales Team Member” table appear here within ~30 minutes. Confirm their details once and every dashboard picks them up."
        />
        {candidates.length === 0 ? (
          <EmptyNote text="Nobody waiting. Add new hires to the Airtable Sales Team Member table and they'll show up here." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {candidates.map((c) => (
              <CandidateCard key={c.airtableRecordId} candidate={c} closeUsers={closeUsers} />
            ))}
          </div>
        )}
        {dismissed.length > 0 ? <DismissedList dismissed={dismissed} /> : null}
      </div>

      <div>
        <BlockTitle
          title={`Current team · ${activeCount} active · ${team.length - activeCount} inactive`}
          hint="Someone left? Deactivate them — their history stays counted, they just stop showing as active. Rehired? Reactivate."
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {team.map((m) => (
            <MemberRow key={m.id} member={m} closeUsers={closeUsers} />
          ))}
        </div>
      </div>

      {unmapped.length > 0 ? (
        <div>
          <BlockTitle
            title={`Seen dialing DC leads, not on the team · ${unmapped.length}`}
            hint="These people are making calls but aren't set up. Add them to the Airtable Sales Team Member table — they'll appear in the verify queue above."
          />
          <div
            className="geg-mono"
            style={{ fontSize: 12, color: 'var(--color-geg-text-2)', lineHeight: 2 }}
          >
            {unmapped.map((u) => (
              <div key={u.closeUserId}>
                {u.name}{' '}
                <span style={{ color: 'var(--color-geg-text-faint)' }}>
                  · {u.dials.toLocaleString('en-US')} dials
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------

function CandidateCard({
  candidate,
  closeUsers,
}: {
  candidate: DcRepCandidate
  closeUsers: CloseUserOption[]
}) {
  const c = candidate
  const [state, setState] = useState(() => {
    // The pre-selected Close account (saved draft, else the suggestion) must
    // ALSO seed the email — a pre-selection never fires the picker's
    // onChange, so without this the email field sits empty while the
    // dropdown clearly shows one (Drake 2026-08-13, verifying Justin).
    const preselected = c.draft?.closeUserId ?? c.suggestedCloseUserId ?? ''
    const preselectedEmail = closeUsers.find((x) => x.closeUserId === preselected)?.email ?? ''
    return {
      fullName: c.draft?.fullName ?? c.fullName ?? '',
      salesRole: (c.draft?.salesRole ?? 'setter') as SalesRole | '',
      email: c.draft?.email ?? preselectedEmail,
      closeUserId: preselected,
    }
  })
  const { pending, msg, setMsg, run } = useAction()

  const set = (patch: Partial<typeof state>) => setState((prev) => ({ ...prev, ...patch }))
  const onPickCloseUser = (closeUserId: string) => {
    const u = closeUsers.find((x) => x.closeUserId === closeUserId)
    set({ closeUserId, email: u?.email ?? state.email })
  }
  const toInput = (): RepDraftInput => ({
    airtableRecordId: c.airtableRecordId,
    fullName: state.fullName || null,
    salesRole: (state.salesRole || null) as SalesRole | null,
    email: state.email || null,
    closeUserId: state.closeUserId || null,
    calendlyEventTypeUri: null,
  })

  const usingSuggestion =
    !!state.closeUserId && state.closeUserId === c.suggestedCloseUserId && !c.draft?.closeUserId

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
        <span className="geg-serif" style={{ fontSize: 16, color: 'var(--color-geg-text)' }}>
          {c.fullName ?? '(unnamed)'}
        </span>
        <span className="geg-mono" style={{ fontSize: 10, color: 'var(--color-geg-text-faint)' }}>
          {c.jobTitle ?? 'no job title'}
          {c.airtableCreatedAt ? ` · added ${c.airtableCreatedAt.slice(0, 10)}` : ''}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <Field label="Full name">
          <input style={inputStyle} value={state.fullName} onChange={(e) => set({ fullName: e.target.value })} />
        </Field>
        <Field label="Role">
          <select style={inputStyle} value={state.salesRole} onChange={(e) => set({ salesRole: e.target.value as SalesRole | '' })}>
            <option value="">— pick —</option>
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </Field>
        <Field label={usingSuggestion ? 'Their Close account · suggested, confirm' : 'Their Close account'}>
          <select
            style={{ ...inputStyle, ...(usingSuggestion ? { borderColor: 'var(--color-geg-accent)' } : null) }}
            value={state.closeUserId}
            onChange={(e) => onPickCloseUser(e.target.value)}
          >
            <option value="">— pick from Close —</option>
            {closeUsers.map((u) => (
              <option key={u.closeUserId} value={u.closeUserId}>
                {u.fullName ?? u.email ?? u.closeUserId}
                {u.email ? ` · ${u.email}` : ''}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Email">
          <input style={inputStyle} type="email" value={state.email} onChange={(e) => set({ email: e.target.value })} placeholder="filled by the Close pick" />
        </Field>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
        <button
          type="button"
          disabled={pending}
          style={primaryBtn(pending)}
          onClick={() => {
            if (!state.fullName.trim()) return setMsg('Error: full name is required.')
            if (!state.salesRole) return setMsg('Error: pick a role.')
            if (!state.closeUserId) return setMsg('Error: pick their Close account.')
            // Self-heal: an empty email fills from the selected Close account
            // before validating (belt to the pre-selection seeding above).
            const email =
              state.email.trim() ||
              closeUsers.find((x) => x.closeUserId === state.closeUserId)?.email ||
              ''
            if (!email) return setMsg('Error: that Close account has no email on file — type one in.')
            if (email !== state.email) set({ email })
            run(() => dcVerifyRep({ ...toInput(), email }), 'Verified — they now show up everywhere.')
          }}
        >
          Verify
        </button>
        <button type="button" disabled={pending} style={secondaryBtn(pending)} onClick={() => run(() => dcSaveRepDraft(toInput()), 'Saved for later.')}>
          Save for later
        </button>
        <button
          type="button"
          disabled={pending}
          style={dangerBtn(pending)}
          onClick={() => {
            if (!window.confirm('Dismiss this candidate? Use this for test/junk rows only.')) return
            run(() => dcDismissRepCandidate(c.airtableRecordId), 'Dismissed.')
          }}
        >
          Dismiss
        </button>
        {msg ? <Msg msg={msg} /> : null}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function MemberRow({ member, closeUsers }: { member: DcTeamMember; closeUsers: CloseUserOption[] }) {
  const [editing, setEditing] = useState(false)
  const [state, setState] = useState(() => ({
    fullName: member.fullName,
    salesRole: (member.salesRole ?? 'setter') as SalesRole,
    email: member.email ?? '',
    closeUserId: member.closeUserId ?? '',
  }))
  const { pending, msg, run } = useAction()
  const set = (patch: Partial<typeof state>) => setState((prev) => ({ ...prev, ...patch }))

  const roleLabel = ROLE_OPTIONS.find((r) => r.value === member.salesRole)?.label ?? member.salesRole ?? '—'

  return (
    <div style={{ ...cardStyle, opacity: member.isActive ? 1 : 0.6, padding: '12px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="geg-serif" style={{ fontSize: 15, color: 'var(--color-geg-text)', minWidth: 160 }}>
          {member.fullName}
        </span>
        <Chip text={roleLabel} />
        {!member.isActive ? <Chip text="Inactive" faint /> : null}
        <span className="geg-mono" style={{ fontSize: 10, color: 'var(--color-geg-text-faint)' }}>
          {member.closeUserId ? `Close ✓ ${member.closeUserName ?? ''}` : 'Close —'}
          {' · '}
          {member.airtableUserId ? 'Forms ✓' : 'Forms —'}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button type="button" disabled={pending} style={secondaryBtn(pending)} onClick={() => setEditing((v) => !v)}>
            {editing ? 'Close' : 'Edit'}
          </button>
          <button
            type="button"
            disabled={pending}
            style={member.isActive ? dangerBtn(pending) : primaryBtn(pending)}
            onClick={() => {
              if (member.isActive && !window.confirm(`Deactivate ${member.fullName}? Their history stays; they stop showing as active.`)) return
              run(
                () => setTeamMemberActive(member.id, !member.isActive),
                member.isActive ? 'Deactivated.' : 'Reactivated.',
              )
            }}
          >
            {member.isActive ? 'Deactivate' : 'Reactivate'}
          </button>
        </span>
      </div>
      {editing ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
            <Field label="Full name">
              <input style={inputStyle} value={state.fullName} onChange={(e) => set({ fullName: e.target.value })} />
            </Field>
            <Field label="Role">
              <select style={inputStyle} value={state.salesRole} onChange={(e) => set({ salesRole: e.target.value as SalesRole })}>
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Their Close account">
              <select style={inputStyle} value={state.closeUserId} onChange={(e) => set({ closeUserId: e.target.value })}>
                <option value="">— none —</option>
                {closeUsers.map((u) => (
                  <option key={u.closeUserId} value={u.closeUserId}>
                    {u.fullName ?? u.email ?? u.closeUserId}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Email">
              <input style={inputStyle} type="email" value={state.email} onChange={(e) => set({ email: e.target.value })} />
            </Field>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
            <button
              type="button"
              disabled={pending}
              style={primaryBtn(pending)}
              onClick={() =>
                run(
                  () =>
                    updateTeamMember({
                      id: member.id,
                      fullName: state.fullName,
                      salesRole: state.salesRole,
                      email: state.email,
                      closeUserId: state.closeUserId || null,
                      airtableUserId: member.airtableUserId,
                      calendlyEventTypeUri: member.calendlyEventTypeUri,
                    }),
                  'Saved.',
                )
              }
            >
              Save changes
            </button>
            {msg ? <Msg msg={msg} /> : null}
          </div>
        </div>
      ) : msg ? (
        <div style={{ marginTop: 8 }}>
          <Msg msg={msg} />
        </div>
      ) : null}
    </div>
  )
}

// Collapsed safety net for accidental dismissals — Restore puts the person
// straight back in the verify queue.
function DismissedList({ dismissed }: { dismissed: DismissedCandidate[] }) {
  const { pending, msg, run } = useAction()
  return (
    <details style={{ marginTop: 10 }}>
      <summary
        className="geg-mono"
        style={{
          fontSize: 10,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--color-geg-text-faint)',
          cursor: 'pointer',
        }}
      >
        Dismissed ({dismissed.length}) — click to show
      </summary>
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {dismissed.map((d) => (
          <div
            key={d.airtableRecordId}
            style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0' }}
          >
            <span className="geg-serif" style={{ fontSize: 13.5, color: 'var(--color-geg-text-2)', minWidth: 140 }}>
              {d.fullName ?? d.airtableRecordId}
            </span>
            <span className="geg-mono" style={{ fontSize: 10, color: 'var(--color-geg-text-faint)' }}>
              dismissed {d.dismissedAt ? d.dismissedAt.slice(0, 10) : '—'}
            </span>
            <button
              type="button"
              disabled={pending}
              style={secondaryBtn(pending)}
              onClick={() =>
                run(() => dcRestoreRepCandidate(d.airtableRecordId), 'Restored — back in the queue above.')
              }
            >
              Restore
            </button>
          </div>
        ))}
        {msg ? <Msg msg={msg} /> : null}
      </div>
    </details>
  )
}

// ---------------------------------------------------------------------------

function BlockTitle({ title, hint }: { title: string; hint: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        className="geg-mono"
        style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-geg-text)' }}
      >
        {title}
      </div>
      <SectionNote text={hint} />
    </div>
  )
}

function EmptyNote({ text }: { text: string }) {
  return (
    <div
      style={{
        border: '1px dashed var(--color-geg-border)',
        borderRadius: 8,
        padding: '18px 20px',
        color: 'var(--color-geg-text-faint)',
        fontSize: 13,
      }}
    >
      {text}
    </div>
  )
}

function Chip({ text, faint }: { text: string; faint?: boolean }) {
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 9.5,
        letterSpacing: '0.07em',
        textTransform: 'uppercase',
        color: faint ? 'var(--color-geg-text-faint)' : 'var(--color-geg-text-2)',
        border: '1px solid var(--color-geg-border)',
        borderRadius: 4,
        padding: '2px 7px',
      }}
    >
      {text}
    </span>
  )
}

function Msg({ msg }: { msg: string }) {
  return (
    <span
      className="geg-mono"
      style={{
        fontSize: 11.5,
        color: msg.startsWith('Error') ? 'var(--color-geg-danger, #c0392b)' : 'var(--color-geg-text-2)',
      }}
    >
      {msg}
    </span>
  )
}

const cardStyle: React.CSSProperties = {
  border: '1px solid var(--color-geg-border)',
  background: 'var(--color-geg-bg-elev)',
  borderRadius: 8,
  padding: '16px 18px',
}
