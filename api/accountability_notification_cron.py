"""Daily 7am EST accountability notification cron (Batch A — M6.1).

Vercel Cron POSTs here at 12:00 UTC daily (= 7am EST, 8am EDT — per
Drake's call, "off by an hour during DST is fine"). The cron:

  1. Computes "yesterday in EST" via `date.today() - timedelta(days=1)`.
     At 12 UTC the prior calendar day in UTC matches the prior calendar
     day in EST/EDT (since EST = UTC-5, prior day in UTC at 12 UTC =
     prior day in EST at 07 EST). Verified.
  2. Fetches yesterday's accountability submissions from Airtable
     (filterByFormula on the date field, paginates if >100 records),
     extracts + lowercases + strips the Email field per record.
  3. Queries active accountability-enabled clients from Gregory with
     embedded primary_csm join (mirrors api/accountability_roster.py
     eligibility filter, tightened to status='active' AND
     accountability_enabled=true).
  4. Computes the "missing" list (eligible but not in Airtable's set
     of yesterday-submitters), groups by CSM full_name.
  5. Posts one Slack message per CSM (skipping CSMs with empty lists,
     and skipping the entire post step if NO CSM has missing clients).
  6. On Airtable failure: posts a loud failure alert to the same
     channel and returns 500 — partial data is worse than no data.
  7. Logs the run to webhook_deliveries with
     `source='accountability_notification_cron'` so the audit trail
     captures every fire (success and failure both).

Env vars required:

  ACCOUNTABILITY_NOTIFICATION_CRON_AUTH_TOKEN — Vercel Cron Bearer auth
  AIRTABLE_ACCOUNTABILITY_PAT                 — Airtable personal access
                                                token; expires-or-revokes
                                                surface as a loud Slack
                                                alert
  AIRTABLE_ACCOUNTABILITY_BASE_ID             — Airtable base id
                                                (appR566PxMuP71mD6 today)
  AIRTABLE_ACCOUNTABILITY_TABLE_ID            — Airtable table id
                                                (tblmHH0TVpMa0xYTU today)
  SLACK_BOT_TOKEN                             — used by shared.slack_post
  SLACK_CS_ACCOUNTABILITY_CHANNEL_ID          — destination channel
  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY    — shared.db client

Manual trigger for testing:
  curl -i -X POST -H "Authorization: Bearer $ACCOUNTABILITY_NOTIFICATION_CRON_AUTH_TOKEN" \\
       https://ai-enablement-sigma.vercel.app/api/accountability_notification_cron
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

# Make sibling packages importable when Vercel instantiates this handler.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.db import get_client  # noqa: E402
from shared.slack_post import post_message  # noqa: E402

# Vercel's Python runtime defaults the root logger to WARNING; bump to
# INFO so operational lines surface in the Vercel log stream.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.accountability_notification_cron")
logger.setLevel(logging.INFO)

# Audit-row source label. Searchable from SQL; do not change without
# updating any audit dashboards.
_DELIVERY_SOURCE = "accountability_notification_cron"

# Airtable HTTP timeout. Real-world response is well under a second
# but we don't want to wedge the function on a slow upstream.
_AIRTABLE_TIMEOUT_SECONDS = 15


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime instantiates this per request."""

    def do_POST(self) -> None:
        try:
            self._handle()
        except Exception as exc:
            logger.exception(
                "accountability_notification_cron: unhandled top-level error: %s",
                exc,
            )
            self._respond(500, {"error": "internal_error"})

    def do_GET(self) -> None:
        # Same auth + behavior as POST so a manual curl works the same
        # way Vercel Cron's POST does. Mirrors gregory_brain_cron.
        self.do_POST()

    def _handle(self) -> None:
        if not _verify_auth(self.headers):
            self._respond(401, {"error": "unauthorized"})
            return

        result = run_accountability_notification_cron()
        status_code = 500 if result["status"] == "failed" else 200
        self._respond(status_code, result)

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


# ---------------------------------------------------------------------------
# Main flow (testable independently of the HTTP wrapper)
# ---------------------------------------------------------------------------


