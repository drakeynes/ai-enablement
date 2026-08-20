"""End-to-end orchestration for setter-call Sonnet review.

Public entry point: `review_call(close_call_id)`. It:

  1. Loads the transcript + diarized words from setter_call_transcripts.
  2. Sends the transcript to Sonnet 4.6 with the v1 prompt.
  3. Parses + validates the JSON response.
  4. Computes talk-time from the words array.
  5. Upserts everything to setter_call_reviews.

Idempotent on close_call_id. By default we skip re-reviewing rows
that already exist (a re-run with `force=True` overrides — useful
after a prompt iteration).

Cost telemetry: input/output tokens + USD cost are persisted directly
on the row. Does NOT write to agent_runs — sales LLM spend stays
self-contained inside the sales-dashboard.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agents.setter_call_reviewer.prompt import (
    BOOK_SYSTEM_PROMPT,
    CLOSE_SYSTEM_PROMPT,
    DC_ADS_SYSTEM_PROMPT,
    PROMPT_VERSION,
)
from agents.setter_call_reviewer.slack_post import post_review_to_slack
from agents.setter_call_reviewer.talk_time import compute_talk_time
from shared.claude_client import DEFAULT_MODEL, complete

# "DC Revival Lead" Close custom field — the canonical revival-campaign marker
# (the re-engagement SMS auto-creates these leads and stamps this CF). A call to
# a revival lead is a Digital College reactivation: the rep closes on the phone,
# so it's graded on the close rubric, not the book rubric. Keep in sync with
# shared.lead_tagging.REVIVAL_CF and lib/db/funnel-appointment-setting.ts.
#
# NOTE: this replaced an opt-in-date proxy (latest_opt_in_date < a horizon),
# which silently missed the bulk of revival leads — SMS-created ones often have
# NO opt-in date at all, so the proxy graded them outbound (Drake 2026-06-30).
REVIVAL_CF = "cf_QivXkWBvr34UIDkUBKXNCQo6woarc62wEbIacWWbN7P"
from shared.db import get_client

logger = logging.getLogger("ai_enablement.setter_call_reviewer")

# Sonnet's output ceiling for this review. v1 prompt outputs ~500-800
# tokens typically; 2048 leaves headroom for chatty calls without
# inviting model verbosity.
_MAX_OUTPUT_TOKENS = 2048

# Keys common to both rubrics. The outcome pair is appended per call_type:
# outbound → booked/no_book_reason, revival → closed/no_close_reason.
_BASE_REQUIRED_KEYS = frozenset(
    {
        "sentiment",
        "lead_score",
        "lead_score_reason",
        "should_be_dqd",
        "dq_reason",
        "setter_strengths",
        "setter_weaknesses",
        "lead_attributes",
    }
)

# Per-call-type outcome contract: (boolean field, reason field, system prompt).
_OUTCOME_FIELDS = {
    "outbound": ("booked", "no_book_reason"),
    "revival": ("closed", "no_close_reason"),
    "dc_ads": ("closed", "no_close_reason"),
}
_SYSTEM_PROMPTS = {
    "outbound": BOOK_SYSTEM_PROMPT,
    "revival": CLOSE_SYSTEM_PROMPT,
    "dc_ads": DC_ADS_SYSTEM_PROMPT,
}

# The dc_ads rubric's extra signal keys (migration 0150). All required in
# the model output; vocab fields are coerced (not rejected) off-vocab.
_DC_ADS_EXTRA_KEYS = frozenset(
    {
        "intent",
        "offer_understanding",
        "rep_score",
        "rep_score_reason",
        "main_objection",
        "why_not_closed",
        "rep_gap",
        "recoverable",
        "recoverable_note",
        "voc_quotes",
        "archetype",
    }
)

# Fixed vocabularies — keep in sync with migration 0150's CHECKs. Off-vocab
# model output coerces to 'other' (structural fix: never fail a review over
# a label the CHECK would reject anyway).
_WHY_NOT_CLOSED_VOCAB = frozenset(
    {
        "didnt_understand_offer",
        "low_intent",
        "price_platform_objection",
        "rep_execution",
        "bad_timing",
        "skepticism",
        "cant_pay_today",
        "spouse_partner",
        "other",
    }
)
# rep_gap (0155, prompt v4): the specific gap inside a rep_execution loss.
_REP_GAP_VOCAB = frozenset(
    {
        "no_close_attempt",
        "gave_up_at_objection",
        "no_urgency",
        "weak_discovery",
        "offer_not_explained",
        "talked_over_lead",
        "deferred_to_followup",
        "other",
    }
)
_ARCHETYPE_VOCAB = frozenset(
    {
        "high_intent_entrepreneur",
        "curious_ai_learner",
        "broke_opportunity_seeker",
        "skeptic",
        "existing_business_owner",
        "other",
    }
)
_VOC_TOPIC_VOCAB = frozenset({"goal", "fear", "objection", "why_applied", "other"})
_MAX_VOC_QUOTES = 4


class ReviewError(RuntimeError):
    """Raised when the reviewer can't produce a valid review.

    Cases: transcript missing, Sonnet returned non-JSON, JSON
    structurally invalid, required key missing, value out of range.
    The caller decides whether to retry, skip, or surface.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def review_call(
    close_call_id: str,
    *,
    db: Any | None = None,
    force: bool = False,
    post_to_slack: bool = True,
) -> dict[str, Any]:
    """Review one transcript end-to-end. Returns the upserted review row.

    When `post_to_slack=True` (the default), a Slack message is posted
    to the sales-reviews channel on first review. Re-runs skip the
    post if `slack_message_ts` is already set. Pass `False` to suppress
    Slack entirely (used for the initial backfill of 55 historical
    calls — we don't want to spam the channel with old reviews).
    """
    db = db or get_client()

    if not force:
        existing = _load_existing_review(db, close_call_id)
        if existing:
            logger.info(
                "setter_review.skip_existing close_call_id=%s",
                close_call_id,
            )
            # Existing row — Slack may or may not have posted before.
            # post_review_to_slack is itself idempotent on
            # slack_message_ts, so safe to call. Only call when the
            # caller opts in.
            if post_to_slack:
                _maybe_post_to_slack(db, close_call_id, existing)
            return existing

    transcript_row = _load_transcript(db, close_call_id)
    if not transcript_row:
        raise ReviewError(
            f"no transcript found for {close_call_id} — run transcribe_call first"
        )

    transcript_text = transcript_row["transcript_text"]
    words = transcript_row.get("words") or []

    # Pick the rubric BEFORE the Sonnet call. Precedence: the REVIVAL_CF
    # marker (explicit revival-campaign lead) → dc_ads_lead_facts membership
    # (the DC paid-ads cohort — graded close-on-phone + the 0150 signal set)
    # → outbound book-a-closer. The call_type also drives which outcome
    # columns we write.
    call_type = _resolve_call_type(db, close_call_id)
    bool_key, reason_key = _OUTCOME_FIELDS[call_type]

    logger.info(
        "setter_review.sonnet_request close_call_id=%s call_type=%s transcript_chars=%d words=%d",
        close_call_id,
        call_type,
        len(transcript_text),
        len(words),
    )

    result = complete(
        system=_SYSTEM_PROMPTS[call_type],
        messages=[{"role": "user", "content": transcript_text}],
        model=DEFAULT_MODEL,
        max_tokens=_MAX_OUTPUT_TOKENS,
        # No run_id — sales pipeline does NOT write to agent_runs.
        run_id=None,
    )

    review = _parse_and_validate(result.text, close_call_id, call_type)
    setter_words, prospect_words, talk_ratio = compute_talk_time(words)

    # Write BOTH outcome pairs every time: the active call_type's pair from
    # the review, and the inactive pair explicitly nulled. The explicit nulls
    # matter on a re-grade that flips call_type (e.g. backfilling an existing
    # outbound row to revival) — the upsert UPDATE only touches columns we
    # send, so without these the prior rubric's outcome would linger.
    outcome_cols = {
        "booked": None,
        "no_book_reason": None,
        "closed": None,
        "no_close_reason": None,
    }
    outcome_cols[bool_key] = review[bool_key]
    outcome_cols[reason_key] = review[reason_key]

    # The dc_ads signal set (0150) — explicitly nulled for the other call
    # types for the same re-grade reason as outcome_cols (a flip away from
    # dc_ads must clear the stale signals).
    signal_cols: dict[str, Any] = {key: None for key in _DC_ADS_EXTRA_KEYS}
    signal_cols["voc_quotes"] = []  # column is NOT NULL DEFAULT '[]'
    if call_type == "dc_ads":
        for key in _DC_ADS_EXTRA_KEYS:
            signal_cols[key] = review[key]

    row = {
        "close_call_id": close_call_id,
        "call_type": call_type,
        "sentiment": review["sentiment"],
        "lead_score": review["lead_score"],
        "lead_score_reason": review["lead_score_reason"],
        "should_be_dqd": review["should_be_dqd"],
        "dq_reason": review["dq_reason"],
        **outcome_cols,
        **signal_cols,
        "setter_strengths": review["setter_strengths"],
        "setter_weaknesses": review["setter_weaknesses"],
        "lead_attributes": review["lead_attributes"],
        "setter_words": setter_words,
        "prospect_words": prospect_words,
        "talk_ratio_setter": talk_ratio,
        "model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "sonnet_input_tokens": result.input_tokens,
        "sonnet_output_tokens": result.output_tokens,
        "sonnet_cost_usd": float(result.cost_usd),
    }
    persisted = _upsert(db, row)

    if post_to_slack:
        _maybe_post_to_slack(db, close_call_id, persisted)

    return persisted


