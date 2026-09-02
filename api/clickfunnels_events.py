"""ClickFunnels form-submission webhook receiver.

Deployed by Vercel as a serverless Python function at
`/api/clickfunnels_events`. A Webhook step in the DC ClickFunnels
workflow POSTs one flat JSON object per form submission (a parallel
step feeds Make.com → the Google Sheet; the two deliveries are
independent). See docs/runbooks/clickfunnels_ingestion.md.

Two-phase, audit-first (house webhook pattern): every accepted POST is
FIRST captured raw into `webhook_deliveries`
(source='clickfunnels_webhook', status='received', dedup on body hash),
THEN `ingestion.clickfunnels.pipeline.process_pending` normalizes the
capture (plus any backlog) into the `typeform_responses` mirror — the
same table Typeform lives in, so the facts refresh and every dashboard
read both sources identically. A processing failure never fails the
delivery; unprocessed captures are the replay queue and drain on the
next submission.

Auth: shared secret, constant-time-compared against
`CLICKFUNNELS_WEBHOOK_SECRET` — either the `X-Relay-Secret` header (a
Make HTTP module) or `?secret=` in the URL (a ClickFunnels workflow
Webhook step pointed directly at us, which may not support headers).
Env var unset → 503 (endpoint dark until configured). Bad secret → 401,
no DB write. After auth, the house always-200 posture applies: internal
failures log + return 200 so Make's error handling doesn't disable the
route; the payload is retryable and the body-hash key dedupes.

Env vars (set in Vercel — NOT committed):
  CLICKFUNNELS_WEBHOOK_SECRET — shared secret; same value goes in the
                                Make module's X-Relay-Secret header.
  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY — shared.db
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.db import get_client  # noqa: E402

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.clickfunnels_events")

_MAX_BODY_BYTES = 1_000_000
_SECRET_HEADER = "X-Relay-Secret"
_HEADERS_TO_STORE = ("Content-Type", "User-Agent", "X-Forwarded-For")


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — Vercel handler contract
        self._respond(200, {"status": "ok", "endpoint": "clickfunnels_events"})

    def do_POST(self) -> None:  # noqa: N802
        secret = os.environ.get("CLICKFUNNELS_WEBHOOK_SECRET") or ""
        if not secret:
            self._respond(503, {"error": "receiver not configured"})
            return
        # Secret arrives as the X-Relay-Secret header (Make HTTP module)
        # or as ?secret= in the URL (CF workflow webhook steps may not
        # support custom headers).
        provided = self.headers.get(_SECRET_HEADER) or ""
        if not provided:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            provided = (query.get("secret") or [""])[0]
        if not hmac.compare_digest(provided.encode(), secret.encode()):
            logger.warning("clickfunnels_webhook: bad or missing relay secret")
            self._respond(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_BODY_BYTES:
                self._respond(400, {"error": "bad content length"})
                return
            body = self.rfile.read(length)

            try:
                payload: Any = json.loads(body)
            except json.JSONDecodeError:
                # Make can be configured to send non-JSON; keep the raw
                # text so discovery still sees it.
                payload = {"_raw_text": body.decode("utf-8", errors="replace")}

            body_hash = hashlib.sha256(body).hexdigest()[:16]
            webhook_id = f"clickfunnels_webhook:{body_hash}"

            db = get_client()
            insert_resp = (
                db.table("webhook_deliveries")
                .upsert(
                    {
                        "webhook_id": webhook_id,
                        "source": "clickfunnels_webhook",
                        "processing_status": "received",
                        "payload": payload,
                        "headers": {
                            k: str(self.headers.get(k))
                            for k in _HEADERS_TO_STORE
                            if self.headers.get(k) is not None
                        },
                    },
                    on_conflict="webhook_id",
                    ignore_duplicates=True,
                    returning="representation",
                )
                .execute()
            )
            deduplicated = not insert_resp.data
            if not deduplicated:
                logger.info("clickfunnels_webhook: captured %s", webhook_id)

            # Normalize this capture (and drain any backlog) into the
            # typeform_responses mirror. Fail-soft: the capture row is
            # the replay queue, so a processing failure never fails the
            # delivery.
            counts: dict[str, int] = {}
            try:
                from ingestion.clickfunnels.pipeline import process_pending

                counts = process_pending(db, limit=20)
            except Exception as exc:
                logger.exception(
                    "clickfunnels_webhook: processing failed (capture kept): %s", exc
                )

            self._respond(
                200,
                {
                    "captured": not deduplicated,
                    "deduplicated": deduplicated,
                    "id": webhook_id,
                    "processed": counts,
                },
            )
        except Exception as exc:  # always-200 after auth (house posture)
            logger.exception("clickfunnels_webhook: capture failed: %s", exc)
            self._respond(200, {"captured": False})

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:  # quiet default stderr log
        return
