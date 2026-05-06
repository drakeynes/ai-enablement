"""Per-call CS Slack summary post (Batch A — M6.1).

Posts a one-message Fathom call summary to the cross-CSM Slack channel
on every successful Fathom webhook delivery for a `call_category='client'`
call. Hooked into `ingestion.fathom.pipeline.ingest_call` after the
summary document is written and before the IngestOutcome return.

Design constraints (per Drake's spec):
  - Only client calls trigger the post; other categories skip silently.
  - Edge cases (archived client, no primary_csm) post anyway with
    sentinel labels — "if they become a problem we will remove."
  - Slack-post failure is NEVER fatal to the Fathom webhook delivery.
    Exceptions are caught + logged; the call row + summary doc are
    more important than the Slack message.
  - Audit trail via `webhook_deliveries` with
    `source='cs_call_summary_slack_post'` so debugging "did the post
    happen for call X" doesn't require grepping Vercel logs.

Message format (plain text mrkdwn, no rich blocks per Drake's
"minimal time and energy" framing):

    *[CSM Name] / [Client Name]*
    [Fathom summary, full text]
    <https://ai-enablement-sigma.vercel.app/calls/[call_id]|View in Gregory>

Sentinel labels:
  - `[unassigned]` when no active primary_csm
  - `[unknown client]` when primary_client_id resolves to no row
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from shared.slack_post import post_message

logger = logging.getLogger("ai_enablement.cs_call_summary_post")

# Public-dashboard host for the deep-link. Hardcoded — every deployment
# of this code targets the production Vercel project; if we ever spin up
# a staging deploy we'd want this to derive from env.
_GREGORY_CALL_PATH = "https://ai-enablement-sigma.vercel.app/calls/{call_id}"

# webhook_deliveries source label. Searchable by SQL; do not change
# without updating any audit dashboards.
_DELIVERY_SOURCE = "cs_call_summary_slack_post"


def maybe_post_cs_call_summary(
    db,
    *,
    call_id: str,
    call_category: str,
    primary_client_id: str | None,
    summary_text: str | None,
    fathom_external_id: str,
) -> dict[str, Any]:
    """Post the CS call summary for a freshly-ingested call.

    Returns a structured result dict for the caller to log:
      {
        "posted": bool,
        "skipped_reason": str | None,
        "delivery_id": str,
        "slack_ok": bool,
        "slack_error": str | None,
      }

    NEVER raises. Wraps every internal failure as
    `posted=False, skipped_reason='<reason>'` or in the audit row.
    Caller is the Fathom pipeline; the Fathom webhook delivery must
    not fail because Slack posting failed.
    """
    delivery_id = f"cs_call_summary_{uuid.uuid4()}"

    # Skip non-client categories silently. No audit row — would clutter
    # webhook_deliveries with "we didn't do anything" for every internal/
    # external/unclassified call.
    if call_category != "client":
        return {
            "posted": False,
            "skipped_reason": "non_client_category",
            "delivery_id": delivery_id,
            "slack_ok": False,
            "slack_error": None,
        }

    # Skip if no summary text (shouldn't happen post-F2.3 for webhook
    # path; possible for backlog re-ingest before summary docs land).
    # Audit row recorded so we can spot if this happens unexpectedly.
    if not summary_text or not summary_text.strip():
        _insert_delivery(
            delivery_id,
            payload={
                "call_id": call_id,
                "fathom_external_id": fathom_external_id,
                "skipped_reason": "no_summary_text",
            },
            status="malformed",
            error="no_summary_text",
            call_external_id=fathom_external_id,
        )
        return {
            "posted": False,
            "skipped_reason": "no_summary_text",
            "delivery_id": delivery_id,
            "slack_ok": False,
            "slack_error": None,
        }

    channel_id = os.environ.get("SLACK_CS_CALL_SUMMARIES_CHANNEL_ID")
    if not channel_id:
        # Misconfiguration — log loudly but don't crash. Audit row
        # captures the gap for triage.
        logger.error(
            "cs_call_summary_post: SLACK_CS_CALL_SUMMARIES_CHANNEL_ID not set"
        )
        _insert_delivery(
            delivery_id,
            payload={
                "call_id": call_id,
                "fathom_external_id": fathom_external_id,
                "skipped_reason": "channel_not_configured",
            },
            status="failed",
            error="SLACK_CS_CALL_SUMMARIES_CHANNEL_ID not set",
            call_external_id=fathom_external_id,
        )
        return {
            "posted": False,
            "skipped_reason": "channel_not_configured",
            "delivery_id": delivery_id,
            "slack_ok": False,
            "slack_error": "channel_not_configured",
        }

    # Resolve labels. Each lookup wrapped in its own try/except so a
    # single failed lookup doesn't break the post — sentinel labels are
    # acceptable per Drake's spec.
    csm_name = _resolve_primary_csm_name(db, primary_client_id)
    client_name = _resolve_client_full_name(db, primary_client_id)

    text = _format_message(
        csm_name=csm_name or "[unassigned]",
        client_name=client_name or "[unknown client]",
        summary_text=summary_text.strip(),
        call_id=call_id,
    )

    # Insert the audit row BEFORE the post so even a Slack-side failure
    # leaves a record. UPDATE to terminal status after the post.
    _insert_delivery(
        delivery_id,
        payload={
            "call_id": call_id,
            "fathom_external_id": fathom_external_id,
            "csm_name": csm_name,
            "client_name": client_name,
        },
        status="received",
        error=None,
        call_external_id=fathom_external_id,
    )

    result = post_message(channel_id, text)
    if result["ok"]:
        _mark_delivery(delivery_id, status="processed", error=None)
        logger.info(
            "cs_call_summary_post: posted delivery_id=%s call_id=%s",
            delivery_id,
            call_id,
        )
        return {
            "posted": True,
            "skipped_reason": None,
            "delivery_id": delivery_id,
            "slack_ok": True,
            "slack_error": None,
        }

    # Slack-side failure. Log + mark audit row failed; never raise.
    _mark_delivery(
        delivery_id,
        status="failed",
        error=str(result.get("slack_error"))[:2000],
    )
    logger.warning(
        "cs_call_summary_post: slack post failed delivery_id=%s slack_error=%s",
        delivery_id,
        result.get("slack_error"),
    )
    return {
        "posted": False,
        "skipped_reason": "slack_post_failed",
        "delivery_id": delivery_id,
        "slack_ok": False,
        "slack_error": result.get("slack_error"),
    }


# ---------------------------------------------------------------------------
# Label resolution
# ---------------------------------------------------------------------------


def _resolve_primary_csm_name(db, client_id: str | None) -> str | None:
    """Return the active primary_csm's full_name for a client, or None.

    Mirrors api/accountability_roster.py's lookup pattern: query
    client_team_assignments with role='primary_csm' AND unassigned_at
    IS NULL, JOIN to team_members for the full_name.
    """
    if not client_id:
        return None
    try:
        resp = (
            db.table("client_team_assignments")
            .select("team_members(full_name)")
            .eq("client_id", client_id)
            .eq("role", "primary_csm")
            .is_("unassigned_at", "null")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "cs_call_summary_post: primary_csm lookup failed for client_id=%s: %s",
            client_id,
            exc,
        )
        return None
    rows = resp.data or []
    if not rows:
        return None
    tm = rows[0].get("team_members")
    if isinstance(tm, dict):
        return tm.get("full_name")
    return None


def _resolve_client_full_name(db, client_id: str | None) -> str | None:
    """Return the client's full_name (or None). Includes archived rows
    so an archived client still gets a name in the message."""
    if not client_id:
        return None
    try:
        resp = (
            db.table("clients")
            .select("full_name")
            .eq("id", client_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "cs_call_summary_post: client lookup failed for client_id=%s: %s",
            client_id,
            exc,
        )
        return None
    rows = resp.data or []
    if not rows:
        return None
    return rows[0].get("full_name")


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def _format_message(
    *,
    csm_name: str,
    client_name: str,
    summary_text: str,
    call_id: str,
) -> str:
    """Build the plain-text Slack message.

    Uses Slack mrkdwn link syntax for the deep-link
    (`<URL|link text>`) and `*bold*` for the header. No rich blocks
    per Drake's "minimal time and energy" framing.
    """
    deep_link = _GREGORY_CALL_PATH.format(call_id=call_id)
    return (
        f"*{csm_name} / {client_name}*\n"
        f"{summary_text}\n"
        f"<{deep_link}|View in Gregory>"
    )


# ---------------------------------------------------------------------------
# webhook_deliveries audit (mirrors api/airtable_nps_webhook.py pattern)
# ---------------------------------------------------------------------------


def _insert_delivery(
    delivery_id: str,
    *,
    payload: Any,
    status: str,
    error: str | None,
    call_external_id: str | None,
) -> None:
    """Insert the initial audit row. Caught broadly so an audit failure
    never propagates."""
    try:
        from shared.db import get_client

        db = get_client()
        row: dict[str, Any] = {
            "webhook_id": delivery_id,
            "source": _DELIVERY_SOURCE,
            "processing_status": status,
            "payload": payload,
            "headers": {},
            "call_external_id": call_external_id,
        }
        if error is not None:
            row["processing_error"] = error[:2000]
        if status != "received":
            row["processed_at"] = datetime.now(timezone.utc).isoformat()
        db.table("webhook_deliveries").insert(row).execute()
    except Exception as exc:
        logger.warning(
            "cs_call_summary_post: audit row insert failed delivery_id=%s: %s",
            delivery_id,
            exc,
        )


def _mark_delivery(
    delivery_id: str,
    *,
    status: str,
    error: str | None,
) -> None:
    """UPDATE the audit row to a terminal status."""
    try:
        from shared.db import get_client

        db = get_client()
        update: dict[str, Any] = {
            "processing_status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        if error is not None:
            update["processing_error"] = error[:2000]
        db.table("webhook_deliveries").update(update).eq(
            "webhook_id", delivery_id
        ).execute()
    except Exception as exc:
        logger.warning(
            "cs_call_summary_post: audit row update failed delivery_id=%s: %s",
            delivery_id,
            exc,
        )
