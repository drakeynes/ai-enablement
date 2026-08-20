"""Tests for the setter_call_reviewer call-type rubric split (0121 / 0150).

The reviewer grades three rubrics keyed by call_type:
  - outbound → booked / no_book_reason
  - revival  → closed / no_close_reason
  - dc_ads   → closed / no_close_reason + the 0150 signal set

These cover the structural validation that enforces the right outcome
pair per call_type, the dc_ads signal validation + vocab coercion, and
the prompt selection.
"""

from __future__ import annotations

import json

import pytest

from agents.setter_call_reviewer.prompt import (
    BOOK_SYSTEM_PROMPT,
    CLOSE_SYSTEM_PROMPT,
    DC_ADS_SYSTEM_PROMPT,
)
from agents.setter_call_reviewer.reviewer import (
    _OUTCOME_FIELDS,
    _SYSTEM_PROMPTS,
    ReviewError,
    _parse_and_validate,
)

_BASE = {
    "sentiment": "Cool open, warmed mid-call, non-committal close.",
    "lead_score": 7,
    "lead_score_reason": "Qualified with one soft spot.",
    "should_be_dqd": False,
    "dq_reason": None,
    "setter_strengths": [],
    "setter_weaknesses": [],
    "lead_attributes": [],
}


def _payload(**outcome) -> str:
    return json.dumps({**_BASE, **outcome})


# --- outbound rubric -------------------------------------------------------


def test_outbound_accepts_booked_pair():
    parsed = _parse_and_validate(
        _payload(booked=False, no_book_reason="Wanted to talk to spouse."),
        "c1",
        "outbound",
    )
    assert parsed["booked"] is False
    assert parsed["no_book_reason"] == "Wanted to talk to spouse."


def test_outbound_rejects_booked_false_without_reason():
    with pytest.raises(ReviewError, match="no_book_reason"):
        _parse_and_validate(
            _payload(booked=False, no_book_reason=None), "c2", "outbound"
        )


def test_outbound_rejects_revival_outcome_keys():
    # A revival-shaped payload is missing booked/no_book_reason → rejected.
    with pytest.raises(ReviewError, match="missing keys"):
        _parse_and_validate(
            _payload(closed=True, no_close_reason=None), "c3", "outbound"
        )


# --- revival rubric --------------------------------------------------------


def test_revival_accepts_closed_pair():
    parsed = _parse_and_validate(
        _payload(closed=True, no_close_reason=None),
        "c4",
        "revival",
    )
    assert parsed["closed"] is True
    assert parsed["no_close_reason"] is None


def test_revival_rejects_closed_false_without_reason():
    with pytest.raises(ReviewError, match="no_close_reason"):
        _parse_and_validate(
            _payload(closed=False, no_close_reason=None), "c5", "revival"
        )


def test_revival_rejects_booked_outcome_keys():
    # An outbound-shaped payload is missing closed/no_close_reason → rejected.
    with pytest.raises(ReviewError, match="missing keys"):
        _parse_and_validate(_payload(booked=True, no_book_reason=None), "c6", "revival")


# --- dc_ads rubric ---------------------------------------------------------

_DC_SIGNALS = {
    "intent": 6,
    "offer_understanding": 4,
    "rep_score": 7,
    "rep_score_reason": "Clean pitch, soft close ask.",
    "main_objection": "thinks $300 is too much right now",
    "why_not_closed": "cant_pay_today",
    "rep_gap": None,
    "recoverable": True,
    "recoverable_note": "Call back Friday after payday.",
    "voc_quotes": [
        {"quote": "I just want something that finally works", "topic": "goal"}
    ],
    "archetype": "curious_ai_learner",
}


def _dc_payload(**overrides) -> str:
    return json.dumps(
        {
            **_BASE,
            "closed": False,
            "no_close_reason": "Couldn't pay today.",
            **_DC_SIGNALS,
            **overrides,
        }
    )


def test_dc_ads_accepts_full_signal_set():
    parsed = _parse_and_validate(_dc_payload(), "d1", "dc_ads")
    assert parsed["closed"] is False
    assert parsed["why_not_closed"] == "cant_pay_today"
    assert parsed["rep_score"] == 7
    assert parsed["voc_quotes"] == [
        {"quote": "I just want something that finally works", "topic": "goal"}
    ]


def test_dc_ads_rejects_missing_signal_keys():
    payload = json.loads(_dc_payload())
    del payload["rep_score"]
    with pytest.raises(ReviewError, match="missing keys"):
        _parse_and_validate(json.dumps(payload), "d2", "dc_ads")


def test_dc_ads_rejects_out_of_range_scores():
    with pytest.raises(ReviewError, match="intent out of range"):
        _parse_and_validate(_dc_payload(intent=11), "d3", "dc_ads")


def test_dc_ads_coerces_off_vocab_why_not_closed_to_other():
    parsed = _parse_and_validate(
        _dc_payload(why_not_closed="dog_ate_wallet"), "d4", "dc_ads"
    )
    assert parsed["why_not_closed"] == "other"


