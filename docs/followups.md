# Followups

Ops reminders and known gaps that aren't "ideas to build" (those live in `docs/future-ideas.md`) and aren't "decisions to revisit" (those are ADRs under `docs/decisions/`). These are things to verify, be aware of, or handle when the moment surfaces.

**Entry format.** Short. Four lines:

- **What:** one-sentence description.
- **Why it matters:** consequence if ignored.
- **Next action:** concrete step that resolves it (or a check that answers whether it needs resolving).
- **Logged:** date.

---

## Cleanup pass — toggle re-activation for positive-status transitions

- **What:** the M5 master sheet reconcile (2026-05-04) fired status flips going positive (`ghost→active` or `paused→active`) for 2 clients (Marcus Miller, Allison Jayme Boeshans) and possibly more in future runs. The M5.6 cascade is **one-directional** (off-only) — when those clients moved INTO negative status earlier, `accountability_enabled` and `nps_enabled` got flipped to false, and the cascade does NOT auto-revert on positive transitions. So Marcus Miller is now active but `accountability_enabled=false, nps_enabled=false`. Allison Jayme Boeshans appears to have been manually flipped back to true at some point.
- **Why it matters:** an active client with accountability/nps automation off won't get DMs, nudges, or NPS surveys. If Scott expects these clients to receive automation, the toggles need a manual flip or the cleanup script needs a "positive-transition toggle reset" pass.
- **Next action:** two paths. (a) Add a "positive-transition toggle reset" subsection to `scripts/cleanup_master_sheet_reconcile.py` that flips toggles to true when status goes from negative → active. Risk: makes the apply less idempotent (re-running might flip something Scott explicitly wants off). (b) Surface positive-transition clients in scott_notes Bucket B with their current toggle state and let Scott decide per-client. Lean: (b) — keeps the cleanup script's "respect Scott's explicit CSV values" semantics intact.
- **Logged:** 2026-05-04 (M5 master sheet reconcile — Marcus Miller + Allison Jayme Boeshans surfaced this).

## Cleanup pass — Matthew Gibson is in CSV but not Gregory

- **What:** Matthew Gibson (USA row 180, email `leandeavor@gmail.com`, owned by Nico) is on Scott's master sheet as an active client AND is one of the handover-note targets per Scott's morning message. He doesn't exist in Gregory yet (handover note couldn't apply to him; surfaced to scott_notes A6 + A9). 7 other unmatched-with-email or unmatched-without-email CSV rows are similar candidates — see scott_notes A9 + A10.
- **Why it matters:** these clients are operationally real but invisible to Gregory. Scott's daily Gregory review will miss them. Path 2 outbound roster also doesn't include them.
- **Next action:** for each unmatched-with-email row (Matthew Gibson, Anthony Huang, Melvin Dayal): confirm with Scott whether to create or whether they're duplicates of an existing Gregory client (then add to alternate_emails). For unmatched-without-email rows (5 clients): Scott decides per row. Once Matthew Gibson is created, re-run the cleanup script — the handover-note append is idempotent and will pick him up.
- **Logged:** 2026-05-04 (M5 master sheet reconcile A6/A9/A10).

## Cleanup pass — re-run cadence + idempotency monitoring

- **What:** `scripts/cleanup_master_sheet_reconcile.py` is designed to be re-run as Scott edits the master sheet. The first run (2026-05-04) made 95 explicit DB writes touching ~70 unique clients. Idempotency is achieved per-RPC (no-op when unchanged), per-trustpilot (UPDATE only when value differs), and per-handover-note (gate on literal-text-not-present). But each re-run does fire the cascade trigger for any negative-going status transition that's already true, writing a fresh `client_standing_history` row attributed to Gregory Bot with `cascade:status_to_<status>:by:<gregory-bot-uuid>`. Documented intentional in M5.6, but worth knowing if scanning history.
- **Why it matters:** if Scott's master sheet stops drifting (Path 2 outbound landed yesterday, so Gregory ↔ Make.com automation is closing the loop), this script becomes a periodic sanity check. If it stays drift-y because Scott still edits the master sheet manually, the script becomes a regular sweep tool. Either way: the audit trail builds up `cleanup:m5_master_sheet_reconcile` history rows over time.
- **Next action:** decide cadence after a few runs. Options: (a) ad-hoc when Scott sends a "match Gregory to my sheet please" Slack, (b) weekly cron (would need a Vercel function wrapper or Make.com trigger), (c) deprecate the script entirely once Path 2 + future Path 3-equivalent loops close all the holes. Lean: (a) until the next two cleanup-pass uses tell us whether (b) or (c) is right.
- **Logged:** 2026-05-04 (M5 master sheet reconcile first run).

## Path 2 outbound roster — outbound-pull audit log not implemented

