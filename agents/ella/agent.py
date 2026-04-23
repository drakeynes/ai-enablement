"""Ella (Slack Bot V1) — entry point.

`respond_to_mention(event_data)` is the function the Slack interface
layer calls when Ella is @mentioned. The flow:

  1. Start an `agent_runs` row via `shared.logging.start_agent_run`.
  2. Resolve the client from the Slack user id in the event.
  3. Retrieve context via `agents.ella.retrieval`.
  4. Build the system prompt via `agents.ella.prompts`.
  5. Call Claude via `_call_claude` (real call into
     `shared.claude_client.complete` — token costs land on the run).
  6. Detect the [ESCALATE] marker at the start of the response. If
     Ella signaled an escalation, the marker is stripped and
     `escalate()` is called. Ella's own warm ack (now marker-free)
     is preserved verbatim on the returned `EllaResponse` — the
     system prompt trains her to write a short, warm message
     (default cheerful / humble sparingly / emotional patterns).
     A canned ack would flatten the emotional-escalation
     distinction, which is the tone we care most about getting
     right.
  7. End the agent_run with terminal status and return `EllaResponse`.

Escalation is marker-based, not numeric. The system prompt instructs
Ella to prefix every escalation response with the literal token
[ESCALATE] on its own line; the detector checks for that token at the
start of the response (after lstripping) and strips it before the
text is returned to the handler or written to `escalations.context` —
the client never sees the control token. This replaced a substring-
matching approach that missed acks where Ella personalized by naming
the advisor ("get Lou looped in") instead of using the literal phrase
"your advisor," which is the behavior the system prompt rewards. The
`confidence` field on `EllaResponse` is kept for telemetry continuity
— 1.0 for direct answers, 0.0 for escalations — but is no longer the
gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.ella.escalation import escalate
from agents.ella.prompts import build_system_prompt
from agents.ella.retrieval import ContextBundle, retrieve_context_for_client
from shared.claude_client import complete
from shared.db import get_client
from shared.logging import end_agent_run, logger, start_agent_run

# Literal token Ella is instructed (in the system prompt) to prefix
# every escalation response with. Detection is start-of-response,
# case-sensitive, exact bracket form — see prompts.py § WHAT YOU
# ESCALATE. The marker is stripped before the response text is stored
# on the agent_runs row, written to escalations.context, or returned
# to the handler.
_ESCALATION_MARKER = "[ESCALATE]"


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

    # Stitch the primary CSM dict onto the client dict so prompts.py
    # has a single bag of profile data to render from. ContextBundle
    # stays the canonical retrieval shape; the prompt just needs the
    # flat view.
    client_for_prompt = dict(client)
    client_for_prompt["primary_csm"] = context.primary_csm

    system_prompt = build_system_prompt(client_for_prompt, context.chunks)
    response_text, confidence = _call_claude(
        system_prompt, query_text, context, run_id=run_id
    )

    if _is_escalation(response_text):
        # Strip the control token before anything downstream sees it —
        # the client doesn't need to see it, and neither does the CSM
        # reviewing the escalations row. `proposed_action` is
        # intentionally omitted; its contract is "what the agent
        # wanted to do, for a reviewer to approve / reject / edit" —
        # in V1 there's no approval UI and Ella's response has
        # already been posted to the client by the time this row
        # lands. The cleaned ack is on the row via
        # `context.ella_response` for reference.
        client_text = _strip_escalation_marker(response_text)
        escalation_id = escalate(
            reason="ella_escalated",
            context={
                "query_text": query_text,
                "ella_response": client_text,
                "client_id": client["id"],
                "event": _redact_event(event_data),
            },
            client_id=client["id"],
            agent_run_id=run_id,
        )
        end_agent_run(
            run_id,
            status="escalated",
            output_summary=f"escalated to advisor (escalation_id={escalation_id})",
            confidence_score=confidence,
        )
        return EllaResponse(
            response_text=client_text,
            confidence=confidence,
            escalated=True,
            escalation_reason="ella_escalated",
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
# Claude + retrieval seams
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
    *,
    run_id: str | None = None,
) -> tuple[str, float]:
    """Call Claude with Ella's system prompt and the user's question.

    Returns `(response_text, confidence)`. The response text is
    returned raw — including the [ESCALATE] marker if Ella emitted
    one — so `_run` can route on the marker and strip it before the
    text flows further. Confidence is a coarse telemetry signal, not
    the gate: 1.0 for direct answers, 0.0 when the marker is present.

    `run_id` is passed through so token counts and cost land on the
    correct `agent_runs` row.
    """
    result = complete(
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
        run_id=run_id,
    )
    text = result.text.strip()
    confidence = 0.0 if _is_escalation(text) else 1.0
    return text, confidence


def _is_escalation(response_text: str) -> bool:
    """Detect the [ESCALATE] marker at the start of the response.

    Case-sensitive, exact bracket form. Leading whitespace /
    newlines are stripped before the check so Claude's occasional
    leading newline doesn't cause a miss. Mid-string mentions of
    [ESCALATE] (e.g., Ella explaining what escalation means, or
    echoing a user who typed it) are deliberately not matched — only
    a prefix signals a handoff.
    """
    return response_text.lstrip().startswith(_ESCALATION_MARKER)


def _strip_escalation_marker(response_text: str) -> str:
    """Remove the [ESCALATE] marker and the whitespace between it and
    the ack body. Idempotent: returns the text unchanged if no marker
    is present at the start.
    """
    leading_stripped = response_text.lstrip()
    if not leading_stripped.startswith(_ESCALATION_MARKER):
        return response_text
    remainder = leading_stripped[len(_ESCALATION_MARKER):]
    return remainder.lstrip()


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
    """Keep only fields useful for logging; drop Slack payload bulk.

    `is_team_test` is included when the Slack handler stamps it onto
    the event so we can later filter team-test runs out of client
    interaction metrics."""
    keys = ("user", "channel", "ts", "thread_ts", "event_ts", "is_team_test")
    return {k: event_data.get(k) for k in keys if event_data.get(k) is not None}