def _maybe_post_to_slack(
    db: Any,
    close_call_id: str,
    review_row: dict[str, Any],
) -> None:
    """Resolve setter / prospect context, then hand off to the Slack
    poster. Fail-soft: Slack failures never break the review.

    The context lookup (close_calls + team_members + close_leads) is
    deliberately separate from the persisted review row to keep the
    review table free of denormalized humanized labels — those would
    rot when team_members rows are renamed or merged.
    """
    try:
        ctx = _load_slack_context(db, close_call_id)
        # call_type on the persisted row is authoritative for the type
        # badge / close-vs-book outcome line (call_type is NOT NULL on every
        # row since migration 0121).
        post_review_to_slack(
            db,
            close_call_id=close_call_id,
            review_row=review_row,
            setter_name=ctx["setter_name"],
            prospect_name=ctx["prospect_name"],
            duration_s=ctx["duration_s"],
            direction=ctx["direction"],
            call_type=review_row.get("call_type") or "outbound",
        )
    except Exception as exc:
        # Defensive — post_review_to_slack already swallows Slack
        # transport errors; this catches anything in the context
        # resolution that went sideways.
        logger.warning(
            "setter_review.slack_context_failed close_call_id=%s err=%s",
            close_call_id,
            exc,
        )


def _resolve_call_type(db: Any, close_call_id: str) -> str:
    """Pick the rubric for this call from its lead. One lead-chain lookup.

    Precedence:
      1. revival — the lead carries the REVIVAL_CF "DC Revival Lead"
         custom field (non-empty), matching the canonical revival
         predicate the tagger and the /outbound funnel use.
      2. dc_ads  — the lead is a member of dc_ads_lead_facts (the DC
         paid-ads cohort, same membership the DC Ads dashboard reads,
         refreshed every 15 min — a fresh opt-in lands there before its
         first ≥90s call finishes transcribing).
      3. outbound — everything else. Fail-safe default: any lookup miss
         grades on the book rubric.
    """
    call_resp = (
        db.table("close_calls")
        .select("lead_id")
        .eq("close_id", close_call_id)
        .maybe_single()
        .execute()
    )
    lead_id = (call_resp.data or {}).get("lead_id") if call_resp else None
    if not lead_id:
        return "outbound"

    ld_resp = (
        db.table("close_leads")
        .select("custom_fields_raw")
        .eq("close_id", lead_id)
        .maybe_single()
        .execute()
    )
    cf = (ld_resp.data or {}).get("custom_fields_raw") if ld_resp else None
    if (cf or {}).get(REVIVAL_CF):
        return "revival"

    facts_resp = (
        db.table("dc_ads_lead_facts")
        .select("close_id")
        .eq("close_id", lead_id)
        .maybe_single()
        .execute()
    )
    if facts_resp and facts_resp.data:
        return "dc_ads"

    return "outbound"


