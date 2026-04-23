"""Wiring tests for `agents.ella.slack_handler`.

Mocks the database and the agent core so no Supabase / no Claude.
Verifies the routing rules from the handler module docstring:

  - non-app_mention events are dropped
  - channels not mapped to a client are dropped
  - unknown askers are dropped
  - client askers pass through with the original event
  - team-member askers get the event rewritten to the channel's
    client and `is_team_test=True` stamped

The agent core (`respond_to_mention`) is the seam we mock — we
assert on what the handler hands it, since that's the contract.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.ella import slack_handler
from agents.ella.agent import EllaResponse


# ---------------------------------------------------------------------------
# Test doubles for the supabase client
# ---------------------------------------------------------------------------


class _FakeQuery:
    """Records the chain of `.select(...).eq(...).is_(...).execute()`
    calls and returns whatever the parent FakeDB has queued up."""

    def __init__(self, parent: "_FakeDB", table: str):
        self.parent = parent
        self.table = table
        self.filters: dict[str, object] = {}

    def select(self, _cols):
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def is_(self, col, val):
        self.filters[f"{col}__is"] = val
        return self

    def execute(self):
        rows = self.parent.responses.get(self.table, [])
        return SimpleNamespace(data=rows)


class _FakeDB:
    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = responses

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)


def _patch_db(mocker, responses: dict[str, list[dict]]):
    db = _FakeDB(responses)
    mocker.patch("agents.ella.slack_handler.get_client", return_value=db)
    return db


def _patch_agent(mocker, *, escalated: bool = False) -> SimpleNamespace:
    """Patch out `respond_to_mention` so it returns a known shape."""
    response = EllaResponse(
        response_text="here's the answer",
        confidence=1.0,
        escalated=escalated,
        escalation_reason="ella_escalated" if escalated else None,
        escalation_id="esc-xyz" if escalated else None,
        agent_run_id="run-abc",
    )
    mock = mocker.patch(
        "agents.ella.slack_handler.respond_to_mention", return_value=response
    )
    return mock


def _event_callback(
    *,
    event_type: str = "app_mention",
    user: str = "U_CLIENT_1",
    channel: str = "C_CHAN_1",
    text: str = "<@UBOT> how do I cold call?",
    ts: str = "1745000000.000100",
    thread_ts: str | None = "1745000000.000100",
) -> dict:
    inner = {
        "type": event_type,
        "user": user,
        "channel": channel,
        "text": text,
        "ts": ts,
        "event_ts": ts,
    }
    if thread_ts is not None:
        inner["thread_ts"] = thread_ts
    return {"type": "event_callback", "event": inner}


# ---------------------------------------------------------------------------
# Routing: drop conditions
# ---------------------------------------------------------------------------


def test_handler_ignores_non_app_mention_events(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(mocker, {})

    payload = _event_callback(event_type="message")
    result = slack_handler.handle_slack_event(payload)

    assert result["responded"] is False
    assert result["reason"] == "not_app_mention"
    agent_mock.assert_not_called()


def test_handler_ignores_when_channel_not_mapped_to_client(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": None},
            ],
        },
    )

    result = slack_handler.handle_slack_event(_event_callback())

    assert result["responded"] is False
    assert result["reason"] == "channel_not_client_mapped"
    agent_mock.assert_not_called()


def test_handler_ignores_when_channel_row_missing(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(mocker, {"slack_channels": []})

    result = slack_handler.handle_slack_event(_event_callback())

    assert result["responded"] is False
    assert result["reason"] == "channel_not_client_mapped"
    agent_mock.assert_not_called()


def test_handler_ignores_unknown_asker(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": "client-uuid-1"},
            ],
            "team_members": [],
            "clients": [],
        },
    )

    result = slack_handler.handle_slack_event(_event_callback(user="U_RANDOM"))

    assert result["responded"] is False
    assert result["reason"] == "unknown_asker"
    agent_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Routing: client asker passes through unchanged
# ---------------------------------------------------------------------------


def test_handler_routes_client_mention_to_agent(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": "client-uuid-1"},
            ],
            "team_members": [],          # asker is not a team member
            "clients": [{"id": "client-uuid-1"}],  # asker IS a client
        },
    )

    result = slack_handler.handle_slack_event(
        _event_callback(user="U_CLIENT_1", text="<@UBOT> how do I cold call?")
    )

    agent_mock.assert_called_once()
    agent_event = agent_mock.call_args.args[0]
    assert agent_event["user"] == "U_CLIENT_1"
    assert agent_event["text"] == "how do I cold call?"
    assert agent_event["channel"] == "C_CHAN_1"
    assert "is_team_test" not in agent_event

    assert result["responded"] is True
    assert result["text"] == "here's the answer"
    assert result["channel_id"] == "C_CHAN_1"
    assert result["thread_ts"] == "1745000000.000100"
    assert result["escalated"] is False
    assert result["agent_run_id"] == "run-abc"
    assert result["is_team_test"] is False


def test_handler_uses_ts_when_thread_ts_absent(mocker):
    """A top-level mention has no thread_ts; we thread under its ts."""
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": "client-uuid-1"},
            ],
            "team_members": [],
            "clients": [{"id": "client-uuid-1"}],
        },
    )

    payload = _event_callback(thread_ts=None, ts="1745000000.000999")
    result = slack_handler.handle_slack_event(payload)

    assert result["thread_ts"] == "1745000000.000999"
    agent_event = agent_mock.call_args.args[0]
    assert agent_event["thread_ts"] == "1745000000.000999"


# ---------------------------------------------------------------------------
# Routing: team-member asker triggers test mode
# ---------------------------------------------------------------------------


def test_handler_team_member_rewrites_user_and_flags_test(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": "client-uuid-1"},
            ],
            # asker IS a team member — checked first
            "team_members": [{"id": "tm-uuid-drake"}],
            # team-member branch then fetches the channel client's slack id
            "clients": [{"slack_user_id": "U_CLIENT_1"}],
        },
    )

    result = slack_handler.handle_slack_event(
        _event_callback(user="U_DRAKE", text="<@UBOT> testing")
    )

    agent_mock.assert_called_once()
    agent_event = agent_mock.call_args.args[0]
    # User rewritten to the channel's client's slack id so the
    # agent's client resolution lands on that client.
    assert agent_event["user"] == "U_CLIENT_1"
    assert agent_event["is_team_test"] is True
    assert agent_event["text"] == "testing"

    assert result["responded"] is True
    assert result["is_team_test"] is True


def test_handler_team_member_skips_when_channel_client_has_no_slack_id(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": "client-uuid-1"},
            ],
            "team_members": [{"id": "tm-uuid-drake"}],
            "clients": [{"slack_user_id": None}],  # client lacks slack_user_id
        },
    )

    result = slack_handler.handle_slack_event(_event_callback(user="U_DRAKE"))

    assert result["responded"] is False
    assert result["reason"] == "team_test_client_missing_slack_id"
    agent_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Mention-stripping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<@UBOT> hello", "hello"),
        ("<@UBOT|ella> hello", "hello"),
        ("hey <@UBOT> what's up", "hey what's up"),
        ("<@UBOT>   spaced   out   ", "spaced out"),
        ("no mention here", "no mention here"),
    ],
)
def test_strip_mentions(raw, expected):
    assert slack_handler._strip_mentions(raw) == expected


# ---------------------------------------------------------------------------
# Unwrapping: accept both wrapped and bare event dicts
# ---------------------------------------------------------------------------


def test_handler_accepts_bare_event_dict(mocker):
    agent_mock = _patch_agent(mocker)
    _patch_db(
        mocker,
        {
            "slack_channels": [
                {"slack_channel_id": "C_CHAN_1", "client_id": "client-uuid-1"},
            ],
            "team_members": [],
            "clients": [{"id": "client-uuid-1"}],
        },
    )

    bare = _event_callback()["event"]
    result = slack_handler.handle_slack_event(bare)

    assert result["responded"] is True
    agent_mock.assert_called_once()