def test_dc_ads_nulls_why_not_closed_when_closed():
    parsed = _parse_and_validate(
        _dc_payload(closed=True, no_close_reason=None, why_not_closed="low_intent"),
        "d5",
        "dc_ads",
    )
    assert parsed["why_not_closed"] is None


def test_dc_ads_rejects_closed_false_without_why():
    with pytest.raises(ReviewError, match="why_not_closed"):
        _parse_and_validate(_dc_payload(why_not_closed=None), "d6", "dc_ads")


# --- rep_gap (0155, prompt v4) ----------------------------------------------


def test_dc_ads_keeps_rep_gap_on_rep_execution():
    parsed = _parse_and_validate(
        _dc_payload(why_not_closed="rep_execution", rep_gap="no_close_attempt"),
        "g1",
        "dc_ads",
    )
    assert parsed["rep_gap"] == "no_close_attempt"


def test_dc_ads_coerces_missing_or_off_vocab_rep_gap_to_other():
    parsed = _parse_and_validate(
        _dc_payload(why_not_closed="rep_execution", rep_gap=None), "g2", "dc_ads"
    )
    assert parsed["rep_gap"] == "other"
    parsed = _parse_and_validate(
        _dc_payload(why_not_closed="rep_execution", rep_gap="sneezed"), "g3", "dc_ads"
    )
    assert parsed["rep_gap"] == "other"


def test_dc_ads_nulls_rep_gap_off_rep_execution():
    parsed = _parse_and_validate(
        _dc_payload(why_not_closed="cant_pay_today", rep_gap="no_urgency"),
        "g4",
        "dc_ads",
    )
    assert parsed["rep_gap"] is None
    parsed = _parse_and_validate(
        _dc_payload(
            closed=True, no_close_reason=None, why_not_closed=None, rep_gap="no_urgency"
        ),
        "g5",
        "dc_ads",
    )
    assert parsed["rep_gap"] is None


def test_dc_ads_rejects_recoverable_without_note():
    with pytest.raises(ReviewError, match="recoverable_note"):
        _parse_and_validate(_dc_payload(recoverable_note=None), "d7", "dc_ads")


def test_dc_ads_coerces_archetype_and_cleans_voc_quotes():
    parsed = _parse_and_validate(
        _dc_payload(
            archetype="galaxy_brain",
            voc_quotes=[
                {"quote": "  I'm scared of being left behind  ", "topic": "anxiety"},
                {"quote": "", "topic": "goal"},
                "not-a-dict",
            ],
        ),
        "d8",
        "dc_ads",
    )
    assert parsed["archetype"] == "other"
    assert parsed["voc_quotes"] == [
        {"quote": "I'm scared of being left behind", "topic": "other"}
    ]


def test_outbound_ignores_dc_signal_requirements():
    # The base rubrics never require the 0150 keys.
    parsed = _parse_and_validate(
        _payload(booked=True, no_book_reason=None), "d9", "outbound"
    )
    assert "intent" not in parsed


# --- wiring ----------------------------------------------------------------


def test_outcome_fields_and_prompts_paired():
    assert _OUTCOME_FIELDS["outbound"] == ("booked", "no_book_reason")
    assert _OUTCOME_FIELDS["revival"] == ("closed", "no_close_reason")
    assert _OUTCOME_FIELDS["dc_ads"] == ("closed", "no_close_reason")
    assert _SYSTEM_PROMPTS["outbound"] is BOOK_SYSTEM_PROMPT
    assert _SYSTEM_PROMPTS["revival"] is CLOSE_SYSTEM_PROMPT
    assert _SYSTEM_PROMPTS["dc_ads"] is DC_ADS_SYSTEM_PROMPT


def test_dc_ads_prompt_carries_signal_contract():
    for needle in (
        '"intent"',
        '"offer_understanding"',
        '"rep_score"',
        '"why_not_closed"',
        '"rep_gap"',
        '"recoverable"',
        '"voc_quotes"',
        '"archetype"',
        "didnt_understand_offer",
        "price_platform_objection",
        "broke_opportunity_seeker",
        "gave_up_at_objection",
        "deferred_to_followup",
    ):
        assert needle in DC_ADS_SYSTEM_PROMPT, needle
    # The base rubrics must NOT leak the dc_ads signal vocabulary.
    assert '"intent"' not in BOOK_SYSTEM_PROMPT
    assert '"intent"' not in CLOSE_SYSTEM_PROMPT


def test_close_prompt_targets_phone_close_not_booking():
    assert '"closed"' in CLOSE_SYSTEM_PROMPT
    assert "no_close_reason" in CLOSE_SYSTEM_PROMPT
    assert "Digital College" in CLOSE_SYSTEM_PROMPT
    # The book rubric must NOT leak the close vocabulary, and vice-versa.
    assert '"closed"' not in BOOK_SYSTEM_PROMPT
    assert '"booked"' in BOOK_SYSTEM_PROMPT
