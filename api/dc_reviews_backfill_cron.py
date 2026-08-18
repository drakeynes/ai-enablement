"""DC review-rubric backfill cron (TEMPORARY — remove the schedule when done).

Nabeel verified the v3 dc_ads review output and approved the backfill
(2026-08-18): the ~460 DC-cohort calls reviewed before migration 0150 carry
wrong-rubric (book) grades and are invisible to the dashboard. Each tick
re-grades a batch with force=True — transcripts are already stored, so this
is Sonnet-only (~$0.02/call, ~$9 for the whole queue).

Per tick:
  1. Auth: `Authorization: Bearer ${CRON_SECRET}` (Vercel injects it for
     scheduled invocations).
  2. `dc_ads_backfill_candidates(batch)` (migration 0153) → the newest
     still-wrong calls. The queue provably drains: a successful re-grade
     flips call_type to 'dc_ads' and the row leaves the queue.
  3. `review_call(id, force=True, post_to_slack=False)` each — Slack stays
     quiet (these calls already posted under the old rubric; the row's
     slack_message_ts also makes any post idempotent).
  4. Audit row to webhook_deliveries (source='dc_reviews_backfill') with
     counts; the HTTP response carries the same summary + remaining count.

Batch 20 × ~6-10s/review ≈ 120-200s, inside the 300s budget; the */5
schedule finishes ~460 calls in ~2 hours. When `remaining` reads 0, delete
this cron's schedule entry in vercel.json (keep the endpoint for any future
rubric migration — it no-ops on an empty queue).

Manual trigger:
  curl -i -X POST -H "Authorization: Bearer $CRON_SECRET" \\
       "https://ai-enablement-sigma.vercel.app/api/dc_reviews_backfill_cron?batch=5"
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.setter_call_reviewer import ReviewError, review_call
from shared.db import get_client

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.dc_reviews_backfill_cron")
logger.setLevel(logging.INFO)

_AUDIT_SOURCE = "dc_reviews_backfill"
_DEFAULT_BATCH = 20


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            self._handle()
        except Exception:
            logger.exception("dc_reviews_backfill_cron: unhandled error")
            self._respond(500, {"error": "internal_error"})

    def do_GET(self) -> None:
        self.do_POST()

    def _handle(self) -> None:
        if not _verify_auth(self.headers):
            self._respond(401, {"error": "unauthorized"})
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            batch = int((qs.get("batch") or [str(_DEFAULT_BATCH)])[0])
        except ValueError:
            batch = _DEFAULT_BATCH
        self._respond(200, run(batch))

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


def run(batch: int) -> dict[str, Any]:
    db = get_client()
    ids = [
        r if isinstance(r, str) else r.get("dc_ads_backfill_candidates")
        for r in (db.rpc("dc_ads_backfill_candidates", {"p_limit": batch}).execute().data or [])
    ]
    regraded: list[str] = []
    failed: list[dict[str, str]] = []
    cost_usd = 0.0
    for close_id in ids:
        try:
            row = review_call(close_id, db=db, force=True, post_to_slack=False)
            regraded.append(close_id)
            try:
                cost_usd += float(row.get("sonnet_cost_usd") or 0)
            except (TypeError, ValueError):
                pass
            logger.info(
                "dc_reviews_backfill.regraded close_id=%s type=%s",
                close_id, row.get("call_type"),
            )
        except ReviewError as e:
            failed.append({"close_id": close_id, "error": str(e)[:200]})
            logger.warning("dc_reviews_backfill.fail close_id=%s err=%s", close_id, e)
        except Exception as exc:
            failed.append({"close_id": close_id, "error": f"unexpected: {exc}"[:200]})
            logger.exception("dc_reviews_backfill.unexpected close_id=%s", close_id)

    remaining_rows = db.rpc("dc_ads_backfill_candidates", {"p_limit": 10000}).execute().data or []
    result = {
        "status": "ok",
        "picked": len(ids),
        "regraded": len(regraded),
        "failed": failed,
        "cost_usd": round(cost_usd, 4),
        "remaining": len(remaining_rows),
    }

    try:
        db.table("webhook_deliveries").insert(
            {
                "webhook_id": f"{_AUDIT_SOURCE}_{uuid.uuid4()}",
                "source": _AUDIT_SOURCE,
                "processing_status": "ok" if not failed else "partial",
                "payload": result,
                "headers": {},
                "processed_at": datetime.now(UTC).isoformat(),
            }
        ).execute()
    except Exception:
        logger.warning("dc_reviews_backfill_cron: audit insert failed", exc_info=True)

    return result


def _verify_auth(headers: Any) -> bool:
    expected = os.environ.get("CRON_SECRET") or ""
    if not expected:
        logger.error("dc_reviews_backfill_cron: CRON_SECRET not configured")
        return False
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth_header.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth_header[len("Bearer ") :], expected)