def run_accountability_notification_cron() -> dict[str, Any]:
    """Run one cron iteration. Returns a structured result dict for the
    HTTP layer to serialize. NEVER raises (last-resort try/except wraps
    each outer step)."""
    delivery_id = f"accountability_notification_{uuid.uuid4()}"
    yesterday = date.today() - timedelta(days=1)
    yesterday_iso = yesterday.isoformat()

    db = get_client()

    # Insert the audit row up front. We update to terminal status at
    # every exit path so missing rows are unambiguous.
    _insert_delivery(
        db,
        delivery_id,
        payload={"date_checked": yesterday_iso, "stage": "starting"},
        status="received",
    )

    # 1. Fetch yesterday's submissions from Airtable. Loud failure path
    # if this fails — Slack alert + 500 + audit row failed.
    try:
        submitted_emails = _fetch_yesterday_submissions(yesterday_iso)
    except Exception as exc:
        error_message = f"airtable_fetch_failed: {type(exc).__name__}: {exc}"
        logger.exception(
            "accountability_notification_cron: airtable fetch failed delivery_id=%s",
            delivery_id,
        )
        _mark_delivery(db, delivery_id, status="failed", error=error_message)
        # Loud Slack alert so the failure isn't silent — Drake sees it
        # in minutes, not days.
        _post_failure_alert(delivery_id, yesterday_iso, error_message)
        return {
            "status": "failed",
            "delivery_id": delivery_id,
            "date_checked": yesterday_iso,
            "error": error_message,
        }

    # 2. Query Gregory for accountability-eligible clients.
    try:
        eligible = _fetch_eligible_clients(db)
    except Exception as exc:
        error_message = f"gregory_query_failed: {type(exc).__name__}: {exc}"
        logger.exception(
            "accountability_notification_cron: gregory query failed delivery_id=%s",
            delivery_id,
        )
        _mark_delivery(db, delivery_id, status="failed", error=error_message)
        _post_failure_alert(delivery_id, yesterday_iso, error_message)
        return {
            "status": "failed",
            "delivery_id": delivery_id,
            "date_checked": yesterday_iso,
            "error": error_message,
        }

    # 3. Compute missing list, group by CSM. Clients with no primary_csm
    # are dropped silently; count surfaces in the audit row so Drake
    # can see if the unassigned-active count grows.
    submitted_set = {e.lower().strip() for e in submitted_emails}
    by_csm: dict[str, list[str]] = {}
    unassigned_missing_count = 0

    for client in eligible:
        client_email = (client.get("email") or "").lower().strip()
        if client_email in submitted_set:
            continue
        csm_name = client.get("csm_full_name")
        client_full_name = client.get("full_name") or "[unknown client]"
        if not csm_name:
            unassigned_missing_count += 1
            continue
        by_csm.setdefault(csm_name, []).append(client_full_name)

    eligible_count = len(eligible)
    submitted_count = len(submitted_set)
    missing_count = sum(len(v) for v in by_csm.values()) + unassigned_missing_count

    # 4. Skip the entire post step if NO CSM has missing clients (per
    # spec: "skip and post nothing — no news is good news"). Audit row
    # still records a clean run.
    if not by_csm:
        _mark_delivery(
            db,
            delivery_id,
            status="processed",
            error=None,
            payload_update={
                "date_checked": yesterday_iso,
                "eligible_count": eligible_count,
                "submitted_count": submitted_count,
                "missing_count": missing_count,
                "unassigned_missing_count": unassigned_missing_count,
                "csms_messaged_ok": [],
                "csms_messaged_failed": [],
                "stage": "no_missing_skipped",
            },
        )
        logger.info(
            "accountability_notification_cron: no missing clients — skipped post "
            "delivery_id=%s eligible=%d submitted=%d unassigned_missing=%d",
            delivery_id,
            eligible_count,
            submitted_count,
            unassigned_missing_count,
        )
        return {
            "status": "ok",
            "delivery_id": delivery_id,
            "date_checked": yesterday_iso,
            "eligible_count": eligible_count,
            "submitted_count": submitted_count,
            "missing_count": missing_count,
            "unassigned_missing_count": unassigned_missing_count,
            "csms_messaged_ok": [],
            "csms_messaged_failed": [],
            "skipped_reason": "no_missing_clients",
        }

    # 5. Post one message per CSM. Per-CSM failure is isolated — log
    # + continue; other CSMs still get their messages.
    channel_id = os.environ.get("SLACK_CS_ACCOUNTABILITY_CHANNEL_ID")
    if not channel_id:
        error_message = "SLACK_CS_ACCOUNTABILITY_CHANNEL_ID not set"
        logger.error(
            "accountability_notification_cron: %s delivery_id=%s",
            error_message,
            delivery_id,
        )
        _mark_delivery(db, delivery_id, status="failed", error=error_message)
        return {
            "status": "failed",
            "delivery_id": delivery_id,
            "date_checked": yesterday_iso,
            "error": error_message,
        }

    csms_ok: list[str] = []
    csms_failed: list[dict[str, Any]] = []
    for csm_name in sorted(by_csm.keys()):
        clients_missing = by_csm[csm_name]
        text = _format_csm_message(
            csm_name=csm_name,
            yesterday_iso=yesterday_iso,
            clients_missing=clients_missing,
        )
        result = post_message(channel_id, text)
        if result["ok"]:
            csms_ok.append(csm_name)
        else:
            csms_failed.append(
                {"csm": csm_name, "slack_error": result.get("slack_error")}
            )

    # 6. Mark audit row processed with the full per-CSM breakdown.
    _mark_delivery(
        db,
        delivery_id,
        status="processed" if not csms_failed else "failed",
        error=None
        if not csms_failed
        else f"slack_post_failed_for_some_csms: {csms_failed}",
        payload_update={
            "date_checked": yesterday_iso,
            "eligible_count": eligible_count,
            "submitted_count": submitted_count,
            "missing_count": missing_count,
            "unassigned_missing_count": unassigned_missing_count,
            "csms_messaged_ok": csms_ok,
            "csms_messaged_failed": csms_failed,
            "stage": "complete",
        },
    )
    logger.info(
        "accountability_notification_cron: complete delivery_id=%s "
        "eligible=%d submitted=%d missing=%d unassigned_missing=%d "
        "csms_ok=%d csms_failed=%d",
        delivery_id,
        eligible_count,
        submitted_count,
        missing_count,
        unassigned_missing_count,
        len(csms_ok),
        len(csms_failed),
    )
    return {
        "status": "ok" if not csms_failed else "partial_failure",
        "delivery_id": delivery_id,
        "date_checked": yesterday_iso,
        "eligible_count": eligible_count,
        "submitted_count": submitted_count,
        "missing_count": missing_count,
        "unassigned_missing_count": unassigned_missing_count,
        "csms_messaged_ok": csms_ok,
        "csms_messaged_failed": csms_failed,
    }


