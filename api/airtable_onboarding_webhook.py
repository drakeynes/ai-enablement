"""Airtable onboarding webhook endpoint (Path 3 inbound).

Deployed by Vercel as a serverless Python function at
`/api/airtable_onboarding_webhook`. Make.com fires deliveries here when
Zain's existing onboarding flow (Slack channel created → client invited
→ form submitted) completes for a new client. Receiver is a thin
adapter — validate auth + payload, hand off to
`create_or_update_client_from_onboarding` (migration 0025) which does
the match-or-create work in one transaction.

Full architecture: docs/agents/gregory.md § "Airtable onboarding integration".

Sync flow (mirrors api/airtable_nps_webhook.py):

  1. Validate AIRTABLE_ONBOARDING_WEBHOOK_SECRET env var is set.
     Missing → 500 (deploy misconfiguration). Fail loud BEFORE the
     header check so a missing env var doesn't masquerade as a 401.

  2. Validate X-Webhook-Secret header via hmac.compare_digest
     (constant-time). Missing or mismatch → 401, no DB write.

  3. Read body bytes, parse JSON.
     Malformed JSON → 400 + webhook_deliveries row marked 'malformed'.

  4. Validate payload fields. 4 required (full_name, email, country,
     date_joined) + 3 optional (phone, slack_user_id, slack_channel_id).
     Required: non-null, string-typed, non-empty after strip → missing
     or empty fails 400 missing_field. Optional: absent or null passes
     through as None; if PRESENT, must be string-typed AND non-empty
     after strip (rejecting "" as wrong_type so Make.com mapping bugs
     don't silently coerce). date_joined parsed to a date.

  5. Generate webhook_id = "airtable_onboarding_<uuid4>". Insert
     webhook_deliveries row (status='received').

  6. Call create_or_update_client_from_onboarding RPC. RPC's structured
     RAISE EXCEPTION strings translate to:
       'slack_user_id_conflict'                       → 409
       'slack_channel_id_conflict_for_client'         → 409
       'slack_channel_id_owned_by_different_client'   → 409
     Anything else → 500 + 'failed'.

  7. Mark webhook_deliveries row 'processed', return 200 with the
     {status, delivery_id, client_id, action} response shape.

Env vars required (set in Vercel Production scope, NOT committed):

  AIRTABLE_ONBOARDING_WEBHOOK_SECRET   — shared secret with Make.com
  SUPABASE_URL                         — shared.db
  SUPABASE_SERVICE_ROLE_KEY            — shared.db

Payload shape (from Make.com):

  {
    "full_name":        "Jane Doe",         # required
    "email":            "jane@example.com", # required
    "country":          "USA",              # required
    "date_joined":      "2026-05-05" or "2026-05-05T14:30:00Z",  # required
    "phone":            "+1 555-123-4567",  # optional (omit or null)
    "slack_user_id":    "U01ABC123",        # optional (omit or null)
    "slack_channel_id": "C01ABC456"         # optional (omit or null)
  }

  Optional fields support a re-fire flow: Zain runs onboarding for a
  new client without slack IDs in hand → client lands in Gregory →
  later re-runs the same form with slack IDs filled in → client
  updates in place (NULL-only backfill on slack_user_id, fresh
  slack_channels INSERT via the RPC's Branch C).

Response shape (200 OK):

  {
    "status": "ok",
    "delivery_id": "airtable_onboarding_<uuid4>",
    "client_id": "<uuid>",
    "action": "created" | "updated" | "reactivated"
  }

NOTE on conflict-error pattern matching: the RPC raises three distinct
slack-conflict messages with shared substrings. Order of substring
checks below is significant — `slack_channel_id_owned_by_different_client`
must be checked BEFORE `slack_channel_id_conflict_for_client` to avoid
the longer string being misclassified by its shorter prefix.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import traceback
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any

from shared.db import get_client


# Vercel's Python runtime defaults the root logger to WARNING; INFO is
# what we want for operational lines. Same workaround as
# api/airtable_nps_webhook.py.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.airtable_onboarding_webhook")
logger.setLevel(logging.INFO)


# Cap for stored error strings on webhook_deliveries.processing_error.
_MAX_ERROR_CHARS = 2000

# Headers preserved in webhook_deliveries.headers. X-Webhook-Secret is
# the auth header — NEVER stored.
_HEADERS_TO_STORE = frozenset({
    "content-type",
    "content-length",
    "user-agent",
})

# Required string fields. Validated as non-null + string-typed +
# non-empty after strip. date_joined gets a separate parse step.
_REQUIRED_STRING_FIELDS: tuple[str, ...] = (
    "full_name",
    "email",
    "country",
    "date_joined",
)

# Optional string fields. Absent or null passes through as None. If
# PRESENT, must be string-typed AND non-empty after strip — i.e., the
# caller must not send `""` to mean "blank" (use null instead). This
# keeps the contract strict at the boundary while allowing the re-fire
# flow described in the module docstring.
_OPTIONAL_STRING_FIELDS: tuple[str, ...] = (
    "phone",
    "slack_user_id",
    "slack_channel_id",
)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime instantiates this per request."""

    def do_POST(self) -> None:
        try:
            self._handle_post()
        except Exception as exc:  # last-resort safety net
            logger.exception(
                "airtable_onboarding_webhook: unhandled top-level error: %s",
                exc,
            )
            self._respond(500, {"error": "internal_error"})

    def do_GET(self) -> None:
        # Friendly hint for browser / uptime-check hits + post-deploy
        # smoke verification. Same shape as api/airtable_nps_webhook.py.
        self._respond(
            200,
            {
                "status": "ok",
                "endpoint": "airtable_onboarding_webhook",
                "accepts": "POST",
            },
        )

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def _handle_post(self) -> None:
        # 1. Misconfiguration check FIRST. A missing env var is our bug,
        #    not the caller's; surface as 500 not 401.
        secret = os.environ.get("AIRTABLE_ONBOARDING_WEBHOOK_SECRET")
        if not secret:
            logger.error(
                "airtable_onboarding_webhook: "
                "AIRTABLE_ONBOARDING_WEBHOOK_SECRET not configured"
            )
            self._respond(500, {"error": "misconfigured"})
            return

        # 2. Auth gate. Compare via hmac.compare_digest for constant time.
        #    No webhook_deliveries row written for 401s — gate-before-DB.
        provided = self.headers.get("X-Webhook-Secret", "") or ""
        if not provided or not hmac.compare_digest(provided, secret):
            logger.warning(
                "airtable_onboarding_webhook: unauthorized — header_present=%s",
                bool(provided),
            )
            self._respond(401, {"error": "unauthorized"})
            return

        # From here on every exit path writes a webhook_deliveries row.
        body = self._read_body()
        delivery_id = f"airtable_onboarding_{uuid.uuid4()}"
        sanitized_headers = _sanitize_headers(self.headers)

        # 3. Parse JSON.
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(
                "airtable_onboarding_webhook: body not valid JSON: %s", exc
            )
            _insert_delivery(
                delivery_id,
                payload=None,
                headers=sanitized_headers,
                status="malformed",
                error=f"invalid_json: {exc}",
            )
            self._respond(400, {"error": "invalid_json"})
            return

        if not isinstance(payload, dict):
            logger.warning(
                "airtable_onboarding_webhook: body not a JSON object (got %s)",
                type(payload).__name__,
            )
            _insert_delivery(
                delivery_id,
                payload=payload,
                headers=sanitized_headers,
                status="malformed",
                error="payload_not_object",
            )
            self._respond(400, {"error": "payload_not_object"})
            return

        # 4. Validate required fields.
        validation_error = _validate_payload(payload)
        if validation_error is not None:
            error_code, detail = validation_error
            logger.warning(
                "airtable_onboarding_webhook: %s — %s", error_code, detail
            )
            _insert_delivery(
                delivery_id,
                payload=payload,
                headers=sanitized_headers,
                status="malformed",
                error=f"{error_code}: {detail}",
            )
            self._respond(400, {"error": error_code, "detail": detail})
            return

        # Parse date_joined to a date (ISO date or ISO datetime supported).
        try:
            start_date = _parse_date_joined(payload["date_joined"])
        except ValueError as exc:
            logger.warning(
                "airtable_onboarding_webhook: date_joined unparseable — %s", exc
            )
            _insert_delivery(
                delivery_id,
                payload=payload,
                headers=sanitized_headers,
                status="malformed",
                error=f"wrong_type: date_joined: {exc}",
            )
            self._respond(
                400,
                {
                    "error": "wrong_type",
                    "detail": f"date_joined: {exc}",
                },
            )
            return

        # 5. Insert the 'received' delivery row.
        _insert_delivery(
            delivery_id,
            payload=payload,
            headers=sanitized_headers,
            status="received",
            error=None,
        )

        # 6. Call the RPC. Optional fields pass through as null when
        #    absent or null in the payload. The RPC's null guards on the
        #    slack_* anti-overwrite checks + the wrapped six-branch
        #    block handle the rest.
        db = get_client()
        try:
            rpc_resp = db.rpc(
                "create_or_update_client_from_onboarding",
                {
                    "p_full_name": payload["full_name"].strip(),
                    "p_email": payload["email"].strip(),
                    "p_phone": _optional_field(payload, "phone"),
                    "p_country": payload["country"].strip(),
                    "p_start_date": start_date.isoformat(),
                    "p_slack_user_id": _optional_field(payload, "slack_user_id"),
                    "p_slack_channel_id": _optional_field(
                        payload, "slack_channel_id"
                    ),
                    "p_delivery_id": delivery_id,
                },
            ).execute()
        except Exception as exc:
            error_message = str(exc)
            tb = _sanitize_traceback(traceback.format_exc())

            # Conflict-error pattern matching. Order matters — the
            # `_owned_by_different_client` string contains the shorter
            # `_conflict_for_client` substring is NOT a hazard (different
            # tail), but checking the longer / more specific message
            # first is the safer convention as the message set grows.
            if "slack_channel_id_owned_by_different_client" in error_message:
                conflict = "slack_channel_id_owned_by_different_client"
            elif "slack_channel_id_conflict_for_client" in error_message:
                conflict = "slack_channel_id_conflict_for_client"
            elif "slack_user_id_conflict" in error_message:
                conflict = "slack_user_id_conflict"
            else:
                conflict = None

            if conflict is not None:
                logger.warning(
                    "airtable_onboarding_webhook: %s — delivery_id=%s",
                    conflict,
                    delivery_id,
                )
                _mark_delivery(
                    delivery_id,
                    status="failed",
                    error=error_message[:_MAX_ERROR_CHARS],
                )
                self._respond(
                    409,
                    {
                        "error": conflict,
                        "detail": _extract_conflict_detail(error_message),
                    },
                )
                return

            logger.exception(
                "airtable_onboarding_webhook: RPC raised — delivery_id=%s",
                delivery_id,
            )
            _mark_delivery(delivery_id, status="failed", error=tb)
            self._respond(500, {"error": "rpc_failed"})
            return

        # 7. Success.
        returned = rpc_resp.data
        if not returned:
            logger.error(
                "airtable_onboarding_webhook: RPC returned no data — "
                "delivery_id=%s",
                delivery_id,
            )
            _mark_delivery(
                delivery_id,
                status="failed",
                error="rpc_returned_no_data",
            )
            self._respond(500, {"error": "rpc_returned_no_data"})
            return

        # The RPC returns a jsonb object. Supabase-py wraps it in
        # rpc_resp.data which can be the dict directly, or a list of one
        # depending on the supabase client version. Handle both shapes.
        if isinstance(returned, list):
            result = returned[0] if returned else {}
        else:
            result = returned
        client_id = result.get("client_id")
        action = result.get("action")

        _mark_delivery(delivery_id, status="processed", error=None)

        logger.info(
            "airtable_onboarding_webhook: processed delivery_id=%s "
            "client_id=%s action=%s",
            delivery_id,
            client_id,
            action,
        )

        self._respond(
            200,
            {
                "status": "ok",
                "delivery_id": delivery_id,
                "client_id": client_id,
                "action": action,
            },
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return b""
        return self.rfile.read(length) if length > 0 else b""

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_payload(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Validate the payload. Returns (error_code, detail) on failure or
    None on success.

    Required fields: non-null, string-typed, non-empty after strip.
    Optional fields: absent or null is fine; if present, must be
    string-typed AND non-empty after strip. We reject `""` for optional
    fields rather than coercing to null because Make.com mapping bugs
    that produce `""` are an operator error worth surfacing, not
    silently fixing.

    date_joined parsing happens in a separate step so the error code
    can distinguish missing-field from unparseable-date.
    """
    for field in _REQUIRED_STRING_FIELDS:
        value = payload.get(field)
        if value is None:
            return ("missing_field", f"{field} is required")
        if not isinstance(value, str):
            return (
                "wrong_type",
                f"{field} must be a string, got {type(value).__name__}",
            )
        if not value.strip():
            return ("missing_field", f"{field} cannot be empty")

    for field in _OPTIONAL_STRING_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if value is None:
            continue
        if not isinstance(value, str):
            return (
                "wrong_type",
                f"{field} must be a string or null, got {type(value).__name__}",
            )
        if not value.strip():
            return (
                "wrong_type",
                f"{field} must be non-empty when present (use null to omit)",
            )
    return None


def _optional_field(payload: dict[str, Any], field: str) -> str | None:
    """Return the stripped value for an optional payload field, or None
    when the field is absent / null. Validation already ensured a
    present-non-null value is a non-empty string."""
    value = payload.get(field)
    if value is None:
        return None
    return value.strip()


def _parse_date_joined(raw: str) -> date:
    """Accept ISO date ('2026-05-05') or full ISO timestamp
    ('2026-05-05T14:30:00Z'). Returns a date for storage in
    clients.start_date. Raises ValueError on unparseable input."""
    raw = raw.strip()
    # Try plain date first.
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    # Fall through to datetime parsing. Replace trailing Z (Python <3.11
    # fromisoformat couldn't handle it; 3.11+ can, but explicit replacement
    # is harmless and version-agnostic).
    cleaned = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError as exc:
        raise ValueError(
            f"unparseable date_joined value {raw!r} "
            f"(expected ISO date or ISO datetime)"
        ) from exc


def _extract_conflict_detail(error_message: str) -> str:
    """Pull the conflict detail (existing/new values) out of the RPC's
    raised message. Best-effort — surfaces what the RPC said after the
    error code prefix. Falls back to the raw message if the format
    doesn't match."""
    # RPC raises strings like 'slack_user_id_conflict: existing=U1 new=U2'
    # or 'slack_channel_id_owned_by_different_client: client_id=<uuid>'.
    # Postgres error wrappers often prefix with their own metadata.
    # Find the conflict code, return everything after the first ':'.
    for marker in (
        "slack_channel_id_owned_by_different_client:",
        "slack_channel_id_conflict_for_client:",
        "slack_user_id_conflict:",
    ):
        idx = error_message.find(marker)
        if idx >= 0:
            tail = error_message[idx + len(marker):].strip()
            # Trim trailing CONTEXT/HINT lines if present.
            tail = tail.split("\n", 1)[0].strip()
            return tail
    return error_message[:200]


# ---------------------------------------------------------------------------
# webhook_deliveries lifecycle helpers
# ---------------------------------------------------------------------------


def _insert_delivery(
    delivery_id: str,
    *,
    payload: Any,
    headers: dict[str, str],
    status: str,
    error: str | None,
) -> None:
    """Insert the initial delivery row. Status can be 'received' (happy
    path UPDATEs later) or 'malformed' (terminal, no UPDATE)."""
    db = get_client()
    row: dict[str, Any] = {
        "webhook_id": delivery_id,
        "source": "airtable_onboarding_webhook",
        "processing_status": status,
        "payload": payload,
        "headers": headers,
    }
    if error is not None:
        row["processing_error"] = error[:_MAX_ERROR_CHARS]
    if status != "received":
        row["processed_at"] = datetime.now(timezone.utc).isoformat()
    db.table("webhook_deliveries").insert(row).execute()


def _mark_delivery(
    delivery_id: str,
    *,
    status: str,
    error: str | None,
) -> None:
    """UPDATE a previously-inserted delivery row to a terminal status."""
    db = get_client()
    update: dict[str, Any] = {
        "processing_status": status,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    if error is not None:
        update["processing_error"] = error[:_MAX_ERROR_CHARS]
    db.table("webhook_deliveries").update(update).eq(
        "webhook_id", delivery_id
    ).execute()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _sanitize_headers(headers: Any) -> dict[str, str]:
    """Preserve only the safe debugging headers. X-Webhook-Secret is
    NEVER included. Lower-case the keys for predictable querying."""
    out: dict[str, str] = {}
    for key in _HEADERS_TO_STORE:
        val = headers.get(key)
        if val is not None:
            out[key] = str(val)
    return out


def _sanitize_traceback(tb: str) -> str:
    """Trim the traceback before persisting to the DB. Filters out lines
    containing common secret prefixes — belt-and-suspenders."""
    if not tb:
        return ""
    lines = tb.splitlines()
    filtered = [
        line
        for line in lines
        if "whsec_" not in line and "sk-" not in line and "eyJh" not in line
    ]
    return "\n".join(filtered)[:_MAX_ERROR_CHARS]
