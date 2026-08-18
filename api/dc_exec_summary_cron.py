"""Daily DC Ads executive-summary cron (0152).

Vercel Cron POSTs here at 08:15 UTC (4:15am ET DST) — after the ET day has
fully closed — and generates YESTERDAY's exec summary into
dc_ads_exec_summaries via agents/dc_intel/exec_summary.py. The DC Ads page
renders the newest row. Dashboard-only by decision (no Slack delivery).

Idempotent: an existing row for the date skips (re-run with ?force=1 after
a prompt change). Manual runs can target any day with ?date=YYYY-MM-DD.

Auth: shared `CRON_SECRET` Bearer, same as every cron in this project.

Side effects: one Sonnet call (billable, ~$0.02); a webhook_deliveries
audit row per invocation (source='dc_exec_summary').

Manual trigger:
  curl -i -X POST -H "Authorization: Bearer $CRON_SECRET" \\
       "https://ai-enablement-sigma.vercel.app/api/dc_exec_summary_cron?date=2026-08-18&force=1"
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.dc_intel import generate_exec_summary
from shared.db import get_client

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.dc_exec_summary_cron")
logger.setLevel(logging.INFO)

_AUDIT_SOURCE = "dc_exec_summary"
_ET = ZoneInfo("America/New_York")


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            self._handle()
        except Exception:
            logger.exception("dc_exec_summary_cron: unhandled error")
            self._respond(500, {"error": "internal_error"})

    def do_GET(self) -> None:
        self.do_POST()

    def _handle(self) -> None:
        if not _verify_auth(self.headers):
            self._respond(401, {"error": "unauthorized"})
            return
        qs = parse_qs(urlparse(self.path).query)
        for_date = (qs.get("date") or [None])[0] or (
            datetime.now(_ET).date() - timedelta(days=1)
        ).isoformat()
        force = (qs.get("force") or ["0"])[0] == "1"
        self._respond(200, run(for_date, force=force))

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


def run(for_date: str, *, force: bool = False) -> dict[str, Any]:
    db = get_client()
    status, error = "ok", None
    result: dict[str, Any] = {}
    try:
        result = generate_exec_summary(for_date, db=db, force=force)
    except Exception as exc:
        logger.exception("dc_exec_summary_cron: generation failed for %s", for_date)
        status, error = "error", str(exc)[:2000]

    try:
        row: dict[str, Any] = {
            "webhook_id": f"{_AUDIT_SOURCE}_{uuid.uuid4()}",
            "source": _AUDIT_SOURCE,
            "processing_status": status,
            "payload": {"for_date": for_date, "force": force},
            "headers": {},
            "processed_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        }
        if error is not None:
            row["processing_error"] = error
        db.table("webhook_deliveries").insert(row).execute()
    except Exception:
        logger.warning("dc_exec_summary_cron: audit insert failed", exc_info=True)

    return {"status": status, "for_date": for_date, "error": error,
            "skipped": bool(result.get("skipped"))}


def _verify_auth(headers: Any) -> bool:
    expected = os.environ.get("CRON_SECRET") or ""
    if not expected:
        logger.error("dc_exec_summary_cron: CRON_SECRET not configured")
        return False
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth_header.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth_header[len("Bearer ") :], expected)
