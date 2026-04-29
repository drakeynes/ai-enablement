"""Tests for agents.gregory.concerns.

Covers:
  - Flag-off short-circuit (default V1.1 behavior)
  - Empty-input short-circuit (no summaries + no action items → no Claude call)
  - JSON parse for clean output
  - JSON parse for markdown-fenced output (defensive)
  - Malformed output → empty list (degrade gracefully)
  - Filter on severity / source_call_ids shape
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from agents.gregory import concerns


# ---------------------------------------------------------------------------
# _parse_concerns_response — pure parser tests
# ---------------------------------------------------------------------------


def test_parse_clean_json_returns_concerns():
    payload = json.dumps(
        {
            "concerns": [
                {
                    "text": "Doubt mentioned in last 2 calls",
                    "severity": "high",
                    "source_call_ids": ["call-1", "call-2"],
                }
            ]
        }
    )

    result = concerns._parse_concerns_response(payload)

    assert len(result) == 1
    assert result[0]["text"] == "Doubt mentioned in last 2 calls"
    assert result[0]["severity"] == "high"
    assert result[0]["source_call_ids"] == ["call-1", "call-2"]


def test_parse_markdown_fenced_json_strips_fence():
    """Claude sometimes ignores the no-markdown instruction. Defend
    against it without scolding the model."""
    payload = (
        "```json\n"
        + json.dumps({"concerns": [{"text": "Watchpoint A"}]})
        + "\n```"
    )

    result = concerns._parse_concerns_response(payload)

    assert len(result) == 1
    assert result[0]["text"] == "Watchpoint A"
    assert "severity" not in result[0]  # not in input → not in output


def test_parse_empty_concerns_list_returns_empty():
    payload = json.dumps({"concerns": []})

    result = concerns._parse_concerns_response(payload)

    assert result == []


def test_parse_malformed_json_returns_empty():
    """Don't write garbage into factors.concerns[]; degrade silently."""
    result = concerns._parse_concerns_response("this is not json")
    assert result == []


def test_parse_missing_concerns_key_returns_empty():
    payload = json.dumps({"unrelated": [1, 2, 3]})
    result = concerns._parse_concerns_response(payload)
    assert result == []


def test_parse_invalid_severity_dropped():
    """Severity must be low/medium/high. Other values silently
    omitted, NOT propagated as a wrong shape into factors."""
    payload = json.dumps(
        {"concerns": [{"text": "x", "severity": "catastrophic"}]}
    )
    result = concerns._parse_concerns_response(payload)
    assert len(result) == 1
    assert result[0]["text"] == "x"
    assert "severity" not in result[0]


def test_parse_empty_text_concern_dropped():
    """Text is the only required field; concerns without it are noise."""
    payload = json.dumps({"concerns": [{"text": ""}, {"text": "real"}]})
    result = concerns._parse_concerns_response(payload)
    assert len(result) == 1
    assert result[0]["text"] == "real"


# ---------------------------------------------------------------------------
# generate_concerns — flag gating
# ---------------------------------------------------------------------------


def test_generate_concerns_returns_empty_when_flag_disabled(mocker):
    """V1.1 default: GREGORY_CONCERNS_ENABLED is unset → flag is False
    → no Claude call, empty list returned."""
    mocker.patch.object(concerns, "CONCERNS_ENABLED", False)
    complete_spy = mocker.patch.object(concerns, "complete")

    result = concerns.generate_concerns(db=mocker.Mock(), client_id="c-1")

    assert result == []
    complete_spy.assert_not_called()


def test_generate_concerns_skips_claude_when_no_input(mocker):
    """Flag on, but client has no summaries AND no action items.
    Don't burn tokens for empty input."""
    mocker.patch.object(concerns, "CONCERNS_ENABLED", True)
    mocker.patch.object(concerns, "_fetch_recent_summaries", return_value=[])
    mocker.patch.object(concerns, "_fetch_open_action_items", return_value=[])
    complete_spy = mocker.patch.object(concerns, "complete")

    result = concerns.generate_concerns(db=mocker.Mock(), client_id="c-1")

    assert result == []
    complete_spy.assert_not_called()


def test_generate_concerns_calls_claude_when_input_present(mocker):
    """Flag on + summaries present → Claude call happens, output parsed."""
    mocker.patch.object(concerns, "CONCERNS_ENABLED", True)
    mocker.patch.object(
        concerns,
        "_fetch_recent_summaries",
        return_value=[
            {
                "call_id": "call-1",
                "started_at": "2026-04-15T00:00:00Z",
                "title": "Coaching call",
                "content": "Client said they're nervous about pricing.",
            }
        ],
    )
    mocker.patch.object(concerns, "_fetch_open_action_items", return_value=[])
    mocker.patch.object(
        concerns, "_fetch_client_full_name", return_value="Test Client"
    )
    mocker.patch.object(
        concerns,
        "complete",
        return_value=SimpleNamespace(
            text=json.dumps(
                {
                    "concerns": [
                        {
                            "text": "Pricing nervousness",
                            "severity": "medium",
                            "source_call_ids": ["call-1"],
                        }
                    ]
                }
            )
        ),
    )

    result = concerns.generate_concerns(
        db=mocker.Mock(), client_id="c-1", run_id="run-xyz"
    )

    assert len(result) == 1
    assert result[0]["text"] == "Pricing nervousness"
    assert result[0]["severity"] == "medium"
