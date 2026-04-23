"""Ella (Slack Bot V1) — entry point.

`respond_to_mention(event_data)` is the function the Slack interface
layer calls when Ella is @mentioned. The flow:

  1. Start an `agent_runs` row via `shared.logging.start_agent_run`.
  2. Resolve the client from the Slack user id in the event.
  3. Retrieve context via `agents.ella.retrieval`.
  4. Build the system prompt via `agents.ella.prompts`.
  5. Call Claude via `_call_claude` (real call into
     `shared.claude_client.complete` — token costs land on the run).
  6. Detect escalation in the response text. If Ella signaled an
     escalation, `escalate()` is called and the response_text is
     swapped for a short client-facing ack.
  7. End the agent_run with terminal status and return `EllaResponse`.

Escalation is pattern-based, not numeric. The system prompt instructs
Ella to use one of a small set of phrases ("loop in your advisor",
"check with your advisor", "get your advisor looped in") whenever she
chooses to escalate. We grep her output for those phrases instead of
relying on a confidence score the model would have to fabricate. The
`confidence` field on `EllaResponse` is kept for telemetry continuity —
1.0 for direct answers, 0.0 for escalations — but is no longer the
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

# Phrases Ella is instructed (in the system prompt) to use whenever she
# wants to escalate. Match is case-insensitive substring. Keep this
# list in sync with the escalation guidance block in prompts.py.
_ESCALATION_PHRASES: tuple[str, ...] = (
    "loop in your advisor",
    "check with your advisor",
    "get your advisor looped in",
)


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

    if _looks_like_escalation(response_text):
        escalation_id = escalate(
            reason="ella_escalated",
            context={
                "query_text": query_text,
                "ella_response": response_text,
                "client_id": client["id"],
                "event": _redact_event(event_data),
            },
            client_id=client["id"],
            agent_run_id=run_id,
            proposed_action={"response_text": response_text},
        )
        end_agent_run(
            run_id,
            status="escalated",
            output_summary=f"escalated to advisor (escalation_id={escalation_id})",
            confidence_score=confidence,
        )
        return EllaResponse(
            response_text=response_text,
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

    Returns `(response_text, confidence)`. Confidence here is a
    coarse signal for telemetry, not a gate — escalation is decided
    by `_looks_like_escalation` on the response text. We return 1.0
    for direct answers (the caller flips it to 0.0 if it later
    detects an escalation phrase).

    `run_id` is passed through so token counts and cost land on the
    correct `agent_runs` row.
    """
    result = complete(
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
        run_id=run_id,
    )
    text = result.text.strip()
    confidence = 0.0 if _looks_like_escalation(text) else 1.0
    return text, confidence


def _looks_like_escalation(response_text: str) -> bool:
    """Detect whether Ella's response is an escalation ack.

    Substring match (case-insensitive) against the small set of
    phrases the system prompt instructs her to use. Intentionally
    strict — we'd rather miss an ambiguous escalation and let the
    client respond again than treat a confident answer as one."""
    lowered = response_text.lower()
    return any(phrase in lowered for phrase in _ESCALATION_PHRASES)


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