# ---------------------------------------------------------------------------
# Airtable fetch
# ---------------------------------------------------------------------------


def _fetch_yesterday_submissions(yesterday_iso: str) -> list[str]:
    """Page through Airtable's accountability table for rows where
    `What date is this for?` equals yesterday_iso. Returns a list of
    email strings (raw — caller lowercases + strips at matching time).

    Raises on transport-level failure or missing env vars."""
    pat = os.environ.get("AIRTABLE_ACCOUNTABILITY_PAT")
    base_id = os.environ.get("AIRTABLE_ACCOUNTABILITY_BASE_ID")
    table_id = os.environ.get("AIRTABLE_ACCOUNTABILITY_TABLE_ID")
    if not pat or not base_id or not table_id:
        raise RuntimeError(
            "missing env: AIRTABLE_ACCOUNTABILITY_PAT / "
            "AIRTABLE_ACCOUNTABILITY_BASE_ID / "
            "AIRTABLE_ACCOUNTABILITY_TABLE_ID"
        )

    formula = f"{{What date is this for?}} = '{yesterday_iso}'"
    base_url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {
        "Authorization": f"Bearer {pat}",
        "Content-Type": "application/json",
    }

    emails: list[str] = []
    offset: str | None = None
    page = 0
    while True:
        page += 1
        params = {"filterByFormula": formula, "pageSize": "100"}
        if offset:
            params["offset"] = offset
        url = f"{base_url}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(
            req, timeout=_AIRTABLE_TIMEOUT_SECONDS
        ) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)

        records = parsed.get("records") or []
        for record in records:
            fields = record.get("fields") or {}
            email_value = fields.get("Email")
            if isinstance(email_value, str) and email_value.strip():
                emails.append(email_value)

        offset = parsed.get("offset")
        if not offset:
            break
        # Defensive break — Airtable shouldn't return >5 pages of
        # accountability submissions in a single day at our scale; cap
        # the loop so a runaway pagination doesn't wedge the cron.
        if page > 20:
            logger.warning(
                "accountability_notification_cron: airtable pagination cap hit "
                "at %d pages — stopping",
                page,
            )
            break

    return emails


# ---------------------------------------------------------------------------
# Gregory eligibility query
# ---------------------------------------------------------------------------


def _fetch_eligible_clients(db) -> list[dict[str, Any]]:
    """Query active accountability-enabled clients with their primary
    CSM. Returns a list of dicts with `email`, `full_name`,
    `csm_full_name` (None when no active primary_csm).

    Mirrors api/accountability_roster.py's filter shape: select clients
    + embedded client_team_assignments + team_members.
    """
    resp = (
        db.table("clients")
        .select(
            "id,"
            "email,"
            "full_name,"
            "client_team_assignments("
            "role,unassigned_at,team_members(full_name)"
            ")"
        )
        .is_("archived_at", "null")
        .eq("status", "active")
        .eq("accountability_enabled", True)
        .execute()
    )
    rows = resp.data or []

    eligible: list[dict[str, Any]] = []
    for row in rows:
        email = row.get("email")
        if not email:
            continue
        eligible.append(
            {
                "id": row.get("id"),
                "email": email,
                "full_name": row.get("full_name"),
                "csm_full_name": _select_active_primary_csm_full_name(
                    row.get("client_team_assignments")
                ),
            }
        )
    return eligible


