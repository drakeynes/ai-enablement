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

import time
from dataclasses import dataclass, field
from typing import Any

from agents.gregory.concerns import generate_concerns
from agents.gregory.scoring import build_overall_reasoning, score_signals
from agents.gregory.signals import compute_all_signals
from shared.db import get_client
from shared.logging import end_agent_run, logger, start_agent_run


@dataclass
class HealthComputeResult:
    """Outcome of one compute_health_for_client call. Returned to the
    cron + manual-trigger callers so they can summarize the run
    without re-querying client_health_scores."""

    client_id: str
    score: int
    tier: str
    insufficient_data: bool
    concerns_count: int
    health_score_row_id: str
    agent_run_id: str


@dataclass
class SweepResult:
    """Outcome of compute_health_for_all_active. Per-client outcomes
    plus simple aggregates for the cron's response body."""

    total_clients: int
    succeeded: int
    failed: int
    insufficient_data: int
    per_client: list[HealthComputeResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def compute_health_for_client(
    client_id: str,
    db: Any | None = None,
    trigger_type: str = "manual",
) -> HealthComputeResult:
    """Compute and persist a single client's health score. Opens its
    own agent_runs row; closes it with success or error.

    The shared.db.get_client() default points at cloud (service role).
    Pass an explicit db for tests or alternate routing.

    trigger_type is recorded on the agent_runs row — 'manual' for
    scripts/run_gregory_brain.py, 'cron' for the Vercel cron path.
    """
    if db is None:
        db = get_client()

    started = time.monotonic()
    run_id = start_agent_run(
        agent_name="gregory",
        trigger_type=trigger_type,
        trigger_metadata={"client_id": client_id},
        input_summary=f"compute health for client {client_id}",
    )

    try:
        signals_list = compute_all_signals(db, client_id)
        concerns_list = generate_concerns(db, client_id, run_id=run_id)
        scoring_result = score_signals(signals_list)
        reasoning = build_overall_reasoning(
            signals_list, scoring_result, len(concerns_list)
        )

        factors = {
            "signals": list(signals_list),
            "concerns": list(concerns_list),
            "overall_reasoning": reasoning,
        }

        insert_resp = (
            db.table("client_health_scores")
            .insert(
                {
                    "client_id": client_id,
                    "score": scoring_result["score"],
                    "tier": scoring_result["tier"],
                    "factors": factors,
                    "computed_by_run_id": run_id,
                }
            )
            .execute()
        )
        row_id = insert_resp.data[0]["id"]

        duration_ms = int((time.monotonic() - started) * 1000)
        end_agent_run(
            run_id,
            status="success",
            output_summary=(
                f"score={scoring_result['score']} tier={scoring_result['tier']} "
                f"concerns={len(concerns_list)} "
                f"{'(insufficient data)' if scoring_result['insufficient_data'] else ''}"
            ).strip(),
            duration_ms=duration_ms,
            metadata={
                "client_health_score_id": row_id,
                "insufficient_data": scoring_result["insufficient_data"],
            },
        )

        return HealthComputeResult(
            client_id=client_id,
            score=scoring_result["score"],
            tier=scoring_result["tier"],
            insufficient_data=scoring_result["insufficient_data"],
            concerns_count=len(concerns_list),
            health_score_row_id=row_id,
            agent_run_id=run_id,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        end_agent_run(
            run_id,
            status="error",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise


def compute_health_for_all_active(
    db: Any | None = None,
    trigger_type: str = "cron",
) -> SweepResult:
    """Sweep every active client; compute + persist a health row for
    each. Per-client failures are isolated — one client's exception
    doesn't stop the sweep. The sweep itself doesn't open its own
    agent_runs row; each per-client run is its own row, which keeps
    cost / duration accounting clean per client.
    """
    if db is None:
        db = get_client()

    resp = (
        db.table("clients")
        .select("id, full_name")
        .is_("archived_at", "null")
        .order("full_name")
        .execute()
    )
    clients = resp.data or []

    result = SweepResult(
        total_clients=len(clients),
        succeeded=0,
        failed=0,
        insufficient_data=0,
    )

    for client in clients:
        client_id = client["id"]
        try:
            outcome = compute_health_for_client(
                client_id=client_id, db=db, trigger_type=trigger_type
            )
            result.succeeded += 1
            if outcome.insufficient_data:
                result.insufficient_data += 1
            result.per_client.append(outcome)
        except Exception as exc:
            result.failed += 1
            result.errors.append(
                {
                    "client_id": client_id,
                    "client_name": client.get("full_name") or "(unknown)",
                    "error": str(exc),
                }
            )
            logger.exception(
                "gregory.compute_health_for_client failed",
                extra={"client_id": client_id},
            )

    return result