def _load_slack_context(db: Any, close_call_id: str) -> dict[str, Any]:
    """Pull setter name, prospect name, duration, direction in 3 cheap
    round trips. Returns nullable strings when joins are unresolved.
    """
    # close_calls — the source of duration, direction, user_id, lead_id
    call_resp = (
        db.table("close_calls")
        .select("user_id, lead_id, duration, direction")
        .eq("close_id", close_call_id)
        .maybe_single()
        .execute()
    )
    call = (call_resp.data or {}) if call_resp else {}

    setter_name: str | None = None
    if call.get("user_id"):
        tm_resp = (
            db.table("team_members")
            .select("full_name")
            .eq("close_user_id", call["user_id"])
            .maybe_single()
            .execute()
        )
        if tm_resp and tm_resp.data:
            setter_name = tm_resp.data.get("full_name")

    # Fallback: a rep not in team_members yet (e.g. a brand-new hire before the
    # daily close_users sync / manual add) would otherwise post as "Unknown
    # setter". Resolve the real name straight from Close so the review never
    # shows "Unknown setter". Best-effort — on any failure we keep None and the
    # post falls back to the generic label.
    if setter_name is None and call.get("user_id"):
        try:
            from ingestion.close.client import CloseClient

            u = CloseClient.from_env().get_user(call["user_id"])
            nm = " ".join(
                p
                for p in [
                    (u.get("first_name") or "").strip(),
                    (u.get("last_name") or "").strip(),
                ]
                if p
            ).strip()
            setter_name = nm or None
        except (
            Exception
        ) as exc:  # noqa: BLE001 — display fallback, never fail the review
            logger.warning(
                "setter_review.close_name_fallback_failed user_id=%s err=%s",
                call.get("user_id"),
                exc,
            )

    prospect_name: str | None = None
    if call.get("lead_id"):
        ld_resp = (
            db.table("close_leads")
            .select("display_name")
            .eq("close_id", call["lead_id"])
            .maybe_single()
            .execute()
        )
        if ld_resp and ld_resp.data:
            prospect_name = ld_resp.data.get("display_name")

    # is_revival is NOT recomputed here — the caller reads call_type off the
    # persisted review row (the authoritative rubric decision).
    return {
        "setter_name": setter_name,
        "prospect_name": prospect_name,
        "duration_s": call.get("duration"),
        "direction": call.get("direction"),
    }


