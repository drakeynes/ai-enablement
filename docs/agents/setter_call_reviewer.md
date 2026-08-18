# setter_call_reviewer

Sonnet reviewer for rep sales calls. Reads a Deepgram transcript from
`setter_call_transcripts`, grades the call against the right rubric, and
persists a structured review to `setter_call_reviews` (see
`docs/schema/setter_call_reviews.md` for the full column contract). Posts a
summary to the sales-reviews Slack channel on first review.

Code: `agents/setter_call_reviewer/` — `reviewer.py` (orchestration +
validation), `prompt.py` (the three rubric prompts, `PROMPT_VERSION`),
`slack_post.py` (Block Kit message + never-double-post trail),
`talk_time.py` (diarization-based talk-time math — computed in-app, never
asked of the LLM).

## Pipeline position

`close_calls` (≥90s, recorded) → `ingestion/setter_calls` (Deepgram, audio
never touches our infra) → **this agent** → `setter_call_reviews` → Slack +
dashboard reads. Driven by `api/setter_calls_sweep_cron.py` every 15 min
(transcribe-then-review, cap 20/run; a failed review stays pending and
retries next sweep). Entry points: `review_call(close_call_id, force=False,
post_to_slack=True)`, `find_pending_reviews()`.

## Rubric selection (`_resolve_call_type`, one lead-chain lookup)

1. `revival` — lead carries the "DC Revival Lead" CF → close-on-phone
   rubric (`closed`/`no_close_reason`).
2. `dc_ads` — lead is in `dc_ads_lead_facts` (the DC paid-ads cohort) →
   close-on-phone rubric + the 0150 ad-intelligence signals: intent /
   offer-understanding / rep-score (all 0–10), main objection,
   why-not-closed vocabulary, recoverable, verbatim VoC quotes, archetype.
3. `outbound` — default fail-safe → book-a-closer rubric
   (`booked`/`no_book_reason`).

## Hard rules (Drake 2026-05-27, extended 2026-08-18)

- `lead_score` = lead QUALITY; `rep_score` = rep EXECUTION. Never blended.
- strengths/weaknesses 0–2 each, quote-evidenced, NEVER padded; empty is
  the common case.
- DQ bar: VERY obviously upset only — advisory, never auto-applied.
- Fixed vocabularies (`lead_attributes`, `why_not_closed`, `archetype`,
  VoC topics): new entries arrive via prompt+migration updates, not model
  invention. Off-vocab output **coerces to `'other'`** (logged warning);
  range/shape violations fail the review (`ReviewError`) and retry.
- VoC quotes are verbatim transcript words only, ≤4/call.
- Missed-sales / great-saves are derived downstream in SQL, never
  self-asserted by the model.

## Failure handling

`ReviewError` (non-JSON, missing keys, out-of-range) fails that call's
review; the cron logs it and the transcript stays pending → retried next
sweep. Slack posting is fail-soft (never breaks a review) and idempotent on
`slack_message_ts`. No `agent_runs` writes — sales LLM spend lives on the
row (`sonnet_*_tokens`, `sonnet_cost_usd`, ~$0.02/call at Sonnet 4.6).

## Evals

`tests/agents/setter_call_reviewer/test_reviewer.py` — structural
validation per rubric, dc_ads signal validation + vocab coercion, prompt
wiring/contract assertions. Prompt iteration is direct (no golden-set
gate); `prompt_version` on every row keeps old output attributable. v3
(2026-08-18) added the dc_ads rubric — earlier DC-cohort calls were graded
`outbound` (wrong motion); forward-only by decision, dashboard reads
filter `call_type='dc_ads'`.
