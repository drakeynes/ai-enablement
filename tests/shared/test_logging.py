"""Unit tests for shared.logging.

Mocked — does not write to Supabase.
"""

from __future__ import annotations

import pytest

from shared import logging as agent_logging


class _FakeQuery:
    """Captures the call chain a supabase-py query builds up."""

    def __init__(self, response_data: list[dict] | None = None):
        self.calls: list[tuple] = []
        self._response_data = response_data or []

    def table(self, name):
        self.calls.append(("table", name))
        return self

    def insert(self, payload):
        self.calls.append(("insert", payload))
        return self

    def update(self, payload):
        self.calls.append(("update", payload))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def execute(self):
        return type("R", (), {"data": self._response_data})()


def test_start_agent_run_inserts_with_running_status(mocker):
    fake = _FakeQuery(response_data=[{"id": "run-123"}])
    mocker.patch("shared.logging.get_client", return_value=fake)

    run_id = agent_logging.start_agent_run(
        agent_name="ella",
        trigger_type="slack_mention",
        trigger_metadata={"channel": "C1"},
        input_summary="hello",
    )

    assert run_id == "run-123"
    assert ("table", "agent_runs") in fake.calls
    insert_call = next(c for c in fake.calls if c[0] == "insert")
    payload = insert_call[1]
    assert payload["agent_name"] == "ella"
    assert payload["trigger_type"] == "slack_mention"
    assert payload["status"] == "running"
    assert payload["trigger_metadata"] == {"channel": "C1"}
    assert payload["input_summary"] == "hello"


def test_end_agent_run_updates_with_terminal_fields(mocker):
    fake = _FakeQuery()
    mocker.patch("shared.logging.get_client", return_value=fake)

    agent_logging.end_agent_run(
        run_id="run-123",
        status="success",
        output_summary="answered",
        llm_model="claude-sonnet-4-6",
        llm_input_tokens=1000,
        llm_output_tokens=50,
        llm_cost_usd=0.0042,
        duration_ms=1200,
    )

    update_call = next(c for c in fake.calls if c[0] == "update")
    payload = update_call[1]
    assert payload["status"] == "success"
    assert payload["output_summary"] == "answered"
    assert payload["llm_input_tokens"] == 1000
    assert payload["llm_cost_usd"] == "0.0042"
    assert "ended_at" in payload
    assert ("eq", "id", "run-123") in fake.calls


def test_end_agent_run_rejects_invalid_status(mocker):
    mocker.patch("shared.logging.get_client", return_value=_FakeQuery())

    with pytest.raises(ValueError, match="status must be one of"):
        agent_logging.end_agent_run(run_id="run-123", status="running")
