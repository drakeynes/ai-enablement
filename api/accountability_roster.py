"""Accountability + NPS daily roster endpoint (Path 2 outbound).

Deployed by Vercel as a serverless Python function at
`/api/accountability_roster`. Make.com hits this once per day to pull
the current roster of active non-archived clients with the fields it
needs to drive the accountability + NPS automations that previously
ran off the Financial Master Sheet. Replaces the master sheet as Zain's
source of truth for those scenarios.

Full architecture: docs/agents/gregory.md § "Path 2 outbound roster".

Auth flow (mirrors api/airtable_nps_webhook.py):

  1. Validate MAKE_OUTBOUND_ROSTER_SECRET env var is set.
     Missing → 500 (deploy misconfiguration). Fail loud BEFORE the
     header check so a missing env var doesn't masquerade as a 401.

  2. Validate X-Webhook-Secret header via hmac.compare_digest
     (constant-time). Missing or mismatch → 401, no DB read — same
     gate-before-DB pattern as the Path 1 receiver.

  3. Single SELECT on clients with embedded slack_channels join.
     Filter applied per-client in Python (mirrors getClientById's
     slack_channel selection: most recently created non-archived
     channel). Round-trip count is 1.

  4. Filter rows server-side. Every client in the response has BOTH
     a non-null slack_user_id AND a resolvable slack_channel_id. The
     contract is: every row is actionable by the automation.

  5. Return the roster.

Eligibility (no status filter — let the booleans speak; Make.com
filters on its side based on accountability_enabled / nps_enabled):

  - clients.archived_at IS NULL
  - clients.slack_user_id IS NOT NULL
  - at least one slack_channels row with is_archived=false (most
    recently created wins, matching getClientById)

Env vars required (set in Vercel Production scope, NOT committed):

  MAKE_OUTBOUND_ROSTER_SECRET   — shared secret with Make.com
  SUPABASE_URL                  — shared.db
  SUPABASE_SERVICE_ROLE_KEY     — shared.db

Response shape (200 OK):

  {
    "generated_at": "<ISO8601 UTC>",
    "count": <int>,
    "clients": [
      {
        "client_email": "...",
        "full_name": "...",
        "slack_user_id": "U...",
        "slack_channel_id": "C...",
        "accountability_enabled": <bool>,
        "nps_enabled": <bool>
      },
      ...
    ]
  }

Note on filtered-out clients: rows excluded server-side (NULL
slack_user_id, or no resolvable slack_channel_id) silently disappear
from Make.com's scope. That's intentional — the master-sheet predecessor
left those rows visible and forced Zain to skip them on the Make.com
side. Centralizing the filter here is the cleaner contract. If a
"diagnostic / counts-only" mode is wanted later, add a query param
without changing the default response shape.

Note on slack_channels staleness: this endpoint trusts our
slack_channels table; we don't reconcile against Slack's live archive
state. A channel archived on Slack's side but still is_archived=false
here will surface a slack_channel_id Make.com then fails to post to.
Followup logged.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any

from shared.db import get_client


# Vercel's Python runtime defaults the root logger to WARNING; INFO is
# what we want for operational lines. Same workaround as
# api/airtable_nps_webhook.py.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.accountability_roster")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime instantiates this per request."""

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except Exception as exc:  # last-resort safety net
            logger.exception(
                "accountability_roster: unhandled top-level error: %s", exc
            )
            self._respond(500, {"error": "internal_error"})

    def do_POST(self) -> None:
        # Spec'd: only GET is allowed. PUT/DELETE/PATCH naturally return
        # 501 from BaseHTTPRequestHandler — close enough to "not allowed"
        # without enumerating every verb.
        self._respond(405, {"error": "method_not_allowed"})

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def _handle_get(self) -> None:
        # 1. Misconfiguration check FIRST. A missing env var is our bug,
        #    not the caller's; surface as 500 not 401.
        secret = os.environ.get("MAKE_OUTBOUND_ROSTER_SECRET")
        if not secret:
            logger.error(
                "accountability_roster: MAKE_OUTBOUND_ROSTER_SECRET not configured"
            )
            self._respond(500, {"error": "server_misconfigured"})
            return

        # 2. Auth gate. Compare via hmac.compare_digest for constant time.
        provided = self.headers.get("X-Webhook-Secret", "") or ""
        if not provided or not hmac.compare_digest(provided, secret):
            logger.warning(
                "accountability_roster: unauthorized — header_present=%s",
                bool(provided),
            )
            # Per spec: 401, no body.
            self.send_response(401)
            self.end_headers()
            return

        # 3. Single round-trip query: clients + embedded slack_channels.
        try:
            db = get_client()
            resp = (
                db.table("clients")
                .select(
                    "email,"
                    "full_name,"
                    "slack_user_id,"
                    "accountability_enabled,"
                    "nps_enabled,"
                    "slack_channels(slack_channel_id,is_archived,created_at)"
                )
                .is_("archived_at", "null")
                .execute()
            )
        except Exception:
            logger.exception("accountability_roster: db query failed")
            self._respond(500, {"error": "query_failed"})
            return

        rows = resp.data or []

        # 4. Apply per-client eligibility. Mirror getClientById's
        # slack_channel selection: filter is_archived=false, sort by
        # created_at desc, take the first. Drop clients with NULL
        # slack_user_id or no resolvable channel — every row in the
        # response is actionable.
        clients_payload: list[dict[str, Any]] = []
        for row in rows:
            slack_user_id = row.get("slack_user_id")
            if not slack_user_id:
                continue
            slack_channel_id = _select_active_channel(row.get("slack_channels"))
            if slack_channel_id is None:
                continue
            client_email = row.get("email")
            if not client_email:
                # Master-sheet replacement: Make.com keys on email. A
                # client with no email isn't useful to surface even if
                # all other fields resolve. Rare-to-impossible in
                # practice (197 active clients all have emails today)
                # but defensive against future seed/import edge cases.
                continue
            clients_payload.append(
                {
                    "client_email": client_email,
                    "full_name": row.get("full_name"),
                    "slack_user_id": slack_user_id,
                    "slack_channel_id": slack_channel_id,
                    "accountability_enabled": bool(
                        row.get("accountability_enabled", False)
                    ),
                    "nps_enabled": bool(row.get("nps_enabled", False)),
                }
            )

        body = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(clients_payload),
            "clients": clients_payload,
        }

        logger.info(
            "accountability_roster: served roster — total_rows=%d "
            "actionable_count=%d",
            len(rows),
            len(clients_payload),
        )
        self._respond(200, body)

    # ------------------------------------------------------------------
    # HTTP helpers (mirror api/airtable_nps_webhook.py)
    # ------------------------------------------------------------------

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _select_active_channel(channels: Any) -> str | None:
    """Mirror getClientById's slack_channel selection logic exactly:
    filter is_archived=false, sort by created_at desc, take the first
    slack_channel_id. Returns None if no qualifying row.

    Keeping the rule in one helper so a future change to the contract
    (e.g., "prefer the channel where ella_enabled=true") stays out of
    the request handler."""
    if not channels:
        return None
    if not isinstance(channels, list):
        return None
    active = [
        c for c in channels if isinstance(c, dict) and not c.get("is_archived", False)
    ]
    if not active:
        return None
    active.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    return active[0].get("slack_channel_id")
