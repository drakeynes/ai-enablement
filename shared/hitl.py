"""Human-in-the-loop escalation helper.

One entry point — `escalate()` — that inserts a row into `escalations`
and returns its id. The Slack-notification side (DM to the assigned
reviewer, approval UI, resolution parsing) lives elsewhere; this
module is just the database write.

Every agent uses the same pattern: when the agent is not confident, or
the action needs approval, call `escalate()` with enough context for a
human reviewer to decide without re-investigating.

Example:

    from shared.hitl import escalate

    escalate(
        agent_run_id=run_id,
        agent_name="ella",
        reason="Question contains emotional language; not in scope.",
        context={
            "question": "I'm thinking of quitting the program.",
            "retrieved_chunks": [...],
            "client_id": client.id,
        },
        assigned_to=primary_csm.id,
    )
"""

from __future__ import annotations

from typing import Any

from shared.db import get_client


def escalate(
    agent_run_id: str,
    agent_name: str,
    reason: str,
    context: dict[str, Any],
    proposed_action: dict[str, Any] | None = None,
    assigned_to: str | None = None,
) -> str:
    """Insert a new escalations row and return its id.

    The row lands with `status='open'` (the table default). Resolution
    fields are filled in later by the approval UI when a human acts on
    the escalation.

    `context` must carry everything a reviewer needs to decide — the
    original question, the retrieved chunks, the client id, the
    agent's own reasoning. Shape varies per agent; keep it rich.

    `assigned_to` is optional. If omitted, routing is deferred to a
    later step (e.g., a downstream n8n workflow that picks an assignee
    based on `agent_name` and `context.client_id`).
    """
    payload: dict[str, Any] = {
        "agent_run_id": agent_run_id,
        "agent_name": agent_name,
        "reason": reason,
        "context": context,
    }
    if proposed_action is not None:
        payload["proposed_action"] = proposed_action
    if assigned_to is not None:
        payload["assigned_to"] = assigned_to

    result = (
        get_client()
        .table("escalations")
        .insert(payload)
        .execute()
    )
    return result.data[0]["id"]
