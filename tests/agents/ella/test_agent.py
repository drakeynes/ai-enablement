"""Happy-path wiring test for `agents.ella.agent`.

Verifies that `respond_to_mention` threads through all the right
collaborators: start_agent_run → client resolution → retrieval →
prompt build → Claude call → end_agent_run → EllaResponse. Mocks
every collaborator so no DB / no OpenAI / no Claude.
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


def _patch_common(mocker, *, confidence: float = 0.85):
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
    mocker.patch(
        "agents.ella.agent.build_system_prompt",
        return_value="[stub prompt]",
    )
    mocker.patch(
        "agents.ella.agent._call_claude",
        return_value=("here's the answer", confidence),
    )
    escalate = mocker.patch(
        "agents.ella.agent.escalate", return_value="esc-xyz"
    )
    return SimpleNamespace(
        start=start, end=end, retrieve=retrieve, escalate=escalate
    )


# ---------------------------------------------------------------------------
# Happy path — confident answer
# ---------------------------------------------------------------------------


def test_respond_to_mention_confident_answer_returns_text(mocker):
    spies = _patch_common(mocker, confidence=0.85)

    result = agent.respond_to_mention(_event())

    assert isinstance(result, agent.EllaResponse)
    assert result.response_text == "here's the answer"
    assert result.confidence == 0.85
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
    assert end_kwargs["confidence_score"] == 0.85

    # Retrieve called with the resolved client id, no escalation
    spies.retrieve.assert_called_once()
    spies.escalate.assert_not_called()


# ---------------------------------------------------------------------------
# Low-confidence → escalate path
# ---------------------------------------------------------------------------


def test_respond_to_mention_low_confidence_escalates(mocker):
    spies = _patch_common(mocker, confidence=0.4)

    result = agent.respond_to_mention(_event(text="how do I get a refund?"))

    assert result.escalated is True
    assert result.escalation_reason == "low_confidence"
    assert result.escalation_id == "esc-xyz"
    assert "check with your CSM" in result.response_text
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
