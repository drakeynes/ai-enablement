"""Slack event handler for Ella.

`handle_slack_event(event_payload)` is the bridge between the Slack
Events API webhook (delivered by whatever interface layer ends up
fronting Ella — n8n, FastAPI, Vercel function) and the agent core.
This module does not call Slack's API. It parses the inbound event,
decides whether Ella should respond, prepares the event dict the
agent expects, and returns the response data structured for the
caller to render back to Slack.

V1 routing rules (kept tight on purpose):

  - Only `app_mention` events are answered. DMs and channel
    `message.*` events are ignored.
  - Only channels with a row in `slack_channels` whose `client_id` is
    set are answered. Channels not mapped to a client get a no-op.
    `ella_enabled` is NOT consulted here — for V1 the enabled-channel
    list is hardcoded upstream (the team-facing scope doc calls this
    out as a deferred-to-V1.1 setting).
  - The asker is one of: a known client (slack_user_id matches an
    active client), a known team member (matches an active team
    member), or unknown.
      * client: respond normally with that client's context.
      * team_member: respond using the *channel's* client context and
        stamp `is_team_test=True` on the event so the run is
        filterable in agent_runs metrics. Team testing in pilot
        channels is the V1 way the team validates Ella before
        clients see her.
      * unknown: no-op. We never respond to messages from accounts
        we can't attribute.

The handler returns a flat dict (not a dataclass) because the
caller serializes it straight back to whatever transport posted the
webhook. `responded=False` means Ella stayed silent — the caller
should not attempt to post anything in that case.
"""

from __future__ import annotations

import re
from typing import Any

from agents.ella.agent import respond_to_mention
from shared.db import get_client
from shared.logging import logger

# Slack mention tokens look like `<@U12345>` or `<@U12345|name>`. We
# strip them out before passing the text to the agent so the model
# isn't distracted by the bot id.
_MENTION_RE = re.compile(r"<@[UW][A-Z0-9]+(?:\|[^>]+)?>")


def handle_slack_event(event_payload: dict[str, Any]) -> dict[str, Any]:
    """Process one inbound Slack event. See module docstring.

    Accepts either the full Events API outer payload (with
    `{"type": "event_callback", "event": {...}}`) or the inner
    event dict directly. The handler unwraps as needed.
    """
    event = _unwrap_event(event_payload)

    if event.get("type") != "app_mention":
        return _no_response(reason="not_app_mention")

    channel_id = event.get("channel")
    user_id = event.get("user")
    thread_ts = event.get("thread_ts") or event.get("ts")
    raw_text = event.get("text") or ""
    text = _strip_mentions(raw_text)

    if not channel_id or not user_id:
        return _no_response(reason="missing_channel_or_user")

    db = get_client()

    channel_row = _lookup_channel(db, channel_id)
    if channel_row is None or channel_row.get("client_id") is None:
        # Either the channel isn't in our mirror yet, or it isn't
        # mapped to a client (internal channel). Either way, Ella
        # has nothing to say.
        logger.info("ella.slack_handler: channel %s not mapped to a client", channel_id)
        return _no_response(reason="channel_not_client_mapped")

    channel_client_id = channel_row["client_id"]

    asker_kind, channel_client_slack_user_id = _classify_asker(
        db, user_id=user_id, channel_client_id=channel_client_id
    )

    if asker_kind == "unknown":
        logger.info(
            "ella.slack_handler: ignoring mention from unknown user %s in channel %s",
            user_id,
            channel_id,
        )
        return _no_response(reason="unknown_asker")

    # Build the event the agent core will see. For client askers
    # this is the original event; for team-member askers we rewrite
    # `user` to the channel's client so retrieval is scoped right.
    agent_event = dict(event)
    agent_event["text"] = text
    agent_event["thread_ts"] = thread_ts
    if asker_kind == "team_member":
        if not channel_client_slack_user_id:
            # Channel maps to a client without a slack_user_id —
            # we can't pretend to be them. Bail loudly.
            logger.warning(
                "ella.slack_handler: team-member test in channel %s but client "
                "%s has no slack_user_id; skipping",
                channel_id,
                channel_client_id,
            )
            return _no_response(reason="team_test_client_missing_slack_id")
        agent_event["user"] = channel_client_slack_user_id
        agent_event["is_team_test"] = True

    response = respond_to_mention(agent_event)

    return {
        "responded": True,
        "text": response.response_text,
        "thread_ts": thread_ts,
        "channel_id": channel_id,
        "escalated": response.escalated,
        "escalation_id": response.escalation_id,
        "agent_run_id": response.agent_run_id,
        "is_team_test": asker_kind == "team_member",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unwrap_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the inner event dict.

    Slack's Events API wraps app events as
    `{"type": "event_callback", "event": {...}}`. Some upstream
    layers (n8n nodes, test fixtures) hand us the inner dict
    directly. Accept both."""
    if payload.get("type") == "event_callback" and isinstance(payload.get("event"), dict):
        return payload["event"]
    return payload


def _strip_mentions(text: str) -> str:
    """Remove all `<@U...>` mention tokens and collapse whitespace."""
    cleaned = _MENTION_RE.sub("", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _lookup_channel(db, slack_channel_id: str) -> dict[str, Any] | None:
    resp = (
        db.table("slack_channels")
        .select("slack_channel_id,client_id")
        .eq("slack_channel_id", slack_channel_id)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _classify_asker(
    db, *, user_id: str, channel_client_id: str
) -> tuple[str, str | None]:
    """Return `(asker_kind, channel_client_slack_user_id)`.

    `asker_kind` is one of `"client"`, `"team_member"`, `"unknown"`.
    The second return value is the slack_user_id of the channel's
    client (only needed by callers when `asker_kind == "team_member"`,
    but we fetch it eagerly in that case to keep the call site flat).
    """
    # Team member match wins over client match — if a Slack id ever
    # collides across both tables, the team-member interpretation
    # is the safer one (we treat it as a test, not a client query).
    team_resp = (
        db.table("team_members")
        .select("id")
        .eq("slack_user_id", user_id)
        .is_("archived_at", "null")
        .execute()
    )
    if team_resp.data:
        client_resp = (
            db.table("clients")
            .select("slack_user_id")
            .eq("id", channel_client_id)
            .is_("archived_at", "null")
            .execute()
        )
        rows = client_resp.data or []
        channel_client_slack_user_id = rows[0]["slack_user_id"] if rows else None
        return ("team_member", channel_client_slack_user_id)

    client_resp = (
        db.table("clients")
        .select("id")
        .eq("slack_user_id", user_id)
        .is_("archived_at", "null")
        .execute()
    )
    if client_resp.data:
        return ("client", None)

    return ("unknown", None)


def _no_response(*, reason: str) -> dict[str, Any]:
    """Shape returned when Ella stays silent."""
    return {
        "responded": False,
        "reason": reason,
        "text": "",
        "thread_ts": None,
        "channel_id": None,
        "escalated": False,
        "escalation_id": None,
        "agent_run_id": None,
        "is_team_test": False,
    }