def find_pending_reviews(
    db: Any | None = None,
    *,
    limit: int | None = None,
) -> list[str]:
    """Return close_call_ids that have a transcript but no review yet.

    NOT-EXISTS-style query: pull every transcript_id, exclude any that
    already have a review. Cheap at current volume (~55 rows). Add a
    SQL view if this ever scales past low thousands.
    """
    db = db or get_client()

    trx = (
        db.table("setter_call_transcripts")
        .select("close_call_id")
        .order("transcribed_at", desc=False)
        .execute()
    )
    candidates = [r["close_call_id"] for r in (trx.data or [])]
    if not candidates:
        return []

    done = (
        db.table("setter_call_reviews")
        .select("close_call_id")
        .in_("close_call_id", candidates)
        .execute()
    )
    done_ids = {r["close_call_id"] for r in (done.data or [])}
    pending = [c for c in candidates if c not in done_ids]
    if limit is not None:
        pending = pending[:limit]
    return pending


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _load_transcript(db: Any, close_call_id: str) -> dict[str, Any] | None:
    resp = (
        db.table("setter_call_transcripts")
        .select("close_call_id, transcript_text, words")
        .eq("close_call_id", close_call_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp and resp.data else None


def _load_existing_review(db: Any, close_call_id: str) -> dict[str, Any] | None:
    resp = (
        db.table("setter_call_reviews")
        .select("*")
        .eq("close_call_id", close_call_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


def _parse_and_validate(
    text: str, close_call_id: str, call_type: str
) -> dict[str, Any]:
    """Pull JSON out of the model response and structurally validate it.

    Sonnet occasionally wraps responses in markdown fences despite the
    prompt forbidding them. Strip those before parsing. After that the
    response must be a JSON object with all required keys and value
    types matching the prompt spec. The outcome pair required depends on
    call_type: outbound → booked/no_book_reason, revival → closed/
    no_close_reason.
    """
    bool_key, reason_key = _OUTCOME_FIELDS[call_type]
    required_keys = _BASE_REQUIRED_KEYS | {bool_key, reason_key}
    if call_type == "dc_ads":
        required_keys = required_keys | _DC_ADS_EXTRA_KEYS

    candidate = _strip_fences(text).strip()
    if not candidate:
        raise ReviewError(f"empty response from Sonnet for {close_call_id}")

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ReviewError(
            f"non-JSON response for {close_call_id}: {exc}; "
            f"first 200 chars: {candidate[:200]!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ReviewError(
            f"response for {close_call_id} not a JSON object: {type(parsed).__name__}"
        )

    missing = required_keys - set(parsed.keys())
    if missing:
        raise ReviewError(
            f"response for {close_call_id} missing keys: {sorted(missing)}"
        )

    # Type / range checks. These mirror the prompt contract; if any
    # fails we treat the whole review as failed rather than persisting
    # half-bad data and surfacing it as truth.
    if not isinstance(parsed["lead_score"], int) or not 0 <= parsed["lead_score"] <= 10:
        raise ReviewError(
            f"lead_score out of range for {close_call_id}: {parsed['lead_score']!r}"
        )
    if not isinstance(parsed["should_be_dqd"], bool):
        raise ReviewError(
            f"should_be_dqd not bool for {close_call_id}: {parsed['should_be_dqd']!r}"
        )
    if parsed["should_be_dqd"] and not parsed.get("dq_reason"):
        # The model violated the "always provide reason when true" rule.
        # We could let the DB CHECK fail, but a clearer error here helps
        # the caller decide (retry vs. give up).
        raise ReviewError(f"should_be_dqd=true but no dq_reason for {close_call_id}")
    if not isinstance(parsed[bool_key], bool):
        raise ReviewError(
            f"{bool_key} not bool for {close_call_id}: {parsed[bool_key]!r}"
        )
    if parsed[bool_key] is False and not parsed.get(reason_key):
        raise ReviewError(f"{bool_key}=false but no {reason_key} for {close_call_id}")
    for arr_key in ("setter_strengths", "setter_weaknesses"):
        if not isinstance(parsed[arr_key], list):
            raise ReviewError(
                f"{arr_key} not list for {close_call_id}: "
                f"{type(parsed[arr_key]).__name__}"
            )
        # 0-2 items per Drake. We hard-cap at the persistence layer
        # rather than retry — if the model returns 3, slice to 2
        # rather than reject (the first two are usually the strongest).
        if len(parsed[arr_key]) > 2:
            logger.warning(
                "setter_review.over_cap close_call_id=%s key=%s len=%d (truncating to 2)",
                close_call_id,
                arr_key,
                len(parsed[arr_key]),
            )
            parsed[arr_key] = parsed[arr_key][:2]
    if not isinstance(parsed["lead_attributes"], list):
        raise ReviewError(
            f"lead_attributes not list for {close_call_id}: "
            f"{type(parsed['lead_attributes']).__name__}"
        )

    if call_type == "dc_ads":
        _validate_dc_ads_signals(parsed, close_call_id)

    return parsed


def _validate_dc_ads_signals(parsed: dict[str, Any], close_call_id: str) -> None:
    """Validate + normalize the dc_ads signal set IN PLACE.

    Range violations and shape violations fail the review (same bar as
    the base fields). Vocabulary violations COERCE to 'other' with a
    warning instead — the fixed vocab exists so aggregation stays
    stable, and 'other' is the vocab's own catch-all; failing an
    otherwise-good review over a label would trade a whole row for one
    field. (Structural-fix principle, migration 0150.)
    """
    for score_key in ("intent", "offer_understanding", "rep_score"):
        if not isinstance(parsed[score_key], int) or not 0 <= parsed[score_key] <= 10:
            raise ReviewError(
                f"{score_key} out of range for {close_call_id}: {parsed[score_key]!r}"
            )
    if not parsed.get("rep_score_reason"):
        raise ReviewError(f"missing rep_score_reason for {close_call_id}")

    if not isinstance(parsed["recoverable"], bool):
        raise ReviewError(
            f"recoverable not bool for {close_call_id}: {parsed['recoverable']!r}"
        )
    if parsed["recoverable"] and not parsed.get("recoverable_note"):
        raise ReviewError(
            f"recoverable=true but no recoverable_note for {close_call_id}"
        )

    # why_not_closed: required iff the call didn't close (the model gets
    # this right structurally; the closed=false case is the one to guard).
    if parsed.get("closed") is False:
        wnc = parsed.get("why_not_closed")
        if not wnc:
            raise ReviewError(f"closed=false but no why_not_closed for {close_call_id}")
        if wnc not in _WHY_NOT_CLOSED_VOCAB:
            logger.warning(
                "setter_review.off_vocab close_call_id=%s key=why_not_closed value=%r (coercing to other)",
                close_call_id,
                wnc,
            )
            parsed["why_not_closed"] = "other"
    else:
        parsed["why_not_closed"] = None

    # rep_gap (0155, v4): required exactly when the loss was rep_execution
    # (read POST-coercion), forced null on every other outcome. Missing or
    # off-vocab coerces to 'other' — same trade as the parent vocab: never
    # fail a whole review over one label.
    if parsed.get("why_not_closed") == "rep_execution":
        if parsed.get("rep_gap") not in _REP_GAP_VOCAB:
            logger.warning(
                "setter_review.off_vocab close_call_id=%s key=rep_gap value=%r (coercing to other)",
                close_call_id,
                parsed.get("rep_gap"),
            )
            parsed["rep_gap"] = "other"
    else:
        parsed["rep_gap"] = None

    if parsed.get("archetype") not in _ARCHETYPE_VOCAB:
        logger.warning(
            "setter_review.off_vocab close_call_id=%s key=archetype value=%r (coercing to other)",
            close_call_id,
            parsed.get("archetype"),
        )
        parsed["archetype"] = "other"

    quotes = parsed.get("voc_quotes")
    if not isinstance(quotes, list):
        raise ReviewError(
            f"voc_quotes not list for {close_call_id}: {type(quotes).__name__}"
        )
    cleaned: list[dict[str, str]] = []
    for item in quotes[:_MAX_VOC_QUOTES]:
        if not isinstance(item, dict) or not (item.get("quote") or "").strip():
            logger.warning(
                "setter_review.voc_quote_dropped close_call_id=%s item=%r",
                close_call_id,
                item,
            )
            continue
        topic = item.get("topic")
        if topic not in _VOC_TOPIC_VOCAB:
            topic = "other"
        cleaned.append({"quote": str(item["quote"]).strip(), "topic": topic})
    if len(quotes) > _MAX_VOC_QUOTES:
        logger.warning(
            "setter_review.over_cap close_call_id=%s key=voc_quotes len=%d (truncating to %d)",
            close_call_id,
            len(quotes),
            _MAX_VOC_QUOTES,
        )
    parsed["voc_quotes"] = cleaned


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text)


def _upsert(db: Any, row: dict[str, Any]) -> dict[str, Any]:
    resp = (
        db.table("setter_call_reviews")
        .upsert(row, on_conflict="close_call_id", returning="representation")
        .execute()
    )
    if not resp.data:
        raise ReviewError(
            f"setter_call_reviews upsert returned no row for {row['close_call_id']}"
        )
    # Outcome label is call_type-dependent (booked for outbound, closed for
    # revival/dc_ads); log whichever pair the active call_type carries.
    outcome = (
        row.get("closed")
        if row.get("call_type") in ("revival", "dc_ads")
        else row.get("booked")
    )
    logger.info(
        "setter_review.persisted close_call_id=%s call_type=%s score=%s dq=%s outcome=%s cost=$%s",
        row["close_call_id"],
        row.get("call_type"),
        row["lead_score"],
        row["should_be_dqd"],
        outcome,
        row["sonnet_cost_usd"],
    )
    return resp.data[0]
