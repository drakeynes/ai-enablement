"""HITL escalation for Ella.

Resolves the client's primary CSM (via `client_team_assignments`) and
delegates the actual row write to `shared.hitl.escalate`. Keeping this
thin layer in the Ella module means other agents build their own
escalation helpers with different routing logic, without Ella's
assignment logic leaking into shared code.
"""

from __future__ import annotations

from typing import Any

from shared.db import get_client
from shared.hitl import escalate as hitl_escalate


def escalate(
    reason: str,
    context: dict[str, Any],
    client_id: str,
    *,
    agent_run_id: str,
    proposed_action: dict[str, Any] | None = None,
) -> str:
    """Route an Ella-side escalation to the client's primary CSM.

    Returns the new `escalations.id`. If the client has no active
    primary CSM, the row still lands with `assigned_to = null` — a
    downstream n8n workflow or manual pickup handles unassigned
    escalations per the HITL runbook.
    """
    assigned_to = _resolve_primary_csm_id(client_id)
    return hitl_escalate(
        agent_run_id=agent_run_id,
        agent_name="ella",
        reason=reason,
        context=context,
        proposed_action=proposed_action,
        assigned_to=assigned_to,
    )


def _resolve_primary_csm_id(client_id: str) -> str | None:
    db = get_client()
    resp = (
        db.table("client_team_assignments")
        .select("team_member_id")
        .eq("client_id", client_id)
        .eq("role", "primary_csm")
        .is_("unassigned_at", "null")
        .execute()
    )
    rows = resp.data or []
    return rows[0]["team_member_id"] if rows else None