- **What:** `api/accountability_roster.py` (Path 2 outbound, shipped 2026-05-04) does NOT write a `webhook_deliveries`-equivalent row per pull. The decision was deliberate at ship time: that table is for inbound deliveries; this is outbound; Make.com has scenario history on its side; V1 doesn't need a per-pull audit row. Logged here so the deferral is explicit.
- **Why it matters:** if duplicate-pull volume spikes (Make.com mis-configured to pull every minute, an upstream retry loop), or if Drake later wants to debug "did Make.com actually pull at 9am today and what did it get," there's no server-side record. Vercel function logs persist for ~7 days but aren't structured for this kind of query.
- **Next action:** if the gap surfaces (operational mystery about Make.com's pull cadence, or a need for "what was in yesterday's roster" forensics), add an `outbound_webhook_pulls` table — at minimum `(id, source, pulled_at, response_count, secret_match boolean)`. Mirror the `webhook_deliveries` lifecycle helpers in the receiver. Could share a table with inbound if a `direction` column is added; argument either way. ~30 lines added to the handler. Trigger: any operational ambiguity Drake can't resolve from Vercel function logs alone.
- **Logged:** 2026-05-04 (Path 2 outbound ship — explicit V1 carve-out per spec).

## Path 2 outbound — no rate limiting on Make.com pulls

- **What:** the accountability roster endpoint does not enforce any rate limit. Make.com is configured to pull "once per day" per Zain's existing scenario, but nothing on our side prevents a misconfigured scenario or a manual replay from hammering the endpoint. Each pull issues one DB query (single round trip with embedded join) so the cost is tiny — but tiny times misconfigured-fast can still saturate.
- **Why it matters:** at current volume (~100 actionable rows, single query, <1s response) a runaway pull at 1Hz would cost minutes of function-time per day; not a fire but not free. The bigger risk is a runaway pulling auth-failed (401s loop fast on Make.com if the secret rotates and they don't update). Vercel's per-function concurrency cap provides a soft ceiling.
- **Next action:** if a runaway surfaces (cost spike, function-time alerts, audit log shows >>24 pulls/day), add a per-IP or per-secret rate limit. Two options: (a) Vercel Edge Config for a moving-window counter, (b) `webhook_deliveries`-style log + a count check at request entry. Don't pre-build — wait for the symptom.
- **Logged:** 2026-05-04 (Path 2 outbound ship — non-blocker at current volume).

## Path 2 outbound — no pre-filter mode flag for "only enabled clients"

- **What:** the endpoint returns ALL actionable clients with the `accountability_enabled` and `nps_enabled` booleans in the payload; Make.com filters on its side. There's no `?only_enabled=true` query param that would have the server pre-filter rows where both booleans are false. The decision was deliberate — keeping the contract simple ("here is the roster, you decide what to do with it") and avoiding endpoint-shape proliferation.
- **Why it matters:** if Zain's Make.com scenario grows complex enough that filtering the JSON in his platform becomes a maintenance burden, the simplest server-side opt-in is a query param. Not urgent — Make.com filters JSON arrays trivially.
- **Next action:** if Zain asks for it, add a `?only_enabled=true` flag that filters the response to rows where `accountability_enabled OR nps_enabled` is true. Default behavior unchanged. ~5 lines in the handler.
- **Logged:** 2026-05-04 (Path 2 outbound ship — deferred per "every row is actionable" contract).

## Path 2 outbound — slack_channels staleness vs Slack-side archive state

- **What:** the endpoint trusts our `slack_channels.is_archived` column. We have no reconciler that updates that flag when a channel is archived on Slack's side. A channel archived in Slack but still `is_archived=false` in our table will surface a `slack_channel_id` Make.com then fails to post to (Slack API returns `channel_not_found` or similar).
- **Why it matters:** undetected drift = Make.com automation silently failing to deliver to specific clients, with the failure logged on Make.com's side rather than ours. Likely rare today (channels don't get archived often) but the gap is real.
- **Next action:** either (a) add a reconciler that periodically checks Slack `conversations.info` for each non-archived `slack_channels` row and flips `is_archived=true` on Slack-archived channels, OR (b) accept the drift and let Make.com surface "channel not found" failures back to Drake/Zain operationally. (b) is the V1 stance. Trigger to revisit: any reported case of accountability/NPS automation failing to deliver to a specific client.
- **Logged:** 2026-05-04 (Path 2 outbound ship — V1 carve-out, deferred).

## Client→Slack-identity coverage gap — 95 of 195 non-archived clients filtered from Path 2 roster

- **What:** Path 2's deploy-time numbers showed 100 actionable / 195 non-archived = 95 filtered server-side. Of those 95, the breakdown is some combination of: NULL `clients.slack_user_id`, no row in `slack_channels` matching the client, and (rarely) NULL `clients.email`. CLAUDE.md's prior per-message coverage note (`~94 of 2,914 messages from unknown authors`) is a different angle on the same underlying gap. The first time the gap got per-client visibility was the Path 2 deploy.
- **Why it matters:** these 95 clients can't be acted on by Make.com's accountability or NPS automation until their Slack identity resolves. If most are paused/leave/churned, the gap is mostly cosmetic; if meaningful chunks are active clients, Scott will notice missing rows on his daily check.
- **Next action:** triage SQL — count the 95 by `status`. If active count is meaningful, build a one-shot resolver: hit Slack `users.lookupByEmail` per unresolved `clients.email`, populate `slack_user_id` on hits. Bundle into the P1 cleanup pass for today's session if the active-count is non-trivial.
- **Logged:** 2026-05-04 (Path 2 outbound deploy — surfaced the per-client view of an existing gap).

## EditableField `<select>` missing id/name/htmlFor — a11y gap

- **What:** the `<select>` rendered by `components/client-detail/editable-field.tsx` (renderEditor's enum / three_state_bool branch, around lines 280-305 of the post-hotfix file) has no `id` or `name` attribute, and the `<Label>` rendered above it at line ~197 has no `htmlFor` linking the two. Same gap exists on the text/textarea/integer/numeric/date `<Input>` and `<Textarea>` variants. Surfaced during the M5.6 hotfix diagnosis when Drake noticed browser dev tools warning about un-labeled form fields; ruled out as a cause of Bug 1 (silent-click bug) but the a11y problem is real.
- **Why it matters:** screen readers can't announce field labels reliably. Browser autofill heuristics rely partly on `name`/`id` to recognize fields. Form validation tooling (and tests) that reference fields by name don't work. None of these are V1-blocking — the dashboard is internal-only with no screen-reader users today — but the gap will bite the moment Gregory ships beyond the agency.
- **Next action:** thread a stable per-instance id from the `EditableField` props down to the input element and to the `<Label htmlFor=...>`. Either (a) generate via `useId()` if React 18+ is in scope (it is — check `package.json`), or (b) take an `id` prop and have call sites pass slugged labels (e.g. `id="client-status"` for the Status field). Option (a) is more idiomatic and zero-config at call sites. Sweep all input variants in the same pass: `<select>` (line ~280), `<Input>` (line ~349), `<Textarea>` (line ~248). ~20-line refactor; no behavior change. Worth bundling with any other EditableField change.
- **Logged:** 2026-05-04 (M5.6 hotfix surface — diagnosis ruled out as cause of Bug 1 but the underlying a11y issue stands).

## M5.6 silent-toggle backfill — 17 clients flipped accountability/nps without history row

- **What:** the M5.6 migration 0022 backfilled `accountability_enabled` and `nps_enabled` to `false` on 82 negative-status clients. 65 of them got a `cascade:backfill:m5.6` row in `client_standing_history` (those whose `csm_standing` flipped from a non-`at_risk` value or NULL). The other 17 already had `csm_standing='at_risk'` from prior CSM judgment / master-sheet seed, so the backfill flipped the toggles without writing a history row — `csm_standing` didn't change, so the history insert (which is keyed on csm_standing transitions) had nothing to write. There is no `client_accountability_history` / `client_nps_enabled_history` table in V1 either, so the toggle change for these 17 is invisible in the audit trail.
- **Why it matters:** if a CSM later asks "why is accountability off for client X?" and X is one of the 17, the only signal is the migration commit message + this entry. Most queries against the audit trail (e.g. the cascade-attribution query in `docs/schema/client_standing_history.md`) won't surface them. Static snapshot of the 17 client IDs is preserved at `docs/data/m5_6_silent_toggle_backfill.md`.
- **Next action:** if Path 2 audit requirements OR a CSM workflow demands a per-toggle history table, build `client_accountability_history` and `client_nps_enabled_history` (mirror `client_status_history`'s shape: `id, client_id, value boolean, changed_at, changed_by, note`). Backfill from `webhook_deliveries` (post-Path-2 records) plus the 17-client snapshot above. Not urgent — V1 doesn't need toggle-level audit yet.
- **Recovery SQL — identify the silent-toggle 17 post-hoc.** This query mirrors the snapshot file's set as long as none of the 17 has had `csm_standing` cleared+re-set OR a CSM has manually flipped the toggles back on:
  ```sql
  select c.id, c.full_name, c.status, c.csm_standing,
         c.accountability_enabled, c.nps_enabled
  from clients c
  where c.archived_at is null
    and c.status in ('ghost','paused','leave','churned')
    and c.csm_standing = 'at_risk'
    and c.accountability_enabled = false
    and c.nps_enabled = false
    and not exists (
      select 1 from client_standing_history csh
      where csh.client_id = c.id
        and csh.note = 'cascade:backfill:m5.6'
    )
  order by c.status, c.full_name;
  ```
  Cross-check against `docs/data/m5_6_silent_toggle_backfill.md` — divergence means one of: (a) a client had csm_standing cleared and re-set (creating a real history row, removing them from this query's set), (b) a CSM has manually flipped a toggle back to true (the row no longer matches the toggle filter), or (c) a future cascade re-fire wrote a fresh history row. All three are expected lifecycle outcomes; the snapshot file is the immutable "as of M5.6 apply" reference.
- **Logged:** 2026-05-04 (M5.6 close-out — 17 silent toggles accepted per Drake's (a)+(d) call instead of building toggle-level history tables now).

## STATUS_DEFAULT_SELECTED duplicated across client/server boundary

- **What:** the M5.5 filter bar's default-status trio (`['active','paused','ghost']`) is hard-coded twice — once in `app/(authenticated)/clients/filter-bar.tsx` (Client Component, used to pre-check the Status dropdown when the URL param is absent) and once in `app/(authenticated)/clients/page.tsx` (Server Component, used by `readFilters` to inject the same default into the DB query). Both copies are identical; neither imports from the other because the `'use client'` boundary made a shared module path awkward at M5.5 ship time.
- **Why it matters:** if the default trio ever changes (e.g. Scott decides Ghost shouldn't be on by default, or Leave should be), two files need editing. Drift between them produces a silent UX bug — the dropdown UI shows one default while the server query applies a different one, and a fresh page load looks like the filter is "checked but ignored."
- **Next action:** extract to a third file like `lib/clients-filter-defaults.ts` (or fold into `lib/client-vocab.ts` since it's adjacent to the status vocab). Both call sites import the constant. ~5-line refactor, zero behavior change. Worth doing alongside any future filter-default tweak; not urgent on its own.
- **Logged:** 2026-05-03 (M5.5 close-out — intentional defer at ship time).

## NPS backfill 404s — Jonathan Duran-Rojas + Luis Malo email mismatches

- **What:** M5.4 backfill surfaced 2 of 61 clients where Airtable's NPS Clients email doesn't match Gregory's `clients.email` or `metadata.alternate_emails`. Jonathan Duran-Rojas: Airtable has `wetasspressurewasher04@gmail.com`; Gregory has two rows (`Jonathan Duran` / `j05832952@gmail.com` and `Jonathan Duran-Rojas` / `jonathan@luxrevo.com`), neither in alternates. Luis Malo: Airtable has `lmalo721@yahoo.com`; needs the same lookup. Both visible in `webhook_deliveries.processing_error` from the M5.4 backfill run.
- **Why it matters:** these clients' nps_standing stays NULL in Gregory until reconciled. Scott's Monday onboarding will see `—` placeholders for them in Section 2.
- **Next action:** triage flow per `docs/runbooks/backfill_nps_from_airtable.md` § "Failure modes" — figure out the canonical Gregory row for each, add the Airtable email to `clients.metadata.alternate_emails` (via merge_clients RPC if there's a duplicate to clean up, else direct edit), re-run `scripts/backfill_nps_from_airtable.py --apply` to land their nps_standing. Drake handling over the weekend cleanup queue.
- **Logged:** 2026-05-03 (M5.4 backfill — `wetasspressurewasher04@gmail.com` and `lmalo721@yahoo.com`).

## NPS backfill — 4 manual-override-sticky divergences worth Scott discussion

- **What:** the M5.4 backfill's `auto_derive_applied=False` cases were the 4 clients where Scott's existing manual `csm_standing` differs from the segment-mapping. All four: Scott's read is **harsher** than NPS. Tina Hussain (NPS Neutral → mapping content; Scott set at_risk). Jenny Burnett (NPS Neutral → content; Scott at_risk). Mary Kissiedu (NPS Neutral → content; Scott at_risk). Saavan Patel (NPS At Risk → at_risk; Scott problem — one step worse).
- **Why it matters:** signal that NPS is over-optimistic for these clients vs CSM judgment with full context. Useful framing for Scott's Monday onboarding — these are exactly the "manual judgment trumps NPS" cases the override-sticky logic was designed for. The receiver correctly skipped auto-derive on all 4.
- **Next action:** surface the list at Monday's onboarding as discussion items. No code action — the data is correct; this is product/CSM workflow context. If Scott wants a "divergence dashboard" view in the future, it's a small `WHERE csm_standing != <derived from nps_standing>` query against `clients`.
- **Logged:** 2026-05-03 (M5.4 backfill).

## Master-sheet-import seed treatment for auto-derive eligibility — architectural question pending Monday

- **What:** the 137 clients with `csm_standing` set by the M4 Chunk C master sheet importer all carry `changed_by=NULL` on their `client_standing_history` rows (note `'import seed'`). Per the override-sticky rule (`changed_by != Gregory Bot UUID` → skip), these clients are **ineligible for auto-derive forever** unless the rule changes. Concrete impact from M5.4 backfill: only 2 of 59 successful sends actually wrote `csm_standing` via Gregory Bot; the other 57 sticky-skipped because their existing csm_standing came from the importer.
- **Why it matters:** if Scott wants NPS segments to drive `csm_standing` updates going forward (which is what M5.4 was set up for), the master-sheet seed effectively locks the column. Two paths: (a) treat master-sheet-seed as auto-derive-eligible (one-time NULL → Gregory Bot retroactive update on existing history rows, OR change the rule to "changed_by IS NULL OR Gregory Bot"); (b) accept that Scott's master-sheet seeds win and any future auto-derive only fires on net-new clients or clients Scott explicitly clears to NULL. The override-sticky design as built assumes (b); Drake-Scott Monday conversation may flip to (a).
- **Next action:** Monday onboarding decision. If (a): write a one-shot script to update existing master-sheet-seed history rows' `changed_by` to Gregory Bot UUID, OR amend the function logic. If (b): document explicitly in `gregory.md` that master-sheet-seeds are sticky by design.
- **Logged:** 2026-05-03 (M5.4 backfill — exposed the structural implication).

## Airtable NPS Clients name whitespace hygiene

- **What:** multiple rows in Airtable's NPS Clients table have leading/trailing/double whitespace in the Name field — e.g. `' Javier Pena'`, `' Vid'`, `' Marcus Miller'`, `'Edward  Molina'`, `'Jerry Thomas '`. Spotted during the M5.4 backfill dry-run; the script logs them with the exact whitespace preserved.
- **Why it matters:** doesn't affect email-based matching (the receiver's RPC lookup uses `clients.email`, not `clients.full_name`) and doesn't affect Gregory data quality directly. But the Airtable side is messier than ideal — name-based lookups, future Airtable formulas that cross-reference Names, and any human reading the table get noise.
- **Next action:** Airtable-side hygiene pass — Drake or Zain trims whitespace on the affected rows. Or: an Airtable automation that runs `TRIM()` on Name field changes. Low-priority operational hygiene.
- **Logged:** 2026-05-03 (M5.4 backfill dry-run output).

## Receiver-broken-diagnosis — two-step pattern for "is the function actually live?"

- **What:** when a Vercel serverless function appears broken (HTML response on GET instead of friendly JSON, 404 on POST, etc.), there's a two-step diagnostic that catches >90% of cases before deeper investigation: **(1)** `git log origin/main..HEAD` to confirm no unpushed local commits — Code's commits land in local-only state until pushed, and a deploy can't include code that isn't on origin yet. **(2)** Vercel deployment Functions tab — confirm the function actually appears in the build. If absent, either `vercel.json`'s `functions` block is missing the entry, or the file path doesn't match what Vercel expects.
- **Why it matters:** the receiver-shipped-but-broken failure mode tends to look like real code bugs but is usually a deploy/sync gap. Both steps take <30 seconds; either alone catches most cases.
- **Next action:** no code action. Worth referencing in any future "the receiver isn't responding" diagnostic flow — either a runbook addition or a CLAUDE.md operational note.
- **Logged:** 2026-05-03 (M5.4 — captured during deploy verify operations).

## Vercel `auto_derive_applied` response field is best-effort inference — pre-state SELECT could give true precision

- **What:** `api/airtable_nps_webhook.py` returns `auto_derive_applied` by comparing post-RPC `csm_standing` to the segment-mapping. Documented false positive: when a CSM manually set `csm_standing='happy'` (sticky override) and a 'promoter' segment arrives, the RPC skips the auto-derive but the values still match → response says `auto_derive_applied=true`. Verified concretely in the M5.4 backfill: 53 of 59 successes had this false positive (only 2 actual auto-derive writes). The simple comparison was an explicit V1 design choice (accepted by Drake during the receiver chunk).
- **Why it matters:** the response body misleads anyone who reads `auto_derive_applied` as "the auto-derive ran." The source of truth is `client_standing_history.changed_by`. Documented in code comments, gregory.md, and the receiver's response-shape table — but if Make.com or future operators rely on the flag for their own logic, it'll bite.
- **Next action:** if false positives become operationally annoying (someone reads the report wrong, or Make.com tries to route on the flag): add a pre-state `SELECT csm_standing FROM clients WHERE id = ?` before the RPC call, then compute `auto_derive_applied = (pre != post) OR (pre IS NULL)`. One extra round trip, true precision. ~10 lines in the receiver. Defer until needed.
- **Logged:** 2026-05-03 (M5.4 receiver — V1 accepted-imprecision flagged for V2 if it bites).

## `lib/supabase/types.ts` manually edited for `nps_standing` — next CLI regen will overwrite cleanly

- **What:** The Supabase types regen path is broken in this environment (CLI misroutes per the standing followup; Studio UI's gen-types feature was moved/removed in newer dashboard versions). For the M5.4 NPS Standing UI work to compile, `lib/supabase/types.ts` was hand-edited to add `nps_standing: string | null` to the clients `Row`, `Insert`, and `Update` types — plus the three RPC `Returns` blocks that mirror the clients shape (`update_client_status_with_history`, `update_client_journey_stage_with_history`, `update_client_csm_standing_with_history`). 6 insertions total, all between `notes` and `occupation` (alphabetical). The new `update_client_from_nps_segment` RPC from migration 0021 is NOT in the types file at all — fine for now since no TS code calls it (only the Python receiver does).
- **Why it matters:** the file was wiped during a regen attempt and recovered via `git checkout HEAD -- lib/supabase/types.ts` before the manual additions. Any further new columns or RPCs added before a working regen path is restored will need the same hand-edit treatment, and the file will gradually drift from cloud reality. CHECK constraints on `clients.status` (M5.3 added `'leave'`) and `clients.trustpilot_status` (M5.3b renamed) didn't need any types-file changes because Postgres CHECK constraints don't lift to TS literal unions in supabase-cli's regen output anyway — those values stay as plain `string`.
- **Next action:** when a working regen path becomes available again (CLI fix, Studio UI restoration, or a new tool), run regen and let it overwrite the manual edits cleanly. Schedule a follow-up regen review at that point — verify the regen produced the same 6 `nps_standing` lines, plus picked up the missing `update_client_from_nps_segment` RPC type, plus anything else added between now and then. Standing assumption until regen path is restored: every new schema chunk requires a corresponding hand-edit to types.ts in the same commit.
- **Logged:** 2026-05-03 (M5.4 follow-up — relocation chunk surfaced the gap and accepted the manual-edit bridge).

## Airtable NPS receiver — no idempotency layer; Make.com retries create duplicate writes

- **What:** `api/airtable_nps_webhook.py` ships in V1 without idempotency. Every request gets a unique `webhook_deliveries.webhook_id = "airtable_nps_<uuid4>"`, so duplicate Make.com fires create duplicate audit rows. Worse: if the receiver returns 5xx after the RPC committed (rare race — RPC succeeded, network error before response), Make.com's default retry-on-5xx fires the same webhook again. The 0018 RPC's idempotency on `csm_standing` (no-op when value unchanged → no extra history row) covers most of the damage, but `nps_standing` gets re-written (idempotent value-write, harmless) and a second `webhook_deliveries` row lands.
- **Why it matters:** harmless today (`webhook_deliveries` is just an audit log; csm_standing dedup means no extra history rows on the common path). But once we start querying `webhook_deliveries` for analytics ("how many NPS updates per week?") the duplicate-write inflation matters. Also, if the RPC ever stops being idempotent on csm_standing (e.g. someone adds a side effect), we'd silently get duplicate auto-derived writes.
- **Next action:** add `airtable_record_id`-based deduplication. Two paths: (a) move `airtable_record_id` from `call_external_id` to a dedicated unique partial index, then `INSERT ... ON CONFLICT (airtable_record_id) WHERE source = 'airtable_nps_webhook' DO NOTHING RETURNING ...` and short-circuit on conflict (like the Fathom handler's `webhook-id` dedup); (b) add a small RPC `record_nps_segment_with_dedup(client_email, segment, airtable_record_id)` that wraps `update_client_from_nps_segment` with a "SELECT 1 FROM webhook_deliveries WHERE call_external_id = ? AND source = ?" guard. Path (a) is cleaner. Defer until duplicate-write counts become visible in queries OR until a real retry incident surfaces.
- **Logged:** 2026-05-02 (M5.4 receiver — known V1 gap, surfaced at draft time per Drake's "no idempotency layer in V1" decision).

## `docs/runbooks/apply_migrations.md` is stale around the Studio + ledger workflow

- **What:** The runbook is written entirely around the Supabase CLI workflow (`supabase init`, `supabase start`, `supabase db push`, `supabase migration up`) plus a "First Apply Log" section anchored in the v1-schema-only era. None of it mentions Studio + manual ledger registration + dual-verification, which has been the canonical migration path since the M2.3a CLI misroute incident (where 0012 / 0013 went to local instead of cloud and were recovered via Studio). Every migration since (0014–0019) has shipped via Studio + manual ledger; new sessions reading the runbook for "how do I apply this migration" get the wrong picture.
- **Why it matters:** CLAUDE.md and `docs/claude-handoff.md` both reference Studio + ledger as the operational norm but the runbook itself is the doc Code is most likely to consult first for migration mechanics. The verification queries in § "Verify After Apply" are also scoped to the v1 schema (16 tables, migrations 0001–0007) — fine as historical reference but they don't mirror today's per-migration dual-verify pattern (schema reality + ledger registration, run together against cloud explicitly).
- **Next action:** ~30-min refresh pass. Add a "Cloud apply via Studio" section as the canonical path. Move the `supabase db push` content under a "Local apply" or "(deferred — CLI broken in our environment)" heading. Replace the v1-only verification queries with a generic dual-verify template that ages well (one schema-reality query + one ledger query), shown with a worked example. Tag the "First Apply Log" entry as historical context.
- **Logged:** 2026-05-01 (M5.3 — surfaced while drafting `0019_status_add_leave.sql`; runbook still describes CLI-only path while every migration since 0012 has shipped via Studio + manual ledger).

## Notes attribution / history on `clients.notes` — single-author free-text in V1

- **What:** Section 7 of the client detail page uses a single `clients.notes` text column for V1 — single open free-form text field, no per-author attribution, no history. Drake collapsed the originally-specced four-author-split (Scott / Nabeel / Owner / General) and the alternate per-entry-with-attribution model in favor of simplicity.
- **Why it matters:** low-stakes for V1 with the team-of-six editing pattern, but "who wrote this and when" surfaces as a real need once the dashboard sees broader CSM use. Likely 3-session timeframe before this becomes pressing.
- **Next action:** when usage demands it, either (a) introduce a `client_notes` table with `(id, client_id, body, author_id, created_at)` rendered as an attributed feed in Section 7, or (b) extend `clients.notes` to jsonb with structured entries. Sub-table is cleaner long-term and matches the history-table pattern from 0017.
- **Logged:** 2026-05-01 (M4 EOD — design call captured for the M4 client-page schema scope).

## `alerts` vs. `client_health_scores.factors.concerns[]` — two-table redundancy

- **What:** the original V1 schema designed `alerts` as the table for actionable CSM-facing signals (churn risk, upsell, etc.). The M3 concerns generation work landed inside `client_health_scores.factors.concerns[]` jsonb instead — concerns are tied to the health score computation, the dashboard reads them from the same row, and one jsonb write was simpler than coordinating two-table writes. Functionally these overlap: concerns ARE alerts.
- **Why it matters:** low-stakes today (`alerts` is empty; concerns are the only live signal source), but the fork becomes a real annoyance when CSM Co-Pilot needs a single read source for "things CSMs should care about." Two write paths, two read paths, two staleness questions.
- **Next action:** resolve when CSM Co-Pilot writes to the unified surface. Two paths: (a) promote concerns out of jsonb into rows on `alerts` (or a renamed `client_concerns` table) with a back-reference to the originating health-score run, or (b) retire `alerts` and let `client_health_scores.factors` be the single source. Defer until CSM Co-Pilot needs the unified surface.
- **Logged:** 2026-05-01 (M4 EOD — known design seam captured before CSM Co-Pilot work starts).

## Master sheet importer — three carry-overs from M4 Chunk C apply

These three are byproducts of Drake's M4 Chunk C triage decisions on the master sheet importer. None blocks the dashboard's daily use; all want a manual touch when there's spare capacity.

- **(a) 21 auto-created non-churn clients need cross-check against existing-cloud-data-in-other-forms.** The first dry-run surfaced 21 paused/active rows in the master sheet that had no match in cloud (verified 0/20 sampled emails found anywhere — primary, alternate, or by name). Drake amended the spec's auto-create rule to cover non-churn unmatched rows too (was: churn only). All 21 land as new clients with sheet-side data and primary CSM assignments. **Risk:** any of them might already be in cloud under a different identity (e.g. a personal-email variant that's stored under a work-email primary, or a slightly-spelled-different name). When time permits, walk the 21 names and check for existing duplicates that should be merged. List captured in `data/master_sheet/import_report_*.txt` after apply.
- **(b) 4 Aleks-orphaned clients need primary_csm reassigned.** Aleks is no longer at the company per Drake. The importer sees `Aleks` in the Owner (KHO!) column on 4 rows (Colin Hill — churn auto-create; Ming-Shih Wang, Jose Trejo, Alex Crosby — non-churn auto-creates after Drake's amendment) and skips the assignment per spec. These 4 clients will land in cloud with `primary_csm = NULL`. Drake handles reassignment manually via the dashboard's Primary CSM dropdown.
- **(c) Some auto-creates have placeholder emails.** Rows in the master sheet without an email value get `<slug>+import@placeholder.invalid` synthesized so the migration 0001 NOT NULL email constraint holds. From the first dry-run: 6 churned (Jarrett Fortune, Chris Ferrente, Robert Haskell, Lenrico Williams, Charles Biller, roula deraz) plus Andy V (paused, post-amendment). If real emails surface later for any of them, edit via the dashboard's Email field — `placeholder.invalid` TLD is RFC-reserved so no risk of accidentally emailing the address.
- **Why deferred:** Drake's call: getting these 21 + 4 + 7 visible in the dashboard NOW (so the CSM team can onboard against real data tomorrow) outweighs the cleanup tax. Manual review + reassignment is a ~30 min batch when convenient.
- **Logged:** 2026-05-01 (M4 Chunk C apply triage).

## Auth context not threaded through Server Actions — `changed_by` is always null in B2 history rows

- **What:** the four history-writing flows shipped in M4 Chunk B2 (status, journey_stage, csm_standing, nps_submissions.recorded_by) all accept a `p_changed_by` / `p_recorded_by` argument but the dashboard Server Actions pass null. The Supabase auth user is available via `@supabase/ssr` cookies, but there's no `auth.users.id → team_members.id` resolution layer yet, and Server Actions don't currently read the auth cookie. Every history row in B2 records `changed_by = null`.
- **Why it matters:** the audit trail tells you what changed and when, but not who. Acceptable for a single-CSM V1 (Drake is the only editor today). Becomes a problem the moment Lou / Nico / Scott / others edit alongside each other in the dashboard — the timeline goes anonymous.
- **Next action:** wire a small helper (`getCurrentTeamMemberId()` or similar) that reads the Supabase auth cookie in a Server Action context, looks up `team_members` by email, and threads the resolved id through the existing nullable `p_changed_by` argument. Exists as a hook in `app/(authenticated)/clients/[id]/actions.ts` — replace the literal `null` passed today. ~30 min plus testing.
- **Logged:** 2026-05-01 (M4 Chunk B2 — wired the RPCs, didn't wire auth).

## metadata.profile read-modify-write race — concurrent edits clobber each other

- **What:** Section 5 (Profile & Background) writes go through `updateClientProfileFieldAction` → `updateClientProfileField` (lib/db/clients.ts), which performs a read-modify-write on `clients.metadata`: SELECT current metadata, build a new object with the updated `metadata.profile.<path>`, UPDATE the row. If two CSMs save different `metadata.profile.*` fields concurrently, the later UPDATE wins and clobbers the earlier write. Top-level `metadata.alternate_emails` / `alternate_names` / etc. are preserved by spreading the existing object (so the merge_clients RPC's writes won't be clobbered — that flow modifies different keys), but two concurrent profile edits collide.
- **Why it matters:** fine for V1 (single-CSM-at-a-time editing pattern). Becomes a real issue once concurrent CSM editing is normal — you save the niche, your colleague saves the offer, your save wins, their offer disappears.
- **Next action:** when concurrent editing becomes real, migrate `updateClientProfileField` to a Postgres function using `jsonb_set` so the read-modify-write happens server-side under a row lock. Or add an `xmin`-based optimistic-concurrency check at the application layer. ~1 hour plus testing. No urgency in V1.
- **Logged:** 2026-05-01 (M4 Chunk B2 — design call: simpler-now, debt-later).

## NPS-entry has no duplicate-submission protection

- **What:** the Section 2 "Add NPS score" form invokes `insert_nps_submission` which always inserts a fresh row. A CSM who clicks Save twice (network blip, double-tap, browser back-then-forward) creates two `nps_submissions` rows for the same client at near-identical timestamps. (Note: post-M5.4 the dashboard no longer surfaces a "Latest NPS" field — `nps_submissions.score` is invisible in V1; the duplicate sits in the table without a UI consumer. `latest_nps` stays in the data layer for V1.5 score-piping.) Total count of `nps_submissions` becomes inflated.
- **Why it matters:** low-stakes for V1 — duplicate NPS rows are easy to spot in the table and easy to delete via Studio. But "the duplicate count drifts the more clients you have" is a slow-growing data-hygiene tax.
- **Next action:** options when usage scales: (a) optimistic UI lock — disable the Save button between submit and revalidation; (b) server-side dedup — reject inserts where a row exists for `(client_id, score)` within the last 30 seconds; (c) a uniqueness check by (client_id, submitted_at::date) when manual entries dominate. (a) is the cheapest and probably enough.
- **Logged:** 2026-05-01 (M4 Chunk B2 — known design gap, deferred).

## Fathom realtime webhook silent for 7+ days; cron-only ingest in cloud — RESOLVED 2026-04-30 via M4.1

- **Resolution:** M4.1 re-registered the webhook fresh via `POST /external/v1/webhooks` against `https://ai-enablement-sigma.vercel.app/api/fathom_events`, captured a new id (`FTVBjD_JqTfjEzVA`) and new `whsec_` secret, rotated the secret into Vercel `FATHOM_WEBHOOK_SECRET` (Production scope), redeployed, and verified the handler reads the new secret via the bad-signature → 401 probe. End-to-end smoke test (real Fathom recording) is the remaining hand-off step before declaring full restoration.
- **Root cause:** the F2.5 (2026-04-24) UI-based registration was silent from the moment it was created. `webhook_deliveries.source='fathom_webhook'` count over **all time** was zero (not just the 7-day window the original entry framed it as), and Vercel function logs showed zero inbound POSTs to `/api/fathom_events` over the same window. No 401 traffic either, ruling out signature mismatch — Fathom simply wasn't sending. Either the F2.5 UI registration silently failed to register, or Fathom's side dropped it shortly after. The runbook's diagnostic guidance was also wrong — the documented `GET /external/v1/webhooks` endpoint **does not exist** at Fathom (OpenAPI confirms only `POST /webhooks` and `DELETE /webhooks/{id}`); fixed in `docs/runbooks/fathom_webhook.md` § "Resume from F2.5 pause" in the same session.
- **Cleanup gap (intentional):** no `GET /webhooks` API means we couldn't verify whether the F2.5 subscription was still alive at Fathom's side, and we don't have its id to `DELETE`. Re-registered without cleanup. If the F2.5 subscription is still alive, its deliveries now 401 silently at our handler (signature verify fails before any DB write) — harmless but invisible. Acceptable; no action.
- **Logged:** session M3 close-out (2026-04-29); **resolved:** 2026-04-30 (M4.1 diagnose + re-register + redeploy + handler-probe verify).

## Repo cleanup pass — broader sweep beyond `scripts/`

- **What:** the `scripts/` archive cleanup landed mid-M3 (`scripts/archive/` + 3 historical scripts moved + doc references updated). Other parts of the repo likely have similar one-shot or stale artifacts that visually compete with active tooling: candidate areas to sweep include `data/` (one-shot ingestion logs and intermediate files from Fathom backlog runs), `supabase/seed/` (verify each seed file is still in use), `tests/` (any test files for archived scripts or removed features), root-level files (any orphaned config or scratch files). Scope is "make the repo less visually cluttered for human eyes" — not refactoring or deleting working code.
- **Why deferred:** `scripts/` was the highest-friction area and got handled. Broader cleanup is nice-to-have, not blocking. The repo is still navigable.
- **Revisit trigger:** (a) onboarding a new contributor (Zain or future hire) and noticing repo orientation is harder than it should be, (b) Drake catches himself looking past the same stale file for the third time, (c) any future session has spare capacity and Drake wants to ship a small win.
- **Logged:** session M3 close-out.

## Aman sales-call classification — needed before CSM Co-Pilot V1

- **Status update (2026-04-28):** superseded by the "Aman automated classifier — deferred" entry below. The decision landed on manual reclassification via the Gregory dashboard (M2.5) rather than an automated classifier change for V1. The original "next action" below is no longer the live plan — kept for history.
- **What:** Aman's sales/prospect calls don't have a clean classifier category in `ingestion/fathom/classifier.py`. Today they likely land as `external` (non-team-domain participant + no client match → external) which means **no transcript chunks land in the KB** (`_INDEXABLE_CATEGORIES = {"client"}`). The `_apply_aman_sales_override` function in classifier.py already detects "Aman + no CSM → call_type='sales'" and bumps confidence, but the category stays `external` so chunks aren't indexed. As-is: Aman's prospect call content is invisible to retrieval.
- **Why it matters:** for CSM Co-Pilot V1 (next priority after this), if sales-call content surfaces unfiltered to CSMs, the agent reasons over content that isn't its scope. Conversely, if sales calls have legitimate CSM-relevant content (handoff context, client backstory), losing them entirely from retrieval is also wrong. Need a deliberate decision before Co-Pilot ships.
- **Next action:** discovery + design first — three options to weigh: (a) keep as `external`, document the omission, accept the tradeoff; (b) add a new `sales` category to the classifier and route sales-call content to a dedicated index/scope; (c) tag Aman-recorded `external` rows and filter at retrieval time. (b) is the cleanest schema-wise but biggest change — adds a 5th `call_category` enum value, possibly extends `_INDEXABLE_CATEGORIES`, may need migration. (c) is lightest but stretches `external` semantics. Backfill Aman's existing calls after the decision: `select count(*) from calls where call_category='external' and primary_client_id is null and id in (select call_id from call_participants where email='aman@theaipartner.io')`. Full reasoning in CLAUDE.md § Next Session Priorities #1.
- **Logged:** 2026-04-27 (M1 close-out — surfaced by Drake as a CSM Co-Pilot V1 prerequisite).

## Ella user-token posting (M1.4) — DEPLOYED, awaiting Nabeel feedback before pilot rollout

- **What:** M1.4.1 (discovery) → M1.4.2 (operational setup) → M1.4.3 (code change + 14 tests) all shipped 2026-04-27 in commits up to `751cb38`. `api/slack_events.py:_post_to_slack` now uses a two-token strategy: try `SLACK_USER_TOKEN` (xoxp-, posts as @ella user, no APP tag); fall back to `SLACK_BOT_TOKEN` (xoxb-, with APP tag) on any failure. Smoke-tested in `#ella-test-drakeonly` — replies render with no APP tag. Operational rollback (unset `SLACK_USER_TOKEN` + redeploy) takes ~30 sec, no code change. Pinned by `test_no_user_token_uses_bot_directly`.
- **Known constraint surfaced post-deploy:** the *@-mention to invoke Ella* still targets the bot, because Slack's `app_mention` event subscription is bound to the bot user — that's a Slack architectural constraint, not a code choice. The reply renders cleanly as the user; the mention does not. Whether this addresses Nabeel's "looks unprofessional" feedback is open — pending his read.
- **Why it matters:** if Nabeel says current state addresses the ask → invite @ella user to the 6 remaining pilot channels (M1.4.5) and ship. If not → workaround design needed (e.g., custom mention pattern, slash command, accept-and-document the constraint).
- **Next action:** Nabeel feedback first. Then either M1.4.5 pilot rollout (~30 min: invite @ella to each of Fernando G / Musa / Jenny / Dhamen / Trevor / Art channels via the channel UI) OR M1.4.6 design session for the mention constraint. Step-by-step in `docs/architecture/ella_user_token.md` § Deploy + smoke-test runbook.
- **Logged:** 2026-04-27 (M1.4.1 → M1.4.3 implementation + deploy in one day; pilot rollout gated on Nabeel).

## Slack AI/impersonation policy — Drake elected NOT to add "(AI)" suffix; revisit on signal

- **What:** Slack's App Developer Policy prohibits "impersonation of Users or otherwise allow[ing] for false representations within the Application." M1.4.1 read this clause carefully. The intended scope is impersonating a human user without consent — not a dedicated automation account. Many workspaces have non-human user accounts (Zapier, n8n, internal scripts) without policy issues. M1.4.1 *recommended* including "(AI)" in Ella's display name as a cheap defense. **Drake elected not to** — Ella ships as just `Ella` / `@ella` (no AI suffix in the visible display name).
- **Why it matters:** the recommended disclosure was belt-and-suspenders, not strictly required. Drake's call is informed: clients were already announced "Ella, an AI assistant" in the rollout, so the persona is positioned as AI even without the display-name suffix. If Slack ever flags the account, OR if a client expresses confusion about whether Ella is human, the disclosure can be added in seconds via Slack profile settings — no code or token change.
- **Revisit triggers:** (a) Slack support contacts the workspace about the account, (b) a pilot client asks "is Ella a person?" in a way that suggests genuine confusion (vs casual curiosity), (c) any external Slack policy update that tightens the AI-account requirements. Until then: status quo.
- **Logged:** 2026-04-27 (M1.4.1 discovery + post-M1.4.2 Drake decision to skip the suffix).

## Cron sweep race condition — concurrent manual triggers can hit unique-key collision

- **What:** M1.2.5 (2026-04-27) saw two manual `curl` triggers fire ~1 minute apart while debugging the auth-rename + X-Api-Key issues. Both sweeps ran concurrently against the same Fathom window. The cron's per-meeting `_call_already_in_db` check returned False on a few overlapping external_ids because the FIRST sweep hadn't yet INSERTed those rows when the SECOND sweep checked. Result: 2 of 31 cron rows landed `processing_status='failed'` with `duplicate key value violates unique constraint "calls_source_external_id_key"` — both calls actually present in DB from the winning sweep, but the losing sweep's row in `webhook_deliveries` is a noise artifact.
- **Why it matters:** with daily Vercel Cron cadence, the 1-second window between `_call_already_in_db` and `INSERT INTO calls` is unreachable in normal operation — there's only one cron sweep per day. The race only surfaces during human-driven debugging where two manual triggers overlap. Not data loss, not blocking. Just visible-in-the-logs noise that looks like a real failure on shallow inspection.
- **Next action:** if we ever move off daily cron cadence (hourly, or sub-hour) — OR if a future operator adopts a "trigger before reading status" pattern that overlaps two sweeps — tighten dedup by moving `_call_already_in_db` + `INSERT` into a single transaction with `ON CONFLICT (source, external_id) DO NOTHING RETURNING id` (same pattern as the webhook handler's `webhook_deliveries` dedup). ~10 lines in `_upsert_call_row`. Defer until needed.
- **Logged:** 2026-04-27 (M1.2.5 — flagged but not fixed).

## Fathom payload — minor non-load-bearing fields the adapter drops today

- **What:** M1.2.5 audit (2026-04-27) walked `record_from_webhook` field-by-field against a real cloud-stored payload. Found the `markdown_formatted` summary bug (resolved) AND four minor fields the adapter consumes from but doesn't surface: `meeting_title` (redundant alias of `title`, same length on the audited sample), `created_at` (Fathom-side ingest timestamp, distinct from `started_at`/recording start), `calendar_invitees_domains_type` (`only_internal`/`one_or_more_external` — pre-computed classifier signal we re-derive ourselves in `ingestion/fathom/classifier.py`), `recorded_by.team` and `action_items[].assignee.team` (e.g. "Customer Success", "Sales" — would enrich attribution).
- **Why it matters:** none are load-bearing for V1. Each is a small enrichment opportunity: `created_at` for ingest-vs-record-time analytics, `calendar_invitees_domains_type` to shortcut classifier when Fathom and our classifier agree, `recorded_by.team` / `assignee.team` for clearer attribution in summaries / action item ownership UIs. Not blocking anything.
- **Next action:** revisit when (a) we want CSM-Co-Pilot-grade attribution (the `team` fields would help), (b) classifier latency or accuracy ever becomes an issue (the pre-computed `calendar_invitees_domains_type` could shortcut), or (c) raw_payload-only retention isn't enough for some future use case (e.g., audit query that wants `created_at` indexed). Until then: full payload is preserved in `webhook_deliveries.payload` and `calls.raw_payload.raw_text`, so re-deriving any of these later is trivial — no data loss.
- **Logged:** 2026-04-27 (M1.2.5 audit).

## API integration discovery — verify auth scheme empirically before declaring done

- **What:** F2.1's discovery session (Fathom webhook intel) thoroughly read the OpenAPI spec, payload schemas, signature verification, retry semantics — but missed that Fathom's external API uses `X-Api-Key: <key>` for outbound auth, NOT `Authorization: Bearer <key>`. F2.1 produced an architecture doc and 8 commits' worth of code on the assumption of Bearer auth; M1.2's `api/fathom_backfill.py:_fetch_meetings_window` shipped with `Authorization: Bearer ${api_key}` and 401'd against Fathom on first real run. M1.2.5 caught it via Drake's manual-curl probe (`curl -H "X-Api-Key: ..." https://api.fathom.ai/external/v1/meetings` → 200). One-line code fix; the lost time was the deploy → 401 → diagnose loop.
- **Why it matters:** every future external-API integration (CRM, Calendar, n8n webhook receivers, future agent integrations) has the same risk — read the spec carefully, miss one detail, ship code that 401s on first real call. The OpenAPI / docs are the *intended* shape but providers don't always document the actual deployed auth scheme accurately, especially when the spec says `securitySchemes: bearerAuth` but the provider's implementation accepts something else.
- **Next action:** before declaring any API discovery session "done," **run one real curl against the production API endpoint with the documented auth scheme.** A 200 confirms the auth shape; a 401 surfaces the gap before code ships. Add this as a step to a future `docs/runbooks/api_integration_discovery.md` runbook (analog to `adding_new_ingestion_source.md`) — written when the second integration starts (CSM Co-Pilot V2 may add CRM API integration; that's the trigger).
- **Logged:** 2026-04-27 (M1.2.5 deploy caught the F2.1 gap).

## Fathom webhook registration UI viewport bug — workaround needed every time

- **What:** Fathom's webhook registration UI (Settings → API Access → Add Webhook) has a viewport rendering bug where the verify/save button renders below the fold without a scrollbar. On a default browser zoom + standard laptop display, you can fill the form but not submit it. M1.1 lost ~3 days to this — registration appeared complete but Fathom never sent deliveries because the registration object hadn't been finalized server-side. **Workaround:** zoom browser out (Cmd-/Ctrl-`-`) until the verify button is visible, then submit.
- **Why it matters:** any future webhook re-registration (secret rotation, URL change, scope change) will hit this same bug. The runbook in `docs/runbooks/fathom_webhook.md` § Rotate Secret depends on the UI working — if Drake's already zoomed out it's a non-issue, but a future operator following the runbook cold could lose another few days.
- **Next action:** add a one-line note to `docs/runbooks/fathom_webhook.md` § Register that says "zoom out before submitting if the verify button isn't visible." Also, the cleanest long-term fix is to skip the UI entirely — Fathom's `POST /webhooks` API endpoint works fine (per F2.1 doc read). For the next rotation, register via API instead of UI.
- **Logged:** 2026-04-27 (M1.1 root cause).

## Fathom API key + cron backfill auth token — need rotation runbook

- **What:** M1.2 added two new env vars: `FATHOM_API_KEY` (Fathom team-account API key, used by `api/fathom_backfill.py` to read `/meetings`) and `FATHOM_BACKFILL_AUTH_TOKEN` (random secret, used by Vercel Cron's `Authorization: Bearer ...` header). Neither has a documented rotation procedure today. The Fathom API key has the same constraint as the webhook secret — Fathom's API doesn't expose a rotate endpoint, only delete + recreate.
- **Why it matters:** if either is leaked or a team member with access leaves, we need a known-good rotation path. Doing it under pressure without a runbook is error-prone (cron downtime window, missed env-var update on Vercel).
- **Next action:** when adding the secret-rotation section to `docs/runbooks/fathom_webhook.md` (already an open followup for the webhook secret), extend it to cover both new secrets. ~30 min to draft. Not urgent — defer until first rotation is needed.
- **Logged:** 2026-04-27 (M1.2 build).

## F2.5 first-real-delivery verification — RESOLVED 2026-04-27 via M1.2.5

- **Resolution:** M1.2.5 cron sweep ingested 29 real Fathom calls end-to-end on 2026-04-27. Full pipeline proven against real data: 15 client calls each got `calls` + `call_participants` + `call_transcript_chunk` (with chunks + embeddings) + `call_action_items` + `call_summary` (with chunk + embedding, after the in-session `markdown_formatted` adapter fix + backfill). 14 non-client calls (internal/external) got `calls` + `call_participants` only, as designed. Cloud state: +29 calls, +30 documents (15 transcript_chunk + 15 summary), +170 chunks, +153 action_items, +0 auto-created clients. The two debug-window race-condition `failed` rows tracked separately as a known non-bug; calls themselves are present in `calls` from the winning concurrent sweep.
- **Two F2.1 doc-vs-reality gaps caught at deploy** (both same root cause — read OpenAPI without empirical curl probe): X-Api-Key (vs documented Bearer) and `markdown_formatted` (vs spec-driven `markdown`/`text`/etc.). Both fixed in this session; both pinned by unit tests. The "API integration discovery — verify auth scheme empirically" followup captures the lesson; same memory note covers payload-shape verification by extension.
- **Logged:** 2026-04-24 (F2.5 paused); 2026-04-27 (M1.1 zero-delivery check); 2026-04-27 (M1.2 cron build); **resolved:** 2026-04-27 (M1.2.5 first real sweep + both adapter fixes + 15-summary backfill).

## F2.4 handler must use `INSERT ON CONFLICT DO NOTHING` — RESOLVED 2026-04-24

- **Resolution:** F2.4 `api/fathom_events.py` uses `db.table("webhook_deliveries").upsert(..., on_conflict="webhook_id", ignore_duplicates=True, returning="representation")`. Empirically verified (F2.4 dedup probe, 2026-04-24): first insert returns `data_len=1`, duplicate returns `data_len=0`. Handler checks `if not insert_resp.data` and returns 200 `{"deduplicated": True, ...}` without invoking the ingest chain. Live test path 2 (duplicate replay) confirmed: same webhook-id posted twice, second call returned 200 dedup + cloud state unchanged (no second `calls` row, no second embedding cost).
- **Logged:** 2026-04-24 (F2.3 flag); **resolved:** 2026-04-24 (F2.4 impl + test).

## PostgREST transient empty-body 400 on count queries — pattern observed multiple sessions

- **What:** Over F1.4, F2.3, and F2.4 the supabase-py client has intermittently failed on `.select("id", count="exact", head=True).execute()` with `postgrest.exceptions.APIError: {'message': 'JSON could not be generated', 'code': 400, 'hint': 'Refer to full message for details', 'details': "b''"}`. The pattern: PostgREST returns an empty response body; postgrest-py tries to parse it as an APIError, fails at pydantic validation, re-raises a synthesized 400. Not a bug in our code — the service itself is returning an empty body. Affects only head-count queries; full SELECT queries are unaffected. Retrying the same query moments later usually succeeds.
- **Why it matters:** test verification scripts that rely on head-count queries flake intermittently, producing false-failure signals when the actual handler + pipeline work correctly. F2.4's test script was patched to use direct psycopg2 queries for count verification (see `scripts/test_fathom_webhook_locally.py` `_count()` helper), which side-steps the issue entirely. Not a production-path concern since the Fathom handler doesn't issue head-count queries, but the Ella agent's retrieval path and future admin queries might.
- **Next action:** none today. Watch for the failure pattern in production code after F2.5 deploys — if it ever hits a user-visible path, file upstream with Supabase + postgrest-py. Until then, any ops script that needs a reliable count should use `.select("id", count="exact")` without `head=True` (returns the data array which the client can `len()` safely) or drop to psycopg2 direct.
- **Logged:** 2026-04-24 (F2.4 — consolidating observations from F1.4 and F2.3 into one entry).

## F2.4 — traceback sanitization is belt-and-suspenders, not defense in depth

- **What:** F2.4's `_sanitize_traceback` strips lines containing `whsec_`, `sk-`, or `eyJh` before persisting to `webhook_deliveries.processing_error`. This catches the three most common secret prefixes if a traceback accidentally includes env values. But it's not exhaustive — Supabase service role keys are JWTs (start with `eyJh`, which IS matched), but other secret formats (e.g., the pooler password which contains `#`) would pass through unstripped.
- **Why it matters:** minor — the pipeline code doesn't log env values in normal execution. The sanitization is a last-resort defense against an exception that accidentally interpolates an env value into its message. Unlikely to bite in practice, but "unlikely" is not "never."
- **Next action:** no action today. If a failed-row investigation ever surfaces an env value in `processing_error`, expand `_sanitize_traceback`'s pattern list. Or adopt a more principled redaction library (e.g., `secrets.compare_digest` patterns) if the codebase ever grows enough secret-handling paths to justify it.
- **Logged:** 2026-04-24 (F2.4 — intentional micro-debt).

## F2.5 deploy — webhook URL must be exactly `/api/fathom_events`

- **What:** Vercel routes `api/fathom_events.py` to the URL path `/api/fathom_events` (filename = path). When registering the production webhook via Fathom's `POST /webhooks`, the `destination_url` must be `https://ai-enablement-sigma.vercel.app/api/fathom_events` (or whatever the current production Vercel domain is — same project that hosts `api/slack_events.py`, confirmed via CLAUDE.md § Live System State). The trailing path matters exactly: `/api/fathom_events/` with a trailing slash or `/fathom_events` without the `api/` prefix would 404. Also confirm the Vercel deploy picked up `api/fathom_events.py` as a function (visible in Vercel's Functions tab on the dashboard).
- **Why it matters:** F2.5 registers the webhook via a one-shot curl, and once registered, Fathom starts delivering real coaching-call content. A misrouted URL means deliveries 404 silently from our side — Fathom retries for a bit, then gives up per whatever their dead-letter policy is. By the time we notice ("Ella doesn't have data for Monday's call"), several calls could be lost to the cron backfill window.
- **Next action:** during F2.5, first `curl https://ai-enablement-sigma.vercel.app/api/fathom_events -X GET` after deploy — should return 200 with `{"status":"ok","endpoint":"fathom_events","accepts":"POST"}` (the browser-friendly GET hint). If it 404s, fix deploy before registering the webhook. Then register via `POST /webhooks` with that exact URL. Then immediately `curl ... -X POST` with a bad signature and expect 401 — confirms the handler is wired through.
- **Logged:** 2026-04-24 (F2.4 — F2.5 pre-flight reminder).

## call_summary chunk metadata spec unpinned in validator

- **What:** F2.3's `_ensure_summary_document` writes summary chunks with empty metadata (`{}`) because the validator has no pinned spec for `("fathom", "call_summary")` chunk metadata — `validate_chunk_metadata` silently passes when metadata is empty. That's fine today (doc-level metadata carries all retrieval context; chunk-level metadata adds nothing useful for a 1-chunk summary). But `docs/ingestion/metadata-conventions.md` §4 is our declared source of truth for chunk metadata, and a `call_summary` row in the validator's `_CHUNK_SPECS` would make the intent explicit.
- **Why it matters:** minor — today it's fine. If future work starts writing non-empty summary-chunk metadata (section hints, speaker attribution, etc.) without updating the validator spec, the writer gets a warning log per chunk. Easy to miss in production.
- **Next action:** either (a) add `("fathom", "call_summary"): _Spec(required=frozenset(), optional=frozenset())` to `shared/ingestion/validate.py:_CHUNK_SPECS` and update `docs/ingestion/metadata-conventions.md` §4 to note the convention (~10 lines across both files), or (b) defer — harmless as long as future summary writers keep passing empty metadata.
- **Logged:** 2026-04-24 (F2.3 build — intentional micro-debt).

## Summary chunk embedding goes stale when Fathom regenerates a summary

- **What:** `pipeline._sync_summary_content` updates `documents.content` when Fathom re-delivers a call with an updated `default_summary`, but does NOT re-embed the existing chunk (chunk row is left intact, `embedding` column unchanged). The retrieval index therefore carries an embedding for the OLD summary text while the doc+chunk content column shows the NEW text. Retrieval quality on re-summarized calls may drift.
- **Why it matters:** unknown frequency — F2.1 live-test unknown #3 ("does Fathom ever re-fire `new-meeting-content-ready` with updated summary?") is still open. If Fathom never re-fires, this is a non-issue. If it does, retrieval for re-summarized calls could miss relevant content because the embedding is semantically attached to the prior summary text.
- **Next action:** two tiers: (a) cheap — when `_sync_summary_content` detects a content change, DELETE the summary's chunks so the next ingest pass re-chunks + re-embeds (pipeline's existing `_count_chunks == 0` branch handles the re-insert). One extra embedding call per re-delivered summary. Wire up during F2.4 or as a small follow-up. (b) If live-test reveals re-fires never happen, this entry gets closed with no code change.
- **Logged:** 2026-04-24 (F2.3 architecture nuance).

## Single-chunk summary ceiling at embedding model's input limit

- **What:** F2.3's summary path writes one chunk per call regardless of summary length. `text-embedding-3-small` accepts ~8192 tokens per input (~6000 words) — plenty of headroom for typical Fathom summaries (200–500 words). But a transcript of a 3-hour workshop might produce a 2000+ word summary; near the ceiling but still OK. A future unexpected input shape (e.g., Fathom shipping a full meeting notes doc as the "summary") could overflow.
- **Why it matters:** unlikely today; embedding call would raise `openai.BadRequestError` on overflow, which the pipeline's `except Exception` in the chunk loop catches but logs as a chunk-insert failure. We'd notice only via `webhook_deliveries.processing_status='failed'` rows with a specific error pattern, not via data loss (call still lands; summary just stays empty).
- **Next action:** no action today. If/when a failed delivery traces to "summary too long," add paragraph-aware chunking to `_ensure_summary_document` — split on `\n\n` boundaries, target ~500 words per chunk, same pattern as `chunk_transcript` but for text-shaped input. Estimated ~30 lines of code.
- **Logged:** 2026-04-24 (F2.3 capacity forecast).

## Fathom webhook design intel — RESOLVED 2026-04-24 (F2.2 superseded this entry)

- **Status:** superseded by `docs/architecture/fathom_webhook.md`, which contains the committed F2.3 build spec. All F2.1 headline findings (event types, payload shape, identifier compatibility, signing algorithm, registration API, fallback `GET /meetings`) are incorporated there. This followup kept as history for one cycle; safe to delete after F2.3 ships.
- **Logged:** 2026-04-24 (F2.1 discovery); **resolved:** 2026-04-24 (F2.2 architecture committed).

## Fathom webhook — delivery semantics live-test (3 of 4 still open, plan-tier resolved)

- **What:** F2.1 identified four unknowns: (1) `webhook-id` stability across retries, (2) retry count + backoff schedule, (3) summary regeneration firing a second `new-meeting-content-ready`, (4) plan-tier gating. F2.5 (2026-04-24) registered the production webhook via Fathom's UI — **plan-tier (#4) is effectively resolved**: no upgrade prompt, no error, registration succeeded. The other three remain open; they can only be observed once a real delivery (and a retry or regeneration) arrives. Architecture in `docs/architecture/fathom_webhook.md` is defensive on all three so none block production operation.
- **Why it matters:** per-retry behavior (#1, #2) sets expectations for our dedup layer and outage tolerance; summary regen (#3) tells us whether `_sync_summary_content` gets exercised organically. None are blockers — each has a defensible default in the handler — but the actual numbers sharpen operational expectations. If #1 turns out to be unstable, we're already protected by the secondary `(source, external_id)` dedup at the `calls` unique constraint. If #2's retry window exceeds our outage tolerance, that's F2.6 cron backfill's problem to solve. If #3 fires, `_sync_summary_content` updates `documents.content` but doesn't re-embed — the stale-embedding followup is already logged.
- **Next action:** no active work. Observe when first real delivery lands (see the "F2.5 first-real-delivery verification" followup). For #2 specifically, force a retry by returning 500 from the handler briefly (temporarily break the signature verify, say) and observe Fathom's retry cadence — but that's a F2.7 nice-to-have, not a pilot blocker. For #3, wait to see if any delivery shows up with `call_external_id` matching an already-processed call.
- **Logged:** 2026-04-24 (F2.1 discovery); partial resolution 2026-04-24 (F2.5 registration proved plan-tier).

## Fathom webhook secret rotation runbook — needed before first rotation

- **What:** Fathom's API exposes `POST /webhooks` (create) and `DELETE /webhooks/{id}` but no `PATCH`/rotate endpoint. Rotating the production webhook secret requires: (1) create a new webhook at the same URL with a fresh secret, (2) the new webhook's secret is returned in the `POST` response body only once, (3) update the `FATHOM_WEBHOOK_SECRET` env var on Vercel and redeploy, (4) delete the old webhook. Between steps 1 and 3 Fathom may be delivering against both — both must verify against whichever secret was valid at send time. Without a runbook, rotation is error-prone: a mistimed step either drops deliveries (old webhook deleted before new secret is live) or leaks PII (new webhook delivered before env var updated means signature-fail 401s, Fathom retries, eventually dead-letters).
- **Why it matters:** webhook secrets should rotate on suspected compromise (accidental commit, team-member offboarding, vendor breach). Today there's no documented procedure so it'll either be "Drake figures it out at 2am under pressure" or "nobody rotates and we carry a stale secret forever."
- **Next action:** during F2.3 implementation, spend an hour drafting `docs/runbooks/fathom_webhook_secret_rotation.md` with the exact command sequence, expected durations, and verification steps. Include the fallback: for a brief overlap window, the handler accepts either of two env-var-loaded secrets (`FATHOM_WEBHOOK_SECRET`, `FATHOM_WEBHOOK_SECRET_PREV`) and verifies against both — that eliminates the racing-deliveries problem. Drop the PREV var 5 min after the new one goes live.
- **Logged:** 2026-04-24 (F2.2 architecture work surfaced the gap).

## Fathom webhook observability — pull queries vs push alerts

- **What:** F2.2 architecture leaves observability at "Drake runs SELECT on `webhook_deliveries` every few days." Works for V1, but the pull model fails silently: if nobody runs the query for a week and there's been a quiet failure-mode streak, nobody knows. A push-mode alert (e.g., daily 08:30 UTC after the cron sweep: if `select count(*) from webhook_deliveries where status != 'done' and received_at > now() - interval '24 hours'` is nonzero, DM Drake in Slack with the top-5 error signatures) would turn this from "Drake remembers to check" to "the system tells Drake when something's off."
- **Why it matters:** V1 pilot volume is low, so daily quiet failures are plausible (a few missed calls over a week without realizing). By the time we notice in retrieval ("Ella doesn't know about Javi's Monday call"), we've already lost a pilot-week data point. Push alerts close the feedback loop.
- **Next action:** after F2.3 ships and `webhook_deliveries` has accumulated ~2 weeks of real data, assess whether failed-row rate warrants the Slack DM automation. If it does, write a new scheduled agent (n8n workflow or Vercel Cron + Slack Web API) that posts daily. Cadence-wise, this matches `/schedule`-style automation.
- **Logged:** 2026-04-24 (F2.2 architecture — operational nice-to-have).

## Fathom webhook backpressure at scale — defer until > 500 calls/day

- **What:** F2.2 architecture assumes Fathom deliveries don't outpace Vercel's concurrent-function limit. Current pilot volume is ~20 calls/day. At some growth point — rough guess: 500 calls/day, if Fathom batches morning deliveries into a burst — we'd hit Vercel's Hobby-tier concurrency ceiling or the Pro-tier soft limit. At that point our handler needs a queue in front (SQS, Inngest, or a lightweight Postgres-row-queue read by a worker) so Fathom deliveries ack fast and processing runs async behind.
- **Why it matters:** not yet. The 100-client Active++ roster produces ~10–20 coaching calls/day, so we have ~25× headroom before this bites. Flagged now so future-us doesn't have to rediscover the constraint under duress.
- **Next action:** monitor `webhook_deliveries` cardinality weekly. Trigger a redesign when daily counts climb past ~200 (50% of capacity heuristic). The redesign shape: handler writes payload to a `webhook_queue` table, returns 200 immediately; a Vercel Cron every 5 minutes processes the oldest ~50 rows. Shape stays compatible with current `pipeline.ingest_call` — queue drain is just a new caller.
- **Logged:** 2026-04-24 (F2.2 architecture — capacity forecast).

## Fathom `include_crm_matches` — possible future enrichment

- **What:** Fathom's webhook can include `crm_matches` — they do CRM lookups against external CRMs (HubSpot, Salesforce, etc.) and attach the match to a meeting's payload. We don't use a CRM today, so it doesn't matter for V1. Schema details are in the OpenAPI at `https://developers.fathom.ai/api-reference/openapi.yaml` under `CRMMatches`.
- **Why it matters:** if we ever connect a CRM (Drake hasn't ruled it out — it's mentioned in the folder structure's `crm/` placeholder under `ingestion/`), the webhook would start delivering enriched data "for free." Worth knowing the shape before designing the CRM ingestion path.
- **Next action:** no action. Note for when Drake decides on CRM tooling — the Fathom webhook may already carry half of what's needed.
- **Logged:** 2026-04-24 (F2.1 discovery — peripheral finding).

---

## Auto-created client review workflow — human-owned queue, 34 rows live on cloud as of F1.4

- **What:** the Fathom ingestion pipeline auto-creates a minimal `clients` row when a transcript's non-team participant doesn't match any existing client by email (primary or `metadata.alternate_emails`) or by name (primary or `metadata.alternate_names`). Auto-created rows carry `tags=['needs_review']` and `metadata.auto_created_from_call_ingestion=true` + `auto_created_from_call_external_id` + `auto_created_from_call_title` + `auto_create_reason` + `auto_created_at` breadcrumbs (see `ingestion/fathom/pipeline.py:_build_auto_create_metadata`). Their associated `calls` land medium-confidence and their `documents` land `is_active=false` — chunks exist but are invisible to `match_document_chunks` until promoted. Promotion (merging into a canonical row, flipping retrievability, reactivating the document) happens via the Gregory dashboard's "Merge into…" flow on the Clients detail page (M3.2 — atomic via `merge_clients` RPC, migration 0015). The original four pilot pairs were merged via the now-archived one-shot at `scripts/archive/merge_client_duplicates.py`. **There is no agent reviewing these rows; Drake or Zain does it by hand via the dashboard.** **Live cloud state post-F1.4: 34 `needs_review` rows** (34 unique emails → 43 medium-confidence `call_transcript_chunk` docs sitting `is_active=false`, ~550 chunks total). Notable in-queue duplicates the reviewer should collapse on first pass: `allison@silicoproplogicsolutions.com` ↔ `allison@sproplogicsolutions.com` (typo variants of one person), `vid@remodellectai.com` ↔ `vid.velayutham@remodellectai.com` (same person, two captured email addresses — both display as "Vid Velayutham"), `nate@trovki.com` ↔ `natesimon34@gmail.com` (both captured as "Nathan Simon"). Privacy-proxy oddity: one row's email is an Apple Hide-My-Email alias `2_gu4dkojxgiztqnjygu4tomrthdm2qy424oopn2k4tym2vypx4qcm7yiyqiaxaf7g3me4sdg35spsk@imip.me.com` displaying as "Robert Traffie" — preserve display name in `alternate_names` on whichever canonical we merge into (the merge RPC handles this automatically).
- **Why it matters:** unreviewed `needs_review` rows leave real coaching call context in the KB but invisible to Ella (because `is_active=false` gates the transcript_chunk documents). That's the desired safety behavior for ambiguous matches, but the cost is invisible-until-reviewed content. Pilot-week clients are already handled by the F1.2 preload + the original four merges; the risk lives in the long tail of non-pilot client calls that Drake may want Ella to see later. Separately, if auto-create volume climbs (new client roster churn, parser false negatives, re-ingest after webhook lands), the hand-review workflow starts to cost real time.
- **Next action:** the dashboard merge surface exists as of M3.2. Drain the 34-row queue when convenient by visiting each `needs_review`-tagged client's detail page and clicking "Merge into…". When the hand-review starts feeling heavy — revisit triggers: (a) a pilot client's call doesn't surface in an Ella retrieval Drake expected and digging shows an un-promoted auto-row, (b) auto-create count per ingestion batch exceeds ~20, (c) Zain asks for a review tool that's smarter than per-row inspection — design a grouping / fuzzy-match overlay on top of the existing dashboard that surfaces inferred canonicals (name fuzzy-match, email domain, co-occurrence on same call) and lets a human one-click merge. Until then: periodically `select id,email,full_name,metadata->'auto_created_from_call_external_id' from clients where 'needs_review' = any(tags)` to inventory the queue, then merge from the dashboard.
- **Logged:** 2026-04-24 (expanded 2026-04-24 post-F1.4 with actual queue size + in-queue duplicate list).

## 9 client-category calls landed with NULL primary_client_id — orphan transcript chunks

- **What:** F1.4 post-ingest verification surfaced 9 `calls` rows with `call_category='client'`, `classification_method='title_pattern'`, confidence 0.60, AND `primary_client_id IS NULL`. Each has a `call_transcript_chunk` document (is_active=false, chunk counts 2–16 each, ~88 chunks total) with `metadata.client_id=null`. Affected titles: `30mins with Scott (The AI Partner) (...)` for Allison Boeshans, Cindy Yu, Connor Malewicz, King Musa, "Musa  Elmaghrabi " (with trailing/double spaces), Owen Nordberg, Shivam Patel (two variants: trailing-space and clean), tina Hussain. Curious because (a) "King Musa" and "Musa  Elmaghrabi " are the pilot Musa — who F1.2 preloaded and who *did* resolve correctly for his other 3 calls; (b) these landed without also triggering an `AutoCreateRequest`, so the auto-create fallback was bypassed in the classifier.
- **Why it matters:** Ella retrieval is safe (all 9 docs are `is_active=false`, so chunks are invisible to `match_document_chunks`), but those ~88 chunks are orphaned — no canonical client row to promote them to, no auto-row to merge into. A pilot client's calls are among them (Musa × 2), meaning Ella can't surface those two coaching calls to Musa's pilot channel until the underlying classifier issue is fixed and the calls are re-ingested. That's two specific conversations missing from his context window. Additionally this is a symptom of a real classifier edge case — the path through `_classify_by_title` where title_pattern matches but the participant identity on the call is malformed enough that neither resolver hit works AND the AutoCreateRequest path is skipped.
- **Next action:** (1) query sample the underlying transcripts to see what the participant field looks like on one of these calls — specifically the "King Musa" call (external_id 134757219) and "Musa  Elmaghrabi " (134393413) vs Musa's resolved call "30mins with Scott (The AI Partner) (King Musa) Mar 19 2026" to understand the classifier branch that's dropping the auto-create; (2) if the fix is straightforward (e.g., strip whitespace before name-lookup, or ensure `_classify_by_title` always emits AutoCreateRequest when no client resolves), patch `ingestion/fathom/classifier.py` and re-run ingestion for just the 9 affected external_ids via `--only-category client` filter (pipeline upsert will re-process); (3) if complex, leave the orphans as-is and document — pilot rollout isn't blocked since the 9 calls are already absent from retrieval. Worth doing before the live Fathom webhook lands because every new call that hits this classifier branch will also orphan.
- **Logged:** 2026-04-24 (from F1.4 post-ingest verification).

## Preload `alternate_emails` / `alternate_names` on 4 merged pilot rows before Fathom ingest — RESOLVED 2026-04-24, F1.4-confirmed

- **What:** cloud `clients` rows for Javi Pena, Musa Elmaghrabi, Dhamen Hothi, Nicholas LoScalzo were missing the alternate emails/names local had (merge script was run against local only; 2026-04-23 cloud seed only pushed canonical Active++ rows).
- **Resolution:** F1.2 session copied local's alternates onto cloud via a single-transaction jsonb merge. F1.4 post-ingest verification confirmed zero pilot duplicates in the 34-row `needs_review` queue — all 4 pilots resolved cleanly to canonical IDs (Javi 7 calls, Musa 3 retrievable calls, Dhamen 8, Nicholas 8). The F1.2 preload worked end-to-end. Safe to remove this entry next session; kept today as the record that F1.2→F1.4 closed the loop.
- **Logged:** 2026-04-24 (resolved F1.2; confirmed F1.4 same day).

## `call_participants` unique on `(call_id, email)` admits NULL-email duplicates

- **What:** F1.1 audit confirmed the only unique constraint on `call_participants` is `(call_id, email)` (btree). Postgres treats `NULL` as distinct in unique indexes by default, so two rows on the same call with `email IS NULL` would not violate. The Fathom pipeline's `_upsert_participants` always calls `pt.email.lower()`, so a `None` email would raise `AttributeError` rather than silently insert — but a parser change or a new ingestion path that inserts `NULL` emails would bypass the constraint without warning.
- **Why it matters:** minor today (TXT parser always produces an email string per participant), but it's a latent footgun for future ingestion paths — webhook-based, CRM-based, or any path where a participant could legitimately lack an email.
- **Next action:** no action today. If/when we add a non-TXT participant ingestion path, either (a) require email on participants in the schema (`NOT NULL`), or (b) change the unique to `(call_id, coalesce(email, ''))` via an expression index. Flag during that future feature's design, not now.
- **Logged:** 2026-04-24.

## PostgREST 1000-row page cap — use `count='exact', head=True`

- **What:** `db.table("x").select("id").execute()` against cloud silently caps at 1000 rows — PostgREST's default page size. `len(resp.data)` in that case is the page size, not the row count. For accurate counts, always use `db.table("x").select("id", count="exact", head=True).execute().count`.
- **Why it matters:** caught once on 2026-04-23 while building the `CLAUDE.md` snapshot — I reported `document_chunks: 1000` and `slack_messages: 1000` when the actual counts were 4,179 and 2,914. A silent undercount that gets into a doc or a Slack status message is worse than an obvious error, because the number looks plausible at a glance.
- **Next action:** no one-time fix; this is a behavioral reminder for anyone writing ops scripts or quick counts. If we end up writing enough count-queries to want a shared helper, add one to `shared/db.py` (something like `row_count(table_name)`) that always uses the `count='exact', head=True` shape. Until then, be explicit at every call site.
- **Logged:** 2026-04-24.

## `agent_runs.duration_ms` never written — latency observability gap

- **What:** every Ella `agent_runs` row has `duration_ms = NULL`. The column exists, `shared.logging.end_agent_run` accepts the kwarg, but no agent currently times the turn or passes the value through. Cross-logged as a deferred idea in `docs/future-ideas.md` § "`duration_ms` instrumentation on agent_runs" with the full fix plan.
- **Why it matters:** we can't answer "is Ella getting slower over time?" or "which pilot channel is hitting the worst cold-start latency?" from the rows we have. Tokens and cost land correctly (`shared.claude_client.complete()` writes those via its own UPDATE), so the "is she expensive?" question is covered; latency is the observability hole.
- **Next action:** resolution lives in `docs/future-ideas.md`. This followup is the awareness reminder — until that lands, any latency concern needs to be diagnosed from Vercel request timings, not from the DB.
- **Logged:** 2026-04-24.

## Fluid Compute on Vercel — sub-3s user-visible latency path

- **What:** Ella's webhook is synchronous because Vercel's Python runtime kills background threads at response time. Fluid Compute is Vercel's opt-in runtime setting that would let the handler return 200 fast and keep the Python process alive to finish `chat.postMessage` after the response is sent. With Fluid Compute on, we could revert to an ack-then-work pattern and cut user-visible latency back under 3 seconds on cold starts.
- **Why it matters:** current cold-start experience is a 5–10s gap between @mention and reply — acceptable for V1 pilot volume, will get noticeable if pilot usage climbs. The retry-skip branch in `api/slack_events.py` keeps the architecture correct either way; Fluid Compute would just make it feel faster.
- **Next action:** revisit when (a) pilot users flag the lag explicitly, (b) pilot volume makes cold starts visible several times per day per channel, or (c) we're adding a second agent on the same Vercel project and want the runtime choice unified. Toggling Fluid Compute is a project-level setting; enabling it means reverting the sync path in `api/slack_events.py` to the ack-then-thread pattern that was originally designed.
- **Logged:** 2026-04-24.

## Aman automated classifier — deferred in favor of manual reclassification via Gregory dashboard

- **What:** an auto-classifier path for sales calls (via new `sales` category, tag on `external`, or LLM-based classification). The original M2 plan was to design and implement this.
- **Why deferred:** replaced by manual reclassification via the Gregory Calls page (M2.5). Manual review at current call volume (~66 backlog + ~few/week new) is sustainable.
- **Revisit trigger:** manual review becomes a recurring pain (Drake or Zain spending >30 min/week on it), OR Aman's call volume materially increases, OR a new sales hire is added to the team.
- **Logged:** 2026-04-28.

## RLS revisit trigger for Gregory dashboard

- **What:** Row-Level Security policies for the dashboard. Per gregory.md's locked V1 spec, RLS is "off for V1" — meaning V1 ships with RLS *enabled* on every public table but *zero policies*, plus the dashboard's data layer (`lib/db/clients.ts` and the page-entry `team_members` lookup) using the **service role key** to bypass RLS entirely. The auth client (`lib/supabase/server.ts`, anon key + cookies) is used only to verify the user's session in the auth-gate layout. This split was forced into existence mid-M2.3b after the first deploy returned 0 clients despite 134 in cloud — RLS deny-default was the cause; the data-layer-via-service-role pattern was the resolution. V2 needs proper RLS policies on `clients`, `client_team_assignments`, `calls`, `call_action_items`, `client_health_scores`, `nps_submissions` so CSMs see only their assigned clients (joined via `client_team_assignments` where `role='primary_csm'` and `unassigned_at is null`); at that point the dashboard data layer can move back to the anon client (or keep the service-role split where admin operations like merge tooling still need to bypass).
- **Why deferred:** premature for current 2-user model (Drake + Zain admin). App-level auth gate is sufficient at this scale.
- **Revisit trigger:** first non-admin CSM gets dashboard access.
- **Logged:** 2026-04-28; expanded with V1 service-role-split detail and V2 implementation specifics 2026-04-28 during M2.3b housekeeping.

## Doc bugs in CLAUDE.md fathom_webhook section (caught in M2.1)

- **What:** the example queries in CLAUDE.md's fathom_webhook description reference column names that don't match the actual migration 0011: `status` should be `processing_status`, `error->>'traceback'` should be `processing_error`. Also: the description of `webhook_deliveries`' status enum mentions "processed" and "failed-via-race" but the actual enum is `received`, `processed`, `failed`, `duplicate`, `malformed`.
- **Why deferred:** doc cleanup, not a code bug. The actual code uses the right column names.
- **Revisit trigger:** next time CLAUDE.md gets a substantive edit, OR if these queries are ever copy-pasted by someone (Drake, Zain) and fail.
- **Logged:** 2026-04-28.

## docs/strategic-context.md missing

- **What:** Drake's session handoff template references `docs/strategic-context.md` as priority reading, but the file doesn't exist in the repo.
- **Why deferred:** either create the file (capturing the working norms currently in the handoff message) or remove the reference from the handoff template. 30-second fix, but not blocking.
- **Revisit trigger:** next session that has documentation slack to absorb a small task.
- **Logged:** 2026-04-28.

## Readability of `documents` table for human inspection

- **What:** the `documents` table mixes course content, call summaries, and call transcript chunks. Reviewing the table in Supabase Studio is hard because rows are heterogeneous and content is long.
- **Why deferred:** the Gregory dashboard (V1) solves this for call summaries (Section 4 of Calls detail). Course content readability is a separate concern, lower priority.
- **Revisit trigger:** course content auditing becomes a workflow Drake or someone else needs to do regularly.
- **Logged:** 2026-04-28.

## `@supabase/ssr` middleware breaks on Vercel Edge runtime in Next 14 — use Server Component gate instead

- **What:** wiring auth via `middleware.ts` with `@supabase/ssr`'s `createServerClient` crashes at runtime on Vercel's Edge runtime with `ReferenceError: __dirname is not defined`. A transitive dep in the bundle references `__dirname` (Node-only), and Vercel's middleware bundler injects it where Next.js' local `next build` doesn't reproduce the issue. Stable Next 14 doesn't support `export const runtime = 'nodejs'` for middleware (experimental in Next 15+). `@supabase/ssr` exposes no Edge-tailored entry point. Resolution: drop middleware, gate auth in a Server Component layout (`app/(authenticated)/layout.tsx` calls `getUser()` and `redirect('/login')` if null). Both are documented Supabase patterns; the Server Component variant is functionally equivalent for our 2-user dashboard. Token refresh happens client-side in `@supabase/supabase-js` when tokens expire.
- **Why deferred:** resolved in M2.3a — kept here as a constraint to preserve. Future Next.js / Supabase work in this repo must not re-add middleware-based auth without first verifying Vercel Edge bundling.
- **Revisit trigger:** Next.js 15+ adoption (`runtime = 'nodejs'` for middleware becomes stable, OR `@supabase/ssr` ships an Edge-safe entry).
- **Logged:** 2026-04-28.

## `@supabase/ssr` cookie API: always use `getAll`/`setAll`, never the deprecated `get`/`set`/`remove`

- **What:** `@supabase/ssr` 0.5+ deprecated the `get`/`set`/`remove` cookie triplet in favor of `getAll`/`setAll`. Both still work in 0.10.x, but the deprecated triplet is fragile under concurrent cookie writes and emits opaque runtime errors (no useful stack trace) when it fails. M2.3a's first auth-wiring iteration used the verbatim triplet from a Supabase tutorial; deploy returned `MIDDLEWARE_INVOCATION_FAILED` with no diagnostic detail. The refactor to `getAll`/`setAll` was correct on the merits but not the actual fix for that deploy (Edge-runtime `__dirname` was the real cause — see above) — kept the refactor anyway since it's the right pattern.
- **Why deferred:** resolved in M2.3a — kept here as a constraint. Future code (Server Components, Route Handlers, future middleware once Next 15 lands) must use `getAll`/`setAll`.
- **Revisit trigger:** never, unless `@supabase/ssr` releases a 1.0 with a different API.
- **Logged:** 2026-04-28.

## Vercel mixed-framework: explicit `framework` declaration is required when `functions` is also explicit

- **What:** Vercel auto-detects Next.js from a repo-root `package.json` with a `next` dependency — *but only if `vercel.json` doesn't have an explicit `functions` block*. Once `functions` is declared (which we need for the Python serverless functions in `api/`), framework auto-detection is suppressed and Vercel treats the project as "static + functions" — Next.js never builds. M2.3a's first push deployed only the Python functions; every dashboard route 404'd. One-line fix: add `"framework": "nextjs"` to `vercel.json`. Verified locally with `vercel build` before pushing — `builds.json` confirmed `@vercel/next package.json` build step appearing alongside the Python builds, and `.vercel/output/functions/` contained the expected Next.js route bundles.
- **Why deferred:** resolved in M2.3a — kept here as a constraint and a lesson for any future multi-framework Vercel project (e.g., adding a second backend language alongside Python + Next.js). The lesson is non-obvious enough to deserve permanent documentation.
- **Revisit trigger:** any new framework added to the repo's deploy.
- **Logged:** 2026-04-28.

## Supabase CLI default routing is broken in this environment

- **What:** `supabase db diff --linked` and `supabase db push` are silently comparing/pushing to local Docker Supabase rather than the linked cloud project. Verified by (a) the diff suggesting drop of a function that doesn't exist in cloud, and (b) M2.2's apparently-successful migrations 0011/0012/0013 never actually landing in cloud's database OR ledger (caught at the start of M2.3b when type-regen returned schema that didn't match expectations). `npx supabase gen types typescript --project-id <ref>` is similarly affected for write operations but works for reads via the API.
- **Why deferred:** production Python/Vercel services use cloud directly via `SUPABASE_DB_PASSWORD` and the pooler URL (`supabase/.temp/pooler-url`) — completely unaffected. Only CLI-mediated migration workflows are broken, and those have a working workaround (Studio + manual ledger registration; see below).
- **Revisit trigger:** next migration that needs to be applied (M3.x or later), OR before the team grows beyond Drake (other devs running CLI commands need this fixed). Diagnosis path: inspect `supabase/.temp/` for stale state, possibly re-run `supabase link`, possibly reset the local Docker stack.
- **Logged:** 2026-04-28.

## Studio + manual ledger registration is the temporary canonical migration pattern

- **What:** until the Supabase CLI default routing is fixed (above), all migration applications go through Supabase Studio SQL Editor with manual ledger registration. Three migrations (0012, 0013, 0014) applied this way during M2.2 / M2.3b recovery. The pattern: (1) run the `CREATE`/`ALTER` SQL in Studio's SQL Editor, (2) `insert into supabase_migrations.schema_migrations (version, name, statements) values (...) on conflict (version) do nothing`, (3) dual-verify (see next entry). Slower than `supabase db push` but reliable.
- **Why deferred:** workaround for the CLI routing bug. Works reliably; not blocking.
- **Revisit trigger:** when the CLI routing bug is fixed, this pattern can retire. Worth a one-page update to `docs/runbooks/apply_migrations.md` documenting this as the temporary canonical pattern, ideally before M3.1 in case any new migrations come up there.
- **Logged:** 2026-04-28.

## Migration application requires dual verification (schema reality AND ledger)

- **What:** M2.2's `supabase db push` reported success but never wrote to cloud's database OR ledger; the failure was silent because the CLI was routing to local Docker Supabase. The class of bug — single-query verification passing against the wrong database — applies to any migration workflow, not just the broken CLI. Process change: every future migration must verify BOTH (a) schema reality against cloud explicitly via `to_regclass('public.<table>')` or `information_schema.columns`/`pg_proc` queried through a connection that's *known* to target cloud (Studio SQL Editor or psycopg2 via the pooler URL), AND (b) ledger registration via `select version from supabase_migrations.schema_migrations where version = '<n>'`. If either returns 0 rows, the migration didn't actually apply — recover before declaring done.
- **Why deferred:** process discipline, no code work. Embedded in the Studio-pattern entry above; called out separately so the lesson survives even if Studio + manual-ledger goes away.
- **Revisit trigger:** every migration. This is a permanent practice, not a one-off.
- **Logged:** 2026-04-28.

## PostgREST stale-cache symptom can mask deeper issues

- **What:** when `npx supabase gen types` returns schema that doesn't match expectations, the first instinct (flush PostgREST cache via `notify pgrst, 'reload schema'` or Studio's "Reload schema cache" button) addresses only one possible cause. Equally likely: the migration didn't actually apply (see CLI routing bug above). M2.3b lost ~30 minutes chasing a "cache lag" that turned out to be three migrations never having landed in cloud. Diagnostic order: (1) verify the schema object actually exists in cloud via `information_schema` / `to_regclass`, (2) verify ledger registration, THEN (3) flush PostgREST if both pass.
- **Why deferred:** process discipline change, no code work.
- **Revisit trigger:** next time `gen types` returns unexpected results.
- **Logged:** 2026-04-28.

## `psql` not available in Drake's WSL — install errored

- **What:** Drake tried `sudo apt install postgresql-client` to get `psql` for ad-hoc queries; the install errored. For now, ad-hoc cloud queries go through Supabase Studio's SQL Editor; any Code-side query needs to use the existing Python connection patterns (`scripts/*.py` via psycopg2 with `SUPABASE_DB_PASSWORD` from `.env.local`). Several housekeeping commands in this session (the `notify pgrst` flush, the dual-verify queries) had to be handed off to Drake to run because Code couldn't run them locally.
- **Why deferred:** working around it via Studio is fine for now. Install fix isn't blocking any feature work.
- **Revisit trigger:** when Drake has 10 minutes between sessions to debug the apt errors, OR when a workflow genuinely requires `psql` available in terminal (e.g., a runbook that assumes it).
- **Logged:** 2026-04-28.

## `gregory.md` "Repo location" section was rewritten in M2.3 housekeeping — RESOLVED 2026-04-28

- **Resolution:** the original spec section showed Next.js nested in `dashboard/` and a "Vercel config gotcha" note that turned out to be wrong (Vercel auto-detection is suppressed by an explicit `functions` block, not the other way around). Rewritten in this housekeeping pass to reflect the actual deployed layout: Next.js at repo root, `vercel.json` declares `"framework": "nextjs"` plus the Python functions block, both build in one Vercel project. The original "Repo location" tree diagram replaced; the new section also captures *why* Next.js had to be at root (single-Vercel-project + Python functions in `api/` + framework auto-detection all combine to constrain the layout).
- **Logged:** 2026-04-28 (M2.3a deviation surfaced); **resolved:** 2026-04-28 (housekeeping rewrite).

## SearchableClientSelect fetch-all-on-mount — fine for V1, watch growth

- **What:** the merge dialog (M3.2) and the upcoming Calls page primary-client-id picker (M3.3) both render a client dropdown by fetching the full eligible-client list server-side on mount and filtering client-side as the user types. ~134 clients today; the round trip is one cheap PostgREST query and the rendered list fits comfortably in a 64-row scroll container. No keystroke-driven DB calls.
- **Why it matters:** the pattern has a soft ceiling. At ~500–800 clients the dialog open will start to feel sluggish (network + client-side initial-render cost); at ~5000+ rows the JS-side filter cost on every keystroke becomes visible. Neither limit is anywhere near today's scale.
- **Revisit triggers:** (a) `select count(*) from clients where archived_at is null` crosses ~800, (b) anyone reports the merge dialog or the Calls primary-client picker feeling slow on dialog open. Resolution path: server-filtered query bound to debounced search input — ~30 lines of refactor, no API change at the consumer level. Until then: the current implementation is correct for V1 scale.
- **Logged:** 2026-04-29 (M3.2 build).

## `merge_clients` transcript-doc query is whole-table filter — fine at current scale

- **What:** the `merge_clients` plpgsql function (migration 0015) reactivates transcript_chunk documents by querying `documents where document_type = 'call_transcript_chunk' and metadata->>'call_id' = any(<source's call ids as text[])`. Mirrors the Python script's "fetch all transcript chunks, filter on metadata.call_id in Python" approach, but server-side via the PostgREST equivalent. There's no index on `documents.metadata->>'call_id'` because that filter has only ever been used by the merge path.
- **Why it matters:** scan cost is proportional to total transcript_chunk doc count. Today: ~3000 documents in cloud, scan is fast. As ingestion grows past ~50k transcript_chunk docs the scan starts to become the merge bottleneck; a partial index `on (metadata->>'call_id') where document_type='call_transcript_chunk'` would fix it cleanly. Not a correctness issue — just a perf one.
- **Revisit triggers:** (a) `select count(*) from documents where document_type='call_transcript_chunk'` crosses ~50k, OR (b) merge dialog spinner ever takes more than ~2s on submit. Resolution: add the partial index in a small migration. Until then: status quo.
- **Logged:** 2026-04-29 (M3.2 build).

## Surface `alternate_emails` / `alternate_names` on Clients detail page

- **What:** Section 1 (Identity) on the Clients detail page renders `email` and `full_name`, but not `metadata.alternate_emails` / `metadata.alternate_names`. After a merge, the absorbed identities live in those fields and are invisible to dashboard reviewers without opening Studio. Fix: display them as a read-only "Also known as: x@y.com, foo@bar.com" line below the email field, and "Display name variants: Name A, Name B" below the full_name field. Source data is on the client row itself; no new query needed — the page entry already pulls full `metadata` via `getClientById`.
- **Why deferred:** not blocking, no behavior bug. Both fields are correctly populated by the M3.2 merge RPC (verified live during the three-Vid consolidation — both source emails accumulated cleanly into the gmail canonical's `alternate_emails`, dedup-aware across sequential merges into the same target). The data is correct; only the dashboard's read-back is missing. M3.3 (Calls page) is higher-priority forward motion.
- **Revisit triggers:** (a) next Clients detail page polish pass, (b) a reviewer asks "what merged into this client?" and Studio is the only answer, (c) audit needs surface for understanding why a given client matched a participant by an alt-email.
- **Logged:** 2026-04-29 (M3.2 live verification).

## `calls.summary` column is unused — cron path writes to `documents` instead

- **What:** the `calls.summary` text column (migration 0003) is empty for all 560 cloud rows. Fathom cron-ingested summaries land as `documents` rows of `document_type='call_summary'` keyed on `metadata.call_id` (22 such rows in cloud). The Calls detail page Section 4 (M3.3) was originally spec'd to read `calls.summary`; it now reads from `documents` instead, matching reality.
- **Why deferred:** no behavior bug. The dashboard renders the right content; the redundancy is just a column that's never written. Two clean fixes exist; neither is urgent.
- **Resolution options:**
  - **(a) Backfill `calls.summary` at ingest time.** When the Fathom pipeline writes a `call_summary` document, also UPDATE the `calls.summary` column with the same content. Reads then have one source. Costs: write amplification, drift risk if the document is regenerated and the column isn't.
  - **(b) Drop `calls.summary` in a small migration.** Acknowledge that summaries are documents, not call attributes. Costs: nothing — no live reader of the column.
- **Revisit triggers:** (a) we add a query that wants `calls.summary` indexed (rare — summaries are read-once-per-detail-view, not bulk-queried), (b) someone is surprised by the empty column during schema review and wants the redundancy resolved. Until then: status quo, dashboard reads from `documents`.
- **Logged:** 2026-04-29 (M3.3 build).

## Vercel deploys hit intermittent transient build/deploy failures that resolve on redeploy

- **What:** the M3.3 push to production failed at the Vercel deploy step despite a clean build (Next.js detected, all routes emitted, build completed in ~1m). The failure pattern: `status ● Error` with an empty Builds tree (`. [0ms]` and no `λ` function entries underneath); no error message in the build log or `vercel inspect`; production alias kept pointing at the previous good deploy. A redeploy of the same commit (no code change) succeeded.
- **Why it matters:** the failure mode is "loud" — the deploy doesn't silently land in a broken state, the alias doesn't flip, no users see the half-deploy. The blast radius is operator time + deploy minute consumption on the redeploy. Not blocking, but worth tracking so it doesn't become invisible noise.
- **Pattern recurrence:** observed at least once during M3.3 (2026-04-29). If it happens again in close succession or starts taking multiple redeploys to land, escalate to investigation.
- **Revisit triggers:** (a) the same failure mode hits twice in a row on the same commit, (b) a deploy lands in a broken state instead of failing visibly (alias flips to a non-functional deployment), (c) it starts happening multiple times per deploy session. Resolution path: check Vercel status page first; then dig into deployment Events via the dashboard UI (CLI doesn't surface those messages); then open a Vercel support ticket if pattern persists.
- **Logged:** 2026-04-29 (M3.3 deploy).

## NPS ingestion not built — Gregory brain reads it as neutral for every client

- **What:** the M3.4 brain treats the `latest_nps` signal as neutral (50, weight 0.20) for every client because `nps_submissions` is empty in cloud (no ingestion path exists). One of four V1.1 signals is doing nothing. Brain handles missing data gracefully — score is the weighted average over signals that DO have data, and the `factors.signals[].note` for `latest_nps` explicitly says "no NPS submissions on record (NPS ingestion not yet built)" — but the score is more meaningful with NPS than without.
- **Why deferred:** NPS ingestion is its own design conversation (where do scores come from? Survey tool integration? Manual entry via dashboard?). Not blocking V1.1 ship; brain reports honestly.
- **Revisit triggers:** (a) Drake adopts a survey tool and wants to wire it in, (b) someone manually enters a few NPS scores via Studio and the dashboard's NPS indicator starts surfacing them, (c) a CSM asks "why isn't NPS counted in this score?" and the answer "no data" stops being acceptable.
- **Logged:** 2026-04-29 (M3.4 ship).

## Slack signal ingestion to cloud — same gap as NPS for the brain

- **What:** `slack_messages` cloud table is empty (local-only ingestion per `docs/future-ideas.md`). The M3.4 brain V1.1 intentionally omits a Slack-engagement signal because the data doesn't exist server-side; adding the signal in code would just be neutral-for-everyone, no behavior win. Once cloud Slack ingestion lands, add a fifth signal to `agents/gregory/signals.py` (e.g. messages-in-last-14-days, sentiment trend) and re-balance weights.
- **Why deferred:** cloud Slack ingestion has its own followup (`docs/future-ideas.md`); not driven by Gregory.
- **Revisit triggers:** (a) cloud Slack ingestion goes live, (b) a CSM asks for "engagement" as a health signal explicitly. Resolution path: add `compute_slack_engagement(db, client_id)` to `signals.py`, add a weight constant, plumb into `compute_all_signals`, re-balance other weights to keep total at 1.0.
- **Logged:** 2026-04-29 (M3.4 ship).

## Gregory brain golden eval harness deferred — same V1 carve-out as Ella

- **What:** M3.4 ships without a formal eval harness. The unit tests cover signal math, scoring rubric, JSON parsing, and end-to-end wiring (37 tests), but there's no golden dataset of "client X should land in tier Y because of reasons Z" that gates rubric changes. Same V1 carve-out the M1 prompt established for Ella.
- **Why deferred:** the rubric is iterative — V1.1 is starting points, not locked. Building golden cases against numbers we expect to change wastes effort. Once the rubric stabilizes (~3-6 cron runs in, Drake reviews and tunes), build a 20-case golden dataset that covers the four signal-availability matrix corners (everything-known / cadence-only / action-items-only / nothing-known) plus tier-boundary cases.
- **Revisit triggers:** (a) Drake tunes the rubric in scoring.py and wants regression coverage on the change, (b) a brain run produces a tier that's clearly wrong (a green client who should be red, or vice versa) and we want a fixture to pin that case forever.
- **Logged:** 2026-04-29 (M3.4 ship).

## Gregory rubric quirk — never-called clients land green via the "0 action items = clean docket" interpretation

- **What:** the M3.4 first all-active sweep produced 93 green / 40 yellow / 0 red. The 93-green count overstates actual health because the rubric treats "0 action items" as 100 (clean docket, not "missing"), and combined with neutral cadence (50, when no calls exist) + neutral NPS (50), the math lands at `0.4×50 + 0.2×100 + 0.2×100 + 0.2×50 = 70 → green`. So a client who has never been called gets graded green.
- **Why it matters:** the score is communicating "this client is fine" for clients we've never spoken to. The dashboard's Health Score indicator is honest about the underlying signals (the "Why this score" expand shows the cadence note "No calls on record for this client"), but the headline number + green pill misleads at a glance.
- **Resolution options:**
  - **(a)** When `call_cadence` returns the no-calls-on-record case, force `insufficient_data=true` regardless of other signals' contributions. The "I have no real signals about this client" stance from `scoring.py` already exists for the all-neutral case; extend it to "if cadence is unknown, the rest of the rubric isn't trustworthy either."
  - **(b)** Change the `0 action items` interpretation from "100 = clean docket" to "neutral 50 when no calls have occurred." Cleaner semantics: action items are evidence of follow-through, and zero items on a client we've never talked to is no evidence either way.
- **Revisit triggers:** (a) when Drake tunes the rubric for the next iteration, (b) if a never-called client's green pill gets called out by a CSM as misleading. Lean: option (a) — scoping the insufficient-data trigger to "no cadence" is the smaller change and matches how a CSM thinks about the question.
- **Logged:** 2026-04-29 (M3.4 first all-active sweep, EOD review).
