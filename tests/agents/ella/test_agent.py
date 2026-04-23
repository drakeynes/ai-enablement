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
    confidence = 0.0 if agent._looks_like_escalation(response_text) else 1.0
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
# Escalation path — Ella's response uses the escalation phrasing
# ---------------------------------------------------------------------------


def test_respond_to_mention_escalates_when_ella_uses_phrase(mocker):
    escalation_text = (
        "Good question — let me loop in your advisor on this one. "
        "They'll be the right call here."
    )
    spies = _patch_common(mocker, response_text=escalation_text)

    result = agent.respond_to_mention(_event(text="should I fire this client?"))

    assert result.escalated is True
    assert result.escalation_reason == "ella_escalated"
    assert result.escalation_id == "esc-xyz"
    # Ella's actual response text is preserved (not swapped for an ack).
    assert result.response_text == escalation_text
    assert result.confidence == 0.0
    assert result.agent_run_id == "run-abc"

    spies.escalate.assert_called_once()
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
# Escalation phrase detection — direct unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Let me loop in your advisor on this one.",
        "I want to check with your advisor on this.",
        "Let's get your advisor looped in.",
        "LOOP IN YOUR ADVISOR",  # case-insensitive
    ],
)
def test_looks_like_escalation_matches_known_phrases(text):
    assert agent._looks_like_escalation(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Here's how to set up your first sales call: ...",
        "Your advisor is Lou — they cover that on the next call.",
        "",
    ],
)
def test_looks_like_escalation_misses_non_escalation_text(text):
    assert agent._looks_like_escalation(text) is False
