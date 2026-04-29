"""Gregory brain — scoring rubric.

Combines per-signal contributions into a 0-100 health score and a
green/yellow/red tier.

Rubric:
  final_score = sum(signal.weight * signal.contribution) over all signals,
                clamped to 0-100 and rounded to int.

  Each signal's contribution is its own 0-100 internal score (see
  signals.py band logic). Weights live in signals.py as constants and
  must sum to ~1.0 across all signals; if a future signal is added,
  re-balance the weights there.

Tier thresholds:
  >=70 → green
  40-69 → yellow
  <40  → red

These thresholds are V1.1 starting points. Iterate as the dashboard
reveals miscalibration. The IMPORTANT property is that the math is
fully transparent in factors.signals[] — a reviewer reading the "Why
this score" expand can recompute the score by hand.

Insufficient-data default:
  When every signal contributes the neutral 50 (every signal returned
  "no data, neutral"), score lands at 50 and tier is yellow regardless
  of the threshold table. The brain never ships a client at green
  by accident on no data; overall_reasoning explicitly flags it.
"""

from __future__ import annotations

from typing import TypedDict

from agents.gregory.signals import NEUTRAL_CONTRIBUTION, Signal

# Tier thresholds (inclusive lower bounds).
TIER_GREEN_MIN = 70
TIER_YELLOW_MIN = 40


class ScoringResult(TypedDict):
    score: int
    tier: str
    insufficient_data: bool


def score_signals(signals: list[Signal]) -> ScoringResult:
    """Roll signal contributions into a final score + tier.

    Returns:
        score: 0-100 integer.
        tier: 'green' | 'yellow' | 'red'.
        insufficient_data: True iff every signal returned the neutral
            contribution (i.e. no real data anywhere). Score ignores
            tier thresholds in this case and lands at yellow.
    """
    if not signals:
        return ScoringResult(score=NEUTRAL_CONTRIBUTION, tier="yellow", insufficient_data=True)

    total_weight = sum(signal["weight"] for signal in signals)
    if total_weight == 0:
        return ScoringResult(score=NEUTRAL_CONTRIBUTION, tier="yellow", insufficient_data=True)

    weighted = sum(
        signal["weight"] * signal["contribution"] for signal in signals
    )
    raw_score = weighted / total_weight
    score = max(0, min(100, round(raw_score)))

    # Insufficient-data check: every contribution equals the neutral
    # value. If even one signal returned a real number (good or bad),
    # we're not in the insufficient-data case.
    insufficient = all(
        signal["contribution"] == NEUTRAL_CONTRIBUTION for signal in signals
    )

    if insufficient:
        return ScoringResult(score=NEUTRAL_CONTRIBUTION, tier="yellow", insufficient_data=True)

    if score >= TIER_GREEN_MIN:
        tier = "green"
    elif score >= TIER_YELLOW_MIN:
        tier = "yellow"
    else:
        tier = "red"

    return ScoringResult(score=score, tier=tier, insufficient_data=False)


def build_overall_reasoning(
    signals: list[Signal],
    scoring: ScoringResult,
    concerns_count: int,
) -> str:
    """One-sentence narrative explanation that lands in
    factors.overall_reasoning. The dashboard renders it next to the
    raw factors JSON; reviewers read this when they want a quick
    "why" without scanning the breakdown.
    """
    if scoring["insufficient_data"]:
        return (
            "Insufficient signal data; defaulting to yellow. "
            "Score will get more meaningful once NPS submissions and Slack "
            "engagement signals land."
        )

    band = (
        "healthy"
        if scoring["tier"] == "green"
        else "watch closely" if scoring["tier"] == "yellow"
        else "intervention warranted"
    )
    notes = "; ".join(
        f"{signal['name']}={signal['contribution']}" for signal in signals
    )
    suffix = (
        f" {concerns_count} qualitative concern{'s' if concerns_count != 1 else ''} surfaced."
        if concerns_count
        else ""
    )
    return f"Score {scoring['score']} ({band}). Signal breakdown: {notes}.{suffix}"
