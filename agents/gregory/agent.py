"""Gregory brain V1.1 — entry point.

Computes per-client health scores by combining deterministic signals
(call cadence, action items, NPS) with optional Claude-driven concerns,
and writes one row per invocation to `client_health_scores` (history
preserved by design).

Two public entry points:

  - compute_health_for_client(client_id) — single-client run, used by
    the manual trigger script and tests.
  - compute_health_for_all_active() — sweeps every active client, used
    by the weekly Vercel cron and ad-hoc backfills.

Each invocation opens an `agent_runs` row, computes, writes, and closes
the run with token / cost / duration telemetry.

Architecture is complete in V1.1.0 but the Claude-driven concerns
generation is gated behind the `GREGORY_CONCERNS_ENABLED` env var
(default false). With ~22 call_summary documents across 132 active
clients today, ~85% of clients would have empty input; paying for
empty calls is wasteful. The flag flips on once summary coverage
densifies — no code change required.

Deferred V1.2 signals: Slack engagement (slack_messages cloud table
empty), NPS (nps_submissions empty). Brain handles missing data
gracefully; scores get more meaningful as those signals land.
"""

from __future__ import annotations

# Module-level imports go in commit 6 once signals/scoring/concerns are
# all present. Keeping the scaffold minimal here.
