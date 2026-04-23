"""Happy-path wiring test for `agents.ella.agent`.

Verifies that `respond_to_mention` threads through all the right
collaborators: start_agent_run → client resolution → retrieval →
prompt build → Claude call → escalation detection → end_agent_run →
EllaResponse. Mocks every collaborator so no DB / no OpenAI / no
Claude.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.ella import agent
from agents.ella.retrieval import ContextBundle


_CLIENT = {
    "id": "c-1",
    "full_name": "Test Client",
    "slack_user_id": "U12345",
    "email": "tc@example.com",
}

_PRIMARY_CSM = {
    "id": "tm-lou",
    "full_name": "Lou Perez",
    "email": "lou@theaipartner.io",
    "slack_user_id": "U09HY5TG3NX",
}


def _event(text: str = "how do I start with cold calling?") -> dict:
    return {
        "type": "app_mention",
        "user": "U12345",
        "channel": "C09TYEPLGBX",
        "text": f"<@UBOT> {text}",
        "ts": "1745000000.000100",
        "thread_ts": "1745000000.000100",
        "event_ts": "1745000000.000100",
    }


def _patch_common(mocker, *, response_text: str = "here's the answer"):
    """Stub every external collaborator the agent uses."""
    start = mocker.patch(
        "agents.ella.agent.start_agent_run", return_value="run-abc"
    )
    end = mocker.patch("agents.ella.agent.end_agent_run")
    mocker.patch(
        "agents.ella.agent._resolve_client_from_slack_user",
        return_value=dict(_CLIENT),
    )
    retrieve = mocker.patch(
        "agents.ella.agent._retrieve_context",
        return_value=ContextBundle(
            chunks=[], client=dict(_CLIENT), primary_csm=dict(_PRIMARY_CSM)
        ),
    )
    build_prompt = mocker.patch(
        "agents.ella.agent.build_system_prompt",
        return_value="[stub prompt]",
    )
    confidence = 0.0 if agent._is_escalation(response_text) else 1.0
    call_claude = mocker.patch(
        "agents.ella.agent._call_claude",
        return_value=(response_text, confidence),
    )
    escalate = mocker.patch(
        "agents.ella.agent.escalate", return_value="esc-xyz"
    )
    return SimpleNamespace(
        start=start,
        end=end,
        retrieve=retrieve,
        build_prompt=build_prompt,
        call_claude=call_claude,
        escalate=escalate,
    )


# ---------------------------------------------------------------------------
# Happy path — confident direct answer
# ---------------------------------------------------------------------------


def test_respond_to_mention_direct_answer_returns_text(mocker):
    spies = _patch_common(mocker, response_text="here's the answer")

    result = agent.respond_to_mention(_event())

    assert isinstance(result, agent.EllaResponse)
    assert result.response_text == "here's the answer"
    assert result.confidence == 1.0
    assert result.escalated is False
    assert result.escalation_id is None
    assert result.agent_run_id == "run-abc"

    # start/end agent_run wired around the whole flow
    spies.start.assert_called_once()
    start_kwargs = spies.start.call_args.kwargs
    assert start_kwargs["agent_name"] == "ella"
    assert start_kwargs["trigger_type"] == "slack_mention"

    spies.end.assert_called_once()
    end_kwargs = spies.end.call_args.kwargs
    assert end_kwargs["status"] == "success"
    assert end_kwargs["confidence_score"] == 1.0

    # build_system_prompt got the client dict with primary_csm stitched on
    build_args = spies.build_prompt.call_args
    client_arg = build_args.args[0]
    assert client_arg["id"] == "c-1"
    assert client_arg["primary_csm"] == _PRIMARY_CSM

    # No escalation
    spies.retrieve.assert_called_once()
    spies.escalate.assert_not_called()


# ---------------------------------------------------------------------------
# Escalation path — Ella's response starts with the [ESCALATE] marker
# ---------------------------------------------------------------------------


def test_respond_to_mention_escalates_when_response_starts_with_marker(mocker):
    ack_body = (
        "Good question — let me get Lou looped in so you can talk this "
        "through with your advisor directly."
    )
    marked_response = f"[ESCALATE]\n{ack_body}"
    spies = _patch_common(mocker, response_text=marked_response)

    result = agent.respond_to_mention(_event(text="should I fire this client?"))

    assert result.escalated is True
    assert result.escalation_reason == "ella_escalated"
    assert result.escalation_id == "esc-xyz"
    # The marker is stripped before anything downstream sees it —
    # the response text Ella's interface layer would post back to
    # Slack must not carry the control token.
    assert "[ESCALATE]" not in result.response_text
    assert result.response_text == ack_body
    assert result.confidence == 0.0
    assert result.agent_run_id == "run-abc"

    spies.escalate.assert_called_once()
    # The cleaned ack (not the raw marked string) is what lands on
    # escalations.context.ella_response, so a CSM reviewing the row
    # sees what the client saw.
    esc_kwargs = spies.escalate.call_args.kwargs
    assert esc_kwargs["context"]["ella_response"] == ack_body
    assert "[ESCALATE]" not in esc_kwargs["context"]["ella_response"]
    # proposed_action is intentionally omitted in V1 — pinned so a
    # future refactor doesn't silently re-introduce it.
    assert "proposed_action" not in esc_kwargs or esc_kwargs["proposed_action"] is None

    end_kwargs = spies.end.call_args.kwargs
    assert end_kwargs["status"] == "escalated"


# ---------------------------------------------------------------------------
# No client resolved → skip rather than crash
# ---------------------------------------------------------------------------


def test_respond_to_mention_skips_when_no_client_found(mocker):
    mocker.patch("agents.ella.agent.start_agent_run", return_value="run-abc")
    end = mocker.patch("agents.ella.agent.end_agent_run")
    mocker.patch(
        "agents.ella.agent._resolve_client_from_slack_user", return_value=None
    )
    # Retrieve / Claude / escalate should never be called in this path.
    retrieve = mocker.patch("agents.ella.agent._retrieve_context")
    claude = mocker.patch("agents.ella.agent._call_claude")
    esc = mocker.patch("agents.ella.agent.escalate")

    result = agent.respond_to_mention(_event())

    assert result.response_text == ""
    assert result.escalated is False
    retrieve.assert_not_called()
    claude.assert_not_called()
    esc.assert_not_called()
    end.assert_called_once()
    assert end.call_args.kwargs["status"] == "skipped"


# ---------------------------------------------------------------------------
# Exception path — end_agent_run with status='error', re-raise
# ---------------------------------------------------------------------------


def test_respond_to_mention_raises_and_closes_run_on_exception(mocker):
    mocker.patch("agents.ella.agent.start_agent_run", return_value="run-abc")
    end = mocker.patch("agents.ella.agent.end_agent_run")
    mocker.patch(
        "agents.ella.agent._resolve_client_from_slack_user",
        side_effect=RuntimeError("boom"),
    )

    with pytest.raises(RuntimeError, match="boom"):
        agent.respond_to_mention(_event())

    end.assert_called_once()
    assert end.call_args.kwargs["status"] == "error"
    assert "boom" in end.call_args.kwargs["error_message"]


# ---------------------------------------------------------------------------
# Escalation marker detection — direct unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # Canonical shape: marker on its own line, ack below.
        "[ESCALATE]\nAbel, let me loop in your advisor on this one.",
        # Inline separator (space) instead of newline — still a valid prefix.
        "[ESCALATE] Short ack.",
        # Leading whitespace / newlines that Claude sometimes emits.
        "\n[ESCALATE]\nAbel, let me loop in your advisor.",
        "   [ESCALATE] short ack.",
    ],
)
def test_is_escalation_matches_marker_prefix(text):
    assert agent._is_escalation(text) is True


@pytest.mark.parametrize(
    "text",
    [
        # Escalation-style prose without the marker — exactly the
        # false-positive risk the old phrase detector had.
        "Let me loop in your advisor on this one.",
        "Let me get Lou looped in so you can talk this through.",
        # Non-escalation answer.
        "Your advisor is Lou — they cover that on the next call.",
        # Marker appears mid-string, not a handoff signal.
        "Here's my answer. If this doesn't resolve it, we can [ESCALATE] later.",
        # Case-sensitive: lowercase doesn't count.
        "[escalate]\nAbel, let me loop in your advisor.",
        "",
    ],
)
def test_is_escalation_misses_non_marked_text(text):
    assert agent._is_escalation(text) is False


# ---------------------------------------------------------------------------
# Marker stripping — direct unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "[ESCALATE]\nAbel, let me loop in your advisor.",
            "Abel, let me loop in your advisor.",
        ),
        (
            "[ESCALATE] short ack.",
            "short ack.",
        ),
        (
            "[ESCALATE]\n\n\nSpacing varies.",
            "Spacing varies.",
        ),
        (
            "   [ESCALATE]\nLeading whitespace is tolerated.",
            "Leading whitespace is tolerated.",
        ),
        # Idempotent on unmarked text.
        (
            "No marker here — just an answer.",
            "No marker here — just an answer.",
        ),
        ("", ""),
    ],
)
def test_strip_escalation_marker(raw, expected):
    assert agent._strip_escalation_marker(raw) == expected
