# setter_call_reviews

Sonnet structured analysis of rep sales calls — one row per reviewed call,
1:1 with `setter_call_transcripts` (PK + cascade FK `close_call_id`).
Migrations 0054 (v1), 0121 (call-type split), **0150 (dc_ads rubric +
ad-intelligence signals)**. Sales-side only: never in `documents`, no
embeddings, not retrievable by Ella / CS surfaces.

## Purpose

Every ≥90s recorded Close call is transcribed (Deepgram,
`setter_call_transcripts`) and reviewed by Sonnet on a 15-minute sweep
(`api/setter_calls_sweep_cron.py`). The review powers the sales-reviews
Slack channel, the per-call page (`/sales-dashboard/calls/[close_id]`), and
— since 0150 — the DC Ads dashboard's AI call-intelligence layer.

## Rubrics (`call_type`)

Resolution order per call (`agents/setter_call_reviewer/reviewer.py`
`_resolve_call_type`, one lead-chain lookup):

1. **`revival`** — the lead carries the "DC Revival Lead" Close CF
   (`REVIVAL_CF`). Close-on-phone rubric: `closed` / `no_close_reason`.
2. **`dc_ads`** (0150) — the lead is in `dc_ads_lead_facts` (the DC
   paid-ads cohort). Close-on-phone rubric PLUS the signal set below.
3. **`outbound`** — everything else. Book-a-closer rubric: `booked` /
   `no_book_reason`.

The outcome CHECK enforces exactly the active pair; the reviewer nulls the
inactive pair (and, off-dc_ads, the signal columns) explicitly so re-grades
never leave stale values.

## Columns

- **Base (0054, all rubrics):** `sentiment`, `lead_score` 0–10 +
  `lead_score_reason` (lead QUALITY, never rep performance), advisory
  `should_be_dqd`/`dq_reason` (VERY-obviously-upset bar; humans flip Close),
  `setter_strengths`/`setter_weaknesses` (jsonb, 0–2 quote-evidenced items,
  never padded), `lead_attributes` (fixed-vocab `key:value` strings),
  talk-time (`setter_words`/`prospect_words`/`talk_ratio_setter`, computed
  in-app, not by the LLM), provenance (`model`, `prompt_version`,
  `sonnet_*_tokens`, `sonnet_cost_usd`), Slack trail (`slack_channel`/
  `slack_message_ts`/`slack_posted_at` — the never-double-post contract).
- **Outcome (0121):** `booked`/`no_book_reason` (outbound) or
  `closed`/`no_close_reason` (revival + dc_ads).
- **dc_ads signals (0150, null on other rubrics; Nabeel 2026-08-18):**
  `intent` 0–10 (buying intent, independent of ability to pay),
  `offer_understanding` 0–10 (low across an ad's cohort = the ad/LP set
  wrong expectations), `rep_score` 0–10 + `rep_score_reason` (rep EXECUTION
  — the lead_score split rule applied to the rep side), `main_objection`
  (short free text, nullable), `why_not_closed` (fixed vocab, required iff
  `closed=false`: `didnt_understand_offer` · `low_intent` ·
  `price_platform_objection` · `rep_execution` · `bad_timing` ·
  `skepticism` · `cant_pay_today` · `spouse_partner` · `other`),
  `recoverable` + `recoverable_note` (could a follow-up still close it),
  `voc_quotes` (jsonb `[{quote, topic}]`, topic ∈ goal/fear/objection/
  why_applied/other — VERBATIM prospect quotes for marketing mining, ≤4),
  `archetype` (`high_intent_entrepreneur` · `curious_ai_learner` ·
  `broke_opportunity_seeker` · `skeptic` · `existing_business_owner` ·
  `other`).

Vocabularies are fixed lists mirrored in DB CHECKs; the reviewer **coerces**
off-vocab model output to `'other'` (logged) rather than failing the review.
Missed-sales / great-saves flags are deliberately NOT columns — they derive
in SQL from (`lead_score`, `intent`, `rep_score`, `closed`) so thresholds
stay tunable without re-reviewing.

**Rollout (2026-08-18):** pre-0150 DC-cohort calls were graded `outbound`
(wrong motion — the CF-based detection predates the ads cohort); the DC Ads
dashboard reads `call_type='dc_ads'` ONLY, so wrong-rubric reviews never
surface there. Shipped forward-only; after Nabeel verified the first v3
output the ~460-call **backfill was approved and run the same day** via
`api/dc_reviews_backfill_cron.py` + `dc_ads_backfill_candidates()` (0153)
— re-reviews with `force=True`, Sonnet-only (~$0.02/call), no Slack
reposts. The candidates function excludes revival-CF leads (correctly
graded) so the queue provably drains; the endpoint stays for any future
rubric migration, its cron schedule removed once the queue read 0.

## Populated by / read by

- **Writes:** `agents/setter_call_reviewer/reviewer.py` `review_call()`,
  driven by `api/setter_calls_sweep_cron.py` (15-min tick, transcribe-then-
  review; per-run cap 20).
- **Reads:** Slack post (`slack_post.py`), `lib/db/setter-calls.ts`
  (per-call page + list), and the DC Ads AI-intel reads (0151+).

## Example queries

```sql
-- The why-not-closing distribution over a window (dc_ads rubric only)
select why_not_closed, count(*)
from setter_call_reviews r
join close_calls c on c.close_id = r.close_call_id
where r.call_type = 'dc_ads' and r.closed = false
  and c.activity_at >= now() - interval '7 days'
group by 1 order by 2 desc;

-- Likely missed sales (derived, not stored)
select r.close_call_id, r.lead_score, r.intent, r.rep_score
from setter_call_reviews r
where r.call_type = 'dc_ads' and r.closed = false
  and r.lead_score >= 7 and r.intent >= 7 and r.rep_score <= 4;
```
