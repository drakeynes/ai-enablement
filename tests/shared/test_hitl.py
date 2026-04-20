"""Unit tests for shared.hitl.

Mocked — does not write to Supabase.
"""

from __future__ import annotations

from shared import hitl


class _FakeQuery:
    def __init__(self, response_data):
        self.calls: list[tuple] = []
        self._response_data = response_data

    def table(self, name):
        self.calls.append(("table", name))
        return self

    def insert(self, payload):
        self.calls.append(("insert", payload))
        return self

    def execute(self):
        return type("R", (), {"data": self._response_data})()


def test_escalate_inserts_required_fields(mocker):
    fake = _FakeQuery(response_data=[{"id": "esc-1"}])
    mocker.patch("shared.hitl.get_client", return_value=fake)

    esc_id = hitl.escalate(
        agent_run_id="run-1",
        agent_name="ella",
        reason="low confidence",
        context={"question": "?"},
    )

    assert esc_id == "esc-1"
    insert_call = next(c for c in fake.calls if c[0] == "insert")
    payload = insert_call[1]
    assert payload["agent_run_id"] == "run-1"
    assert payload["agent_name"] == "ella"
    assert payload["reason"] == "low confidence"
    assert payload["context"] == {"question": "?"}
    assert "proposed_action" not in payload
    assert "assigned_to" not in payload


def test_escalate_includes_optional_fields_when_provided(mocker):
    fake = _FakeQuery(response_data=[{"id": "esc-2"}])
    mocker.patch("shared.hitl.get_client", return_value=fake)

    hitl.escalate(
        agent_run_id="run-2",
        agent_name="ella",
        reason="out of scope",
        context={"question": "refund?"},
        proposed_action={"reply": "let me check"},
        assigned_to="tm-1",
    )

    payload = next(c for c in fake.calls if c[0] == "insert")[1]
    assert payload["proposed_action"] == {"reply": "let me check"}
    assert payload["assigned_to"] == "tm-1"
