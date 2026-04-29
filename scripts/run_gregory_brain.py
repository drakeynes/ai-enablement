"""Manually trigger Gregory brain — for backfilling, validating a single
client's score, or running ad-hoc between cron sweeps.

Usage:

    # Sweep every active client.
    python scripts/run_gregory_brain.py --all

    # Score a single client (the one Drake reviews before --all).
    python scripts/run_gregory_brain.py --client-id <uuid>

    # Score by email (handier than fishing UUIDs out of Studio).
    python scripts/run_gregory_brain.py --email vid.velayutham@gmail.com

The script writes to client_health_scores immediately — there is no
dry-run mode in V1.1. The history-table design means a "wrong" score
is not destructive; it's just one row to ignore. Re-run after a fix
and the latest-per-client query the dashboard uses will pick up the
new value.

Per the M3.4 hard stops, the first cloud run should be a single-client
run; only after Drake reviews the produced row in Studio does the
all-active sweep land.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sibling packages importable when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.gregory.agent import (  # noqa: E402
    compute_health_for_all_active,
    compute_health_for_client,
)
from shared.db import get_client  # noqa: E402


def _resolve_client_id(db, email: str) -> str:
    """Look up an active client by email. Surfaces a clear error if the
    email doesn't resolve — better than a confusing 'client not found'
    deeper in the agent."""
    resp = (
        db.table("clients")
        .select("id, full_name")
        .eq("email", email)
        .is_("archived_at", "null")
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise SystemExit(f"No active client with email {email!r}.")
    if len(rows) > 1:
        raise SystemExit(
            f"Multiple active clients with email {email!r} — pass --client-id explicitly."
        )
    print(f"Resolved {email} -> {rows[0]['full_name']} ({rows[0]['id']})")
    return rows[0]["id"]


def _run_single(client_id: str) -> int:
    db = get_client()
    print(f"Running brain for client_id={client_id}...")
    result = compute_health_for_client(client_id=client_id, db=db, trigger_type="manual")
    print()
    print(f"  score: {result.score}")
    print(f"  tier: {result.tier}")
    print(f"  insufficient_data: {result.insufficient_data}")
    print(f"  concerns: {result.concerns_count}")
    print(f"  health_score row id: {result.health_score_row_id}")
    print(f"  agent_runs id: {result.agent_run_id}")
    return 0


def _run_all() -> int:
    db = get_client()
    print("Running brain for all active clients...")
    sweep = compute_health_for_all_active(db=db, trigger_type="manual")
    print()
    print(f"  total_clients: {sweep.total_clients}")
    print(f"  succeeded: {sweep.succeeded}")
    print(f"  failed: {sweep.failed}")
    print(f"  insufficient_data: {sweep.insufficient_data}")

    # Tier distribution from per-client outcomes — useful sanity check
    # before the dashboard renders anything.
    from collections import Counter

    tiers = Counter(outcome.tier for outcome in sweep.per_client)
    print(f"  tier distribution: {dict(tiers)}")

    if sweep.errors:
        print()
        print("Errors:")
        for err in sweep.errors:
            print(f"  - {err['client_name']} ({err['client_id']}): {err['error']}")

    return 0 if sweep.failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client-id", help="UUID of the client to score")
    group.add_argument("--email", help="Email of the client to score")
    group.add_argument(
        "--all", action="store_true", help="Sweep every active client"
    )
    args = parser.parse_args(argv)

    if args.all:
        return _run_all()

    if args.email:
        client_id = _resolve_client_id(get_client(), args.email)
    else:
        client_id = args.client_id

    return _run_single(client_id)


if __name__ == "__main__":
    sys.exit(main())
