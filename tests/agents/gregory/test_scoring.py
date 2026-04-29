"""Tests for agents.gregory.scoring.

Pure rubric tests — no DB, no Claude. Cover tier thresholds + the
insufficient-data default.
"""

from __future__ import annotations

from agents.gregory import scoring
from agents.gregory.signals import (
    NEUTRAL_CONTRIBUTION,
    WEIGHT_CALL_CADENCE,
    WEIGHT_OPEN_ACTION_ITEMS,
    WEIGHT_OVERDUE_ACTION_ITEMS,
    WEIGHT_LATEST_NPS,
    Signal,
)


def _signal(name: str, contribution: int, weight: float) -> Signal:
    return Signal(
        name=name,
        weight=weight,
        value=str(contribution),
        contribution=contribution,
        note="test fixture",
    )


# ---------------------------------------------------------------------------
# Tier thresholds
# ---------------------------------------------------------------------------


def test_all_high_signals_tier_green():
    sigs = [
        _signal("call_cadence", 100, WEIGHT_CALL_CADENCE),
        _signal("open_action_items", 100, WEIGHT_OPEN_ACTION_ITEMS),
        _signal("overdue_action_items", 100, WEIGHT_OVERDUE_ACTION_ITEMS),
        _signal("latest_nps", 90, WEIGHT_LATEST_NPS),
    ]

    result = scoring.score_signals(sigs)

    assert result["tier"] == "green"
    assert result["score"] >= 90
    assert result["insufficient_data"] is False


def test_mid_score_lands_yellow():
    sigs = [
        _signal("call_cadence", 50, WEIGHT_CALL_CADENCE),
        _signal("open_action_items", 70, WEIGHT_OPEN_ACTION_ITEMS),
        _signal("overdue_action_items", 70, WEIGHT_OVERDUE_ACTION_ITEMS),
        _signal("latest_nps", 60, WEIGHT_LATEST_NPS),
    ]

    result = scoring.score_signals(sigs)

    assert result["tier"] == "yellow"
    assert 40 <= result["score"] < 70


def test_low_score_lands_red():
    sigs = [
        _signal("call_cadence", 0, WEIGHT_CALL_CADENCE),
        _signal("open_action_items", 30, WEIGHT_OPEN_ACTION_ITEMS),
        _signal("overdue_action_items", 0, WEIGHT_OVERDUE_ACTION_ITEMS),
        _signal("latest_nps", 20, WEIGHT_LATEST_NPS),
    ]

    result = scoring.score_signals(sigs)

    assert result["tier"] == "red"
    assert result["score"] < 40


# ---------------------------------------------------------------------------
# Insufficient-data default
# ---------------------------------------------------------------------------


def test_all_neutral_lands_yellow_50_with_insufficient_flag():
    """The "no data anywhere" case: every signal returned the neutral
    contribution. Brain MUST NOT ship green — yellow with the
    insufficient_data flag set."""
    sigs = [
        _signal("call_cadence", NEUTRAL_CONTRIBUTION, WEIGHT_CALL_CADENCE),
        _signal("open_action_items", NEUTRAL_CONTRIBUTION, WEIGHT_OPEN_ACTION_ITEMS),
        _signal("overdue_action_items", NEUTRAL_CONTRIBUTION, WEIGHT_OVERDUE_ACTION_ITEMS),
        _signal("latest_nps", NEUTRAL_CONTRIBUTION, WEIGHT_LATEST_NPS),
    ]

    result = scoring.score_signals(sigs)

    assert result["tier"] == "yellow"
    assert result["score"] == 50
    assert result["insufficient_data"] is True


def test_one_real_signal_overrides_insufficient_flag():
    """Even one signal with real data takes the brain out of the
    'insufficient data' default — score then follows the rubric."""
    sigs = [
        _signal("call_cadence", 100, WEIGHT_CALL_CADENCE),
        _signal("open_action_items", NEUTRAL_CONTRIBUTION, WEIGHT_OPEN_ACTION_ITEMS),
        _signal("overdue_action_items", NEUTRAL_CONTRIBUTION, WEIGHT_OVERDUE_ACTION_ITEMS),
        _signal("latest_nps", NEUTRAL_CONTRIBUTION, WEIGHT_LATEST_NPS),
    ]

    result = scoring.score_signals(sigs)

    assert result["insufficient_data"] is False


def test_empty_signals_list_lands_yellow_with_flag():
    result = scoring.score_signals([])
    assert result["tier"] == "yellow"
    assert result["insufficient_data"] is True


# ---------------------------------------------------------------------------
# Score boundaries
# ---------------------------------------------------------------------------


def test_score_is_clamped_to_0_to_100():
    sigs = [_signal("call_cadence", 200, WEIGHT_CALL_CADENCE)]
    result = scoring.score_signals(sigs)
    assert 0 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# overall_reasoning
# ---------------------------------------------------------------------------


def test_overall_reasoning_insufficient_data_says_so():
    sigs = [
        _signal("call_cadence", NEUTRAL_CONTRIBUTION, WEIGHT_CALL_CADENCE),
    ]
    result = scoring.score_signals(sigs)
    text = scoring.build_overall_reasoning(sigs, result, concerns_count=0)
    assert "insufficient" in text.lower()


def test_overall_reasoning_includes_signal_breakdown():
    sigs = [
        _signal("call_cadence", 100, WEIGHT_CALL_CADENCE),
        _signal("open_action_items", 80, WEIGHT_OPEN_ACTION_ITEMS),
        _signal("overdue_action_items", 100, WEIGHT_OVERDUE_ACTION_ITEMS),
        _signal("latest_nps", 70, WEIGHT_LATEST_NPS),
    ]
    result = scoring.score_signals(sigs)
    text = scoring.build_overall_reasoning(sigs, result, concerns_count=2)
    # Includes signal names + contributions
    assert "call_cadence=100" in text
    assert "open_action_items=80" in text
    assert "2 qualitative concerns" in text


def test_overall_reasoning_singular_concern():
    sigs = [_signal("call_cadence", 100, WEIGHT_CALL_CADENCE)]
    result = scoring.score_signals(sigs)
    text = scoring.build_overall_reasoning(sigs, result, concerns_count=1)
    assert "1 qualitative concern" in text
    assert "concerns surfaced" not in text  # we want singular form
