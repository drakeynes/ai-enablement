"""Ella (Slack Bot V1) — entry point.

`respond_to_mention(event_data)` is the function the Slack interface
layer will call when Ella is @mentioned. Today it's a skeleton: wires
up `agent_runs` logging around retrieval + Claude + escalation so the
pieces are in place for prompt work and live testing to slot in.

Shape:

  1. Start an `agent_runs` row via `shared.logging.start_agent_run`.
  2. Resolve the client from the Slack user id in the event.
  3. Retrieve context via `agents.ella.retrieval`.
  4. Build the system prompt via `agents.ella.prompts` (stub today).
  5. Call Claude via `_call_claude` (stub today — canned response).
  6. Decide: confident response or escalate via `agents.ella.escalation`.
  7. End the agent_run with terminal status and return `EllaResponse`.

The two placeholders (`build_system_prompt` and `_call_claude`) get
real implementations in the next session once the system prompt is
drafted. No other call sites should need to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.ella.escalation import escalate
from agents.ella.prompts import build_system_prompt
from agents.ella.retrieval import ContextBundle, retrieve_context_for_client
from shared.db import get_client
from shared.logging import end_agent_run, logger, start_agent_run

# Confidence floor — below this, escalate instead of answering.
_CONFIDENCE_FLOOR = 0.7


@dataclass(frozen=True)
class EllaResponse:
    """What `respond_to_mention` returns for the Slack interface to render."""

    response_text: str
    confidence: float
    escalated: bool
    escalation_reason: str | None = None
    escalation_id: str | None = None
    agent_run_id: str | None = None


def respond_to_mention(event_data: dict[str, Any]) -> EllaResponse:
    """Handle one Slack @mention. See module docstring."""
    run_id = start_agent_run(
        agent_name="ella",
        trigger_type="slack_mention",
        trigger_metadata=_redact_event(event_data),
        input_summary=(event_data.get("text") or "")[:200],
    )
    try:
        return _run(event_data, run_id)
    except Exception as exc:
        logger.exception("ella.respond_to_mention failed: %s", exc)
        end_agent_run(run_id, status="error", error_message=str(exc))
        raise


def _run(event_data: dict[str, Any], run_id: str) -> EllaResponse:
    slack_user_id = event_data.get("user")
    client = _resolve_client_from_slack_user(slack_user_id)
    if client is None:
        # Pilot channels should always have a resolvable client —
        # `ella_enabled=true` is set per channel with a client_id.
        # If we see one anyway, log and skip rather than crash.
        reason = f"no_client_for_slack_user_id:{slack_user_id}"
        logger.warning("Ella: %s", reason)
        end_agent_run(run_id, status="skipped", output_summary=reason)
        return EllaResponse(
            response_text="",
            confidence=0.0,
            escalated=False,
            agent_run_id=run_id,
        )

    query_text = event_data.get("text") or ""
    context = _retrieve_context(client["id"], query_text)
    system_prompt = build_system_prompt(client, context.primary_csm)
    response_text, confidence = _call_claude(system_prompt, query_text, context)

    if confidence < _CONFIDENCE_FLOOR:
        escalation_id = escalate(
            reason="low_confidence",
            context={
                "query_text": query_text,
                "confidence": confidence,
                "client_id": client["id"],
                "event": _redact_event(event_data),
            },
            client_id=client["id"],
            agent_run_id=run_id,
            proposed_action={"response_text": response_text},
        )
        ack = (
            "Good question — let me check with your CSM on this one. "
            "They'll get back to you shortly. 🙏"
        )
        end_agent_run(
            run_id,
            status="escalated",
            output_summary=f"escalated to CSM (escalation_id={escalation_id})",
            confidence_score=confidence,
        )
        return EllaResponse(
            response_text=ack,
            confidence=confidence,
            escalated=True,
            escalation_reason="low_confidence",
            escalation_id=escalation_id,
            agent_run_id=run_id,
        )

    end_agent_run(
        run_id,
        status="success",
        output_summary=response_text[:200],
        confidence_score=confidence,
    )
    return EllaResponse(
        response_text=response_text,
        confidence=confidence,
        escalated=False,
        agent_run_id=run_id,
    )


# ---------------------------------------------------------------------------
# Placeholders — replaced when the system prompt + Claude call land
# ---------------------------------------------------------------------------


def _retrieve_context(client_id: str, query_text: str) -> ContextBundle:
    """Thin wrapper over `retrieve_context_for_client`. Kept as an
    internal helper so the agent's test seam is stable when we tune
    retrieval parameters (k, include_global, filters)."""
    return retrieve_context_for_client(client_id, query_text)


def _call_claude(
    system_prompt: str,
    user_text: str,
    context: ContextBundle,
) -> tuple[str, float]:
    """STUB. Returns a canned response and neutral confidence.

    Will be replaced with `shared.claude_client.complete(...)` after
    the system prompt is drafted. The tuple shape is the contract the
    agent depends on; don't change it without updating callers.
    """
    return ("(ella response placeholder — prompt not yet implemented)", 0.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_client_from_slack_user(slack_user_id: str | None) -> dict[str, Any] | None:
    """Look up the active client row for this Slack user id."""
    if not slack_user_id:
        return None
    db = get_client()
    resp = (
        db.table("clients")
        .select("*")
        .eq("slack_user_id", slack_user_id)
        .is_("archived_at", "null")
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _redact_event(event_data: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields useful for logging; drop Slack payload bulk."""
    return {
        k: event_data.get(k)
        for k in ("user", "channel", "ts", "thread_ts", "event_ts")
        if event_data.get(k) is not None
    }
