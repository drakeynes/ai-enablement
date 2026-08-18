-- 0150 — the dc_ads review rubric: new call_type + Nabeel's signal columns.
--
-- Context (Nabeel 2026-08-18): the DC Ads dashboard grows an AI call-review
-- layer — connected-call feed, AI lead-quality columns on the daily/ad
-- tables, rep scores, why-not-closing aggregation, exec summary. The
-- reviewer pipeline (0053/0054/0121) already transcribes + reviews every
-- ≥90s recorded call, but DC **ads** leads don't carry the "DC Revival
-- Lead" CF, so their calls were graded on the outbound BOOK rubric — the
-- wrong question for a close-on-the-phone motion. This migration gives the
-- ads motion its own rubric row shape:
--
--   call_type 'dc_ads' — detected by dc_ads_lead_facts membership (the
--   cohort predicate), graded on closed/no_close_reason like revival, PLUS
--   the ad-intelligence signals below. Forward-only by decision (Drake
--   2026-08-18): existing wrong-rubric rows stay until Nabeel verifies the
--   new output; the dashboard reads call_type='dc_ads' rows ONLY, so the
--   old reviews never surface there. Backfill = re-review with force=True
--   (transcripts are stored; ~$0.02/call) — a later decision.
--
-- All new columns are nullable: only dc_ads rows carry them, enforced by
-- the dc_ads signals CHECK. Vocabularies are fixed lists (the structural-
-- fix principle: the reviewer coerces off-vocab values to 'other' rather
-- than prompt-iterating); new entries arrive via migration, not model
-- invention. Missed-sales / great-saves flags are deliberately NOT columns
-- — they derive in SQL from (lead_score, intent, rep_score, closed) so the
-- thresholds stay tunable without re-reviewing.

alter table setter_call_reviews
  -- Prospect signals (0-10 like lead_score)
  add column intent smallint
    check (intent between 0 and 10),
  add column offer_understanding smallint
    check (offer_understanding between 0 and 10),
  -- Rep execution (the lead_score twin on the rep side — same
  -- quality-vs-execution split rule from 0054)
  add column rep_score smallint
    check (rep_score between 0 and 10),
  add column rep_score_reason text,
  -- The single biggest objection voiced (short free text; null = none)
  add column main_objection text,
  -- Why the call didn't close — fixed vocabulary, Nabeel's mock 2026-08-18.
  -- null when closed=true (or non-dc_ads rows).
  add column why_not_closed text
    check (why_not_closed in (
      'didnt_understand_offer', 'low_intent', 'price_platform_objection',
      'rep_execution', 'bad_timing', 'skepticism', 'cant_pay_today',
      'spouse_partner', 'other')),
  -- Could a follow-up still realistically close this lead?
  add column recoverable boolean,
  add column recoverable_note text,
  -- Voice-of-customer: verbatim prospect quotes for marketing mining.
  -- jsonb array of {quote, topic}, topic in goal|fear|objection|why_applied|other.
  add column voc_quotes jsonb not null default '[]'::jsonb,
  -- Lead archetype — Nabeel's five types + other.
  add column archetype text
    check (archetype in (
      'high_intent_entrepreneur', 'curious_ai_learner',
      'broke_opportunity_seeker', 'skeptic', 'existing_business_owner',
      'other'));

-- call_type gains 'dc_ads' (0121's inline check auto-named by Postgres).
alter table setter_call_reviews
  drop constraint setter_call_reviews_call_type_check;
alter table setter_call_reviews
  add constraint setter_call_reviews_call_type_check
    check (call_type in ('outbound', 'revival', 'dc_ads'));

-- dc_ads uses the close outcome pair, same as revival.
alter table setter_call_reviews
  drop constraint setter_call_reviews_outcome_check;
alter table setter_call_reviews
  add constraint setter_call_reviews_outcome_check check (
    (call_type = 'outbound'
       and booked is not null
       and (booked = true or no_book_reason is not null))
    or
    (call_type in ('revival', 'dc_ads')
       and closed is not null
       and (closed = true or no_close_reason is not null))
  );

-- A dc_ads row must carry the full signal set (the reviewer validates
-- before insert; this is the DB-level backstop). why_not_closed is
-- required exactly when the call didn't close.
alter table setter_call_reviews
  add constraint setter_call_reviews_dc_signals_check check (
    call_type <> 'dc_ads'
    or (intent is not null
        and offer_understanding is not null
        and rep_score is not null
        and rep_score_reason is not null
        and recoverable is not null
        and archetype is not null
        and (closed = true or why_not_closed is not null))
  );

-- The dashboard reads are always call_type='dc_ads' scans over a window.
create index setter_call_reviews_dc_ads_idx
  on setter_call_reviews (reviewed_at desc)
  where call_type = 'dc_ads';

comment on column setter_call_reviews.intent is
  'dc_ads rubric only: prospect BUYING INTENT on this call, 0-10 (desire to enroll, independent of ability to pay). null on other call types.';
comment on column setter_call_reviews.offer_understanding is
  'dc_ads rubric only: how well the prospect understood what Digital College IS by call end, 0-10. Low values across an ad''s cohort = the ad/LP set wrong expectations.';
comment on column setter_call_reviews.rep_score is
  'dc_ads rubric only: rep EXECUTION on this call, 0-10 — discovery, pitch clarity, objection handling, close attempts. NOT lead quality (that''s lead_score; the 0054 split rule applies).';
comment on column setter_call_reviews.why_not_closed is
  'dc_ads rubric, closed=false only: THE primary reason, one of the fixed vocabulary (Nabeel''s mock 2026-08-18). Powers the "Why aren''t DC leads closing?" block. Reviewer coerces off-vocab model output to ''other''.';
comment on column setter_call_reviews.recoverable is
  'dc_ads rubric only: could a follow-up still realistically close this lead? Advisory, drives the recoverable filter on the calls feed.';
comment on column setter_call_reviews.voc_quotes is
  'dc_ads rubric: verbatim prospect quotes for marketing mining — [{quote, topic}], topic in goal|fear|objection|why_applied|other. Exact words only, 0-4 per call.';
comment on column setter_call_reviews.archetype is
  'dc_ads rubric only: the prospect archetype (Nabeel''s five types + other). Aggregated per ad/campaign to see which ads attract which archetypes and which close.';
