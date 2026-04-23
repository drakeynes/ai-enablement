"""Slack Events API webhook for Ella.

Deployed by Vercel as a serverless Python function at
`/api/slack_events`. Slack's Event Subscriptions point at this URL;
this module is the only place `app_mention` events cross from
Slack's edge into our agent code.

V1 flow (synchronous):

  1. Verify the HMAC signature on the raw body. Reject bad signatures
     (401) and stale timestamps (>5 min) without further work.
  2. Handle the one-off `url_verification` challenge inline. Slack
     fires this once when the Event Subscription is first configured.
  3. On Slack retries (`X-Slack-Retry-Num` header present): ack 200
     immediately without re-processing. The original invocation is
     still handling this event; a duplicate would produce two Slack
     replies.
  4. On `event_callback` + `app_mention`: run the agent and post the
     reply synchronously via `chat.postMessage`, then return 200.
     Ella's roundtrip is ~5–10s and Slack's ack window is 3s, so the
     first-delivery on a cold start will time out from Slack's
     perspective — Slack retries, our retry branch acks fast (step 3)
     and the original invocation still lands the post.

Why synchronous and not background-threaded: Vercel's Python runtime
terminates the function process as soon as `do_POST` returns, which
kills any non-daemon `threading.Thread` before it can finish
`chat.postMessage`. Smoke test on 2026-04-23 confirmed this — the
first deployment tried the ack-then-thread pattern and produced zero
replies in Slack despite 200 acks on every request. Fluid Compute
would fix it at the runtime level, but it's a project-level opt-in
we don't have enabled yet. The sync+retry pattern works without any
Vercel config change and costs ~2x container seconds per mention
(first invocation does the work; one retry is acked fast then
discarded). Acceptable for V1 pilot volume.

Env vars required (must be set in the Vercel project):
  SLACK_SIGNING_SECRET       — HMAC verification of inbound webhooks.
  SLACK_BOT_TOKEN            — xoxb- token for outbound chat.postMessage.
  SUPABASE_URL               — shared.db client.
  SUPABASE_SERVICE_ROLE_KEY  — shared.db client.
  ANTHROPIC_API_KEY          — shared.claude_client (Ella's LLM calls).
  OPENAI_API_KEY             — shared.kb_query (embedding retrieval).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler
from typing import Any

from agents.ella.slack_handler import handle_slack_event

# Vercel's Python runtime pre-configures the root logger at WARNING
# level, so a naive `logging.basicConfig(level=INFO)` is a no-op and
# our INFO lines get silently dropped. Set the root logger level
# directly so our INFO-level operational logs land in the Vercel log
# stream (smoke test on 2026-04-23 confirmed this was happening).
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("ai_enablement.slack_webhook")
logger.setLevel(logging.INFO)

# Slack's replay-protection window. Requests older than this are
# rejected regardless of signature — an attacker who captured a valid
# signed request can't replay it hours later.
_MAX_REQUEST_AGE_SECONDS = 300

# Outbound chat.postMessage timeout. Short enough to surface transport
# problems quickly; long enough for Slack's normal tail latency.
_SLACK_POST_TIMEOUT_SECONDS = 10


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime instantiates this per request."""

    def do_POST(self) -> None:
        body = self._read_body()

        if not self._verify_signature(body):
            logger.warning("slack_webhook: signature verification failed")
            self._respond(401, "invalid signature")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("slack_webhook: body was not valid JSON")
            self._respond(400, "bad payload")
            return

        # One-off handshake when the Event Subscription URL is first
        # saved in the Slack app console. We echo `challenge` back.
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge", "")
            logger.info("slack_webhook: url_verification challenge received")
            self._respond(
                200,
                json.dumps({"challenge": challenge}),
                content_type="application/json",
            )
            return

        # Slack retries the webhook on any non-200 or slow response.
        # Retries carry `X-Slack-Retry-Num` and the original event
        # (same event_id). The first delivery's background thread is
        # still handling the mention, so re-running it here would
        # produce a duplicate Slack reply.
        retry_num = self.headers.get("X-Slack-Retry-Num")
        if retry_num:
            logger.info(
                "slack_webhook: skipping retry #%s (reason=%s)",
                retry_num,
                self.headers.get("X-Slack-Retry-Reason"),
            )
            self._respond(200, "ok")
            return

        if payload.get("type") == "event_callback":
            event = payload.get("event") or {}
            if event.get("type") == "app_mention":
                logger.info(
                    "slack_webhook: processing app_mention channel=%s user=%s",
                    event.get("channel"),
                    event.get("user"),
                )
                # Synchronous so the work actually happens. Vercel's
                # Python runtime kills background threads the moment
                # the response is written, so a fire-and-forget
                # threaded post never lands. See module docstring for
                # why this is acceptable: Slack retries fast on our
                # missed ack, and the retry branch above catches them.
                _process_mention(payload)

        # Ack regardless of inner event type. Anything non-200 tells
        # Slack to retry, which we don't want for events we didn't
        # subscribe to.
        self._respond(200, "ok")

    def do_GET(self) -> None:
        # Browser hits / uptime pings land here. A 200 + a small hint
        # is friendlier than a Vercel 404 when someone opens the URL
        # to sanity-check the deployment.
        self._respond(200, "ella slack webhook — POST only")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length else b""

    def _verify_signature(self, body: bytes) -> bool:
        """HMAC-SHA256 verification per Slack's request-signing spec.

        Operates on raw bytes end-to-end so encoding-roundtrip bugs
        can't cause a false rejection. Returns False on any missing
        header, stale timestamp, or mismatch.
        """
        secret = os.environ.get("SLACK_SIGNING_SECRET")
        if not secret:
            logger.error("slack_webhook: SLACK_SIGNING_SECRET not set")
            return False

        timestamp = self.headers.get("X-Slack-Request-Timestamp")
        signature = self.headers.get("X-Slack-Signature")
        if not timestamp or not signature:
            return False

        try:
            ts_int = int(timestamp)
        except ValueError:
            return False

        delta = abs(time.time() - ts_int)
        if delta > _MAX_REQUEST_AGE_SECONDS:
            logger.warning(
                "slack_webhook: rejecting request with timestamp delta %.0fs",
                delta,
            )
            return False

        basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
        expected = "v0=" + hmac.new(
            secret.encode("utf-8"),
            basestring,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def _respond(
        self,
        status: int,
        body: str = "",
        content_type: str = "text/plain",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        encoded = body.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


def _process_mention(payload: dict[str, Any]) -> None:
    """Run Ella on the event and post her response back to Slack.

    Any exception is caught and logged: a single bad mention must not
    take the function down for the next one, and an unhandled
    exception in a background thread would otherwise be swallowed by
    Vercel with no diagnostic trail.
    """
    try:
        result = handle_slack_event(payload)
    except Exception as exc:
        logger.exception("slack_webhook: handle_slack_event raised: %s", exc)
        return

    if not result.get("responded") or not result.get("text"):
        logger.info(
            "slack_webhook: agent returned no response (reason=%s)",
            result.get("reason") or "responded=False",
        )
        return

    channel = result.get("channel_id")
    thread_ts = result.get("thread_ts")
    text = result["text"]

    try:
        _post_to_slack(channel=channel, text=text, thread_ts=thread_ts)
    except Exception as exc:
        logger.exception("slack_webhook: chat.postMessage raised: %s", exc)


def _post_to_slack(*, channel: str, text: str, thread_ts: str | None) -> None:
    """POST to Slack's Web API chat.postMessage endpoint.

    Uses stdlib `urllib.request` to avoid adding `requests` or
    `slack_sdk` as a runtime dep — the call is simple enough that the
    heavier libraries aren't earning their keep.

    Slack's Web API returns HTTP 200 even on application errors;
    `ok: false` in the response body signals failure. We parse and
    log the full body on failure so a missing scope or wrong channel
    surfaces in Vercel logs.
    """
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set")

    body: dict[str, Any] = {"channel": channel, "text": text}
    if thread_ts:
        body["thread_ts"] = thread_ts

    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=_SLACK_POST_TIMEOUT_SECONDS) as resp:
        response_body = resp.read().decode("utf-8")

    parsed = json.loads(response_body)
    if not parsed.get("ok"):
        logger.error(
            "slack.postMessage failed: channel=%s error=%s full_response=%s",
            channel,
            parsed.get("error"),
            parsed,
        )
    else:
        logger.info(
            "slack.postMessage ok: channel=%s thread_ts=%s",
            channel,
            thread_ts,
        )
