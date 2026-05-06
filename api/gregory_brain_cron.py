"""Gregory brain cron — weekly health-score sweep for all active clients.

Deployed by Vercel as a serverless Python function at
`/api/gregory_brain_cron`. Vercel Cron POSTs here on a weekly schedule
(09:00 UTC Mondays, configured in `vercel.json`) — far enough after
the daily Fathom backfill at 08:00 that any new calls / action items
ingested overnight are visible to this run.

Calls `agents.gregory.agent.compute_health_for_all_active()`, which
opens one `agent_runs` row per client, computes signals + scoring +
(gated) concerns, writes one `client_health_scores` row per client,
and returns a SweepResult summary.

The Claude-driven concerns generation is gated behind
`GREGORY_CONCERNS_ENABLED` (env var, default false). With current
~22-summaries-across-132-clients density, paying for the LLM call on
~85% of clients with empty input is wasteful. Flag flips on without
a code change once summary coverage densifies.

Env vars required (set in Vercel — NOT committed):

  CRON_SECRET                   — random secret. Vercel Cron sends it as
                                  `Authorization: Bearer <token>` and the
                                  handler verifies constant-time. Shared
                                  across ALL cron endpoints in this project
                                  (Vercel only supports one CRON_SECRET per
                                  project). Single source of truth.
  GREGORY_CONCERNS_ENABLED      — flip to "true" once summary coverage
                                  is dense enough to justify the LLM
                                  cost. Default off.
  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY — shared.db client.
  ANTHROPIC_API_KEY             — used only if concerns flag is on.

Manual trigger for testing:
  curl -i -X POST -H "Authorization: Bearer $CRON_SECRET" \
       https://ai-enablement-sigma.vercel.app/api/gregory_brain_cron
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from typing import Any

# Make sibling packages importable.
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.gregory.agent import compute_health_for_all_active  # noqa: E402

logger = logging.getLogger("ai_enablement.gregory_brain_cron")


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime instantiates this per request."""

    def do_POST(self) -> None:
        try:
            self._handle()
        except Exception as exc:  # pragma: no cover — last-resort safety net
            logger.exception("gregory_brain_cron: unhandled top-level error: %s", exc)
            self._respond(500, {"error": "internal_error"})

    def do_GET(self) -> None:
        # Same auth + behavior as POST so a manual curl works the same
        # way Vercel Cron's POST does.
        self.do_POST()

    def _handle(self) -> None:
        if not _verify_auth(self.headers):
            self._respond(401, {"error": "unauthorized"})
            return

        sweep = compute_health_for_all_active(trigger_type="cron")

        # Tier distribution from per-client outcomes; summary the cron
        # operator can read at a glance.
        from collections import Counter

        tiers = Counter(outcome.tier for outcome in sweep.per_client)

        body: dict[str, Any] = {
            "ok": True,
            "total_clients": sweep.total_clients,
            "succeeded": sweep.succeeded,
            "failed": sweep.failed,
            "insufficient_data": sweep.insufficient_data,
            "tier_distribution": dict(tiers),
        }
        if sweep.errors:
            body["errors"] = sweep.errors[:10]  # truncate to avoid huge payloads
            body["errors_truncated"] = len(sweep.errors) > 10

        logger.info("gregory_brain_cron: sweep complete %s", body)
        self._respond(200, body)

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


def _verify_auth(headers: Any) -> bool:
    """Bearer-token auth. Validates against `CRON_SECRET` — the single
    project-level env var Vercel Cron sends as the Bearer token. All
    cron endpoints in this codebase share this validation; Vercel only
    supports one CRON_SECRET per project (consolidated in M6.2)."""
    expected = os.environ.get("CRON_SECRET") or ""
    if not expected:
        logger.error("gregory_brain_cron: CRON_SECRET not configured")
        return False
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth_header.startswith("Bearer "):
        return False
    presented = auth_header[len("Bearer ") :]
    return hmac.compare_digest(presented, expected)