def _select_active_primary_csm_full_name(assignments: Any) -> str | None:
    """Pick the full_name of the active primary_csm from the embedded
    client_team_assignments list. Mirrors
    api/accountability_roster.py:_select_advisor_first_name's
    pre-derivation logic."""
    if not assignments or not isinstance(assignments, list):
        return None
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        if assignment.get("role") != "primary_csm":
            continue
        if assignment.get("unassigned_at") is not None:
            continue
        team_member = assignment.get("team_members")
        if not isinstance(team_member, dict):
            continue
        full_name = team_member.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            return full_name.strip()
    return None


# ---------------------------------------------------------------------------
# Slack message formatting
# ---------------------------------------------------------------------------


def _format_csm_message(
    *,
    csm_name: str,
    yesterday_iso: str,
    clients_missing: list[str],
) -> str:
    """Build the per-CSM Slack message.

    First name extraction: split on whitespace, take first token,
    `.capitalize()`. Mirrors the M5.8 Path 2 advisor_first_name pattern
    in api/accountability_roster.py — internal-cap names like "DeShawn"
    will become "Deshawn"; current CSM roster (Lou / Nico / Scott /
    Nabeel) is clean so this is acceptable today.
    """
    first_name = csm_name.split()[0].capitalize() if csm_name else csm_name
    bullet_lines = "\n".join(f"- {name}" for name in clients_missing)
    return (
        f"{first_name} — these clients didn't submit accountability "
        f"yesterday ({yesterday_iso}):\n"
        f"{bullet_lines}"
    )


def _post_failure_alert(
    delivery_id: str, yesterday_iso: str, error_message: str
) -> None:
    """Post a loud failure alert to the accountability channel when
    the cron itself failed (Airtable down, Gregory query broken,
    misconfiguration). Wrapped in try/except — if the failure-alert
    post ALSO fails, log + continue (we already returned 500 to the
    caller with the audit_id; Drake can grep webhook_deliveries)."""
    try:
        channel_id = os.environ.get("SLACK_CS_ACCOUNTABILITY_CHANNEL_ID")
        if not channel_id:
            return
        text = (
            f":warning: accountability cron failed for {yesterday_iso} — "
            f"see webhook_deliveries.webhook_id={delivery_id}\n"
            f"```{error_message[:1500]}```"
        )
        post_message(channel_id, text)
    except Exception as exc:
        logger.warning(
            "accountability_notification_cron: failure-alert post raised: %s",
            exc,
        )


# ---------------------------------------------------------------------------
# webhook_deliveries audit
# ---------------------------------------------------------------------------


def _insert_delivery(
    db,
    delivery_id: str,
    *,
    payload: Any,
    status: str,
) -> None:
    """Insert the initial audit row. Caught broadly — an audit insert
    failure must not propagate into the main flow."""
    try:
        row: dict[str, Any] = {
            "webhook_id": delivery_id,
            "source": _DELIVERY_SOURCE,
            "processing_status": status,
            "payload": payload,
            "headers": {},
        }
        db.table("webhook_deliveries").insert(row).execute()
    except Exception as exc:
        logger.warning(
            "accountability_notification_cron: audit insert failed delivery_id=%s: %s",
            delivery_id,
            exc,
        )


def _mark_delivery(
    db,
    delivery_id: str,
    *,
    status: str,
    error: str | None,
    payload_update: dict[str, Any] | None = None,
) -> None:
    """UPDATE the audit row to a terminal status. If `payload_update`
    is given, replaces the payload (jsonb-typed; we re-write the
    structured shape with eligibility counts + per-CSM breakdown)."""
    try:
        update: dict[str, Any] = {
            "processing_status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        if error is not None:
            update["processing_error"] = error[:2000]
        if payload_update is not None:
            update["payload"] = payload_update
        db.table("webhook_deliveries").update(update).eq(
            "webhook_id", delivery_id
        ).execute()
    except Exception as exc:
        logger.warning(
            "accountability_notification_cron: audit update failed delivery_id=%s: %s",
            delivery_id,
            exc,
        )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _verify_auth(headers: Any) -> bool:
    """Bearer-token auth. Mirrors gregory_brain_cron's pattern; per-
    source-prefixed env var name lets cron secrets rotate independently."""
    expected = os.environ.get("ACCOUNTABILITY_NOTIFICATION_CRON_AUTH_TOKEN") or ""
    if not expected:
        logger.error(
            "accountability_notification_cron: "
            "ACCOUNTABILITY_NOTIFICATION_CRON_AUTH_TOKEN not configured"
        )
        return False
    auth_header = (
        headers.get("Authorization") or headers.get("authorization") or ""
    )
    if not auth_header.startswith("Bearer "):
        return False
    presented = auth_header[len("Bearer ") :]
    return hmac.compare_digest(presented, expected)
