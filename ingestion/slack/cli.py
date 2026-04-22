"""Command-line entrypoint for the Slack backfill ingestion.

Usage:

    python -m ingestion.slack.cli [--days N] [--channel <id>]
                                  [--limit N] [--apply]

Without `--apply`: dry-run — resolves channels, checks bot membership,
fetches history, parses, reports counts per channel + samples. Writes
nothing to Supabase (but `conversations.list` is called to resolve
ella-test, which is read-only).

With `--apply`: upserts to `slack_messages` and materializes a
`slack_channels` row for any Slack-only targets (ella-test).

The V1 target list is pinned here (the 7 pilot clients + #ella-test).
`--channel <slack_channel_id>` restricts the run to that one channel
(useful for re-running a single channel after a fix).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.slack.client import SlackClient  # noqa: E402
from ingestion.slack.pipeline import (  # noqa: E402
    ChannelIngestOutcome,
    RunReport,
    run_ingest,
)
from shared.db import get_client  # noqa: E402

_LOG_DIR = _REPO_ROOT / "data" / "slack_ingest"

# V1 pilot targets. If you're adding a new client channel, update the
# list here. The name has to match `clients.full_name` exactly (case
# and whitespace). Ella test lives under extra_channel_names because
# it isn't linked to a client.
_PILOT_CLIENT_NAMES: tuple[str, ...] = (
    "Fernando G",
    "Javi Pena",
    "Musa Elmaghrabi",
    "Jenny Burnett",
    "Dhamen Hothi",
    "Trevor Heck",
    "Art Nuno",
)
_EXTRA_CHANNEL_NAMES: tuple[str, ...] = ("ella-test",)


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    db = get_client()
    slack = SlackClient()

    # If --channel is passed, restrict targets to just that slack_channel_id.
    client_names = list(_PILOT_CLIENT_NAMES)
    extra_names = list(_EXTRA_CHANNEL_NAMES)
    if args.channel:
        client_names, extra_names = _filter_to_channel(db, args.channel)

    _print_header(args, client_names, extra_names)

    report = run_ingest(
        db, slack,
        client_full_names=client_names,
        extra_channel_names=extra_names,
        days=args.days,
        dry_run=not args.apply,
    )

    _print_dry_run_section(report, limit=args.limit)

    if not args.apply:
        print("Dry run only — no changes written. Re-run with --apply to commit.")
        return 0

    _print_apply_summary(report)
    log_path = _write_log(report)
    print(f"\nLog: {log_path}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=90, help="Days of history to pull. Default 90.")
    p.add_argument("--channel", help="Restrict to one slack_channel_id (e.g. C09TYEPLGBX).")
    p.add_argument("--limit", type=int, default=5, help="Max sample messages per channel in the report.")
    p.add_argument("--apply", action="store_true", help="Write to Supabase. Without, dry-run only.")
    return p.parse_args(argv)


def _filter_to_channel(db, slack_channel_id: str) -> tuple[list[str], list[str]]:
    """Resolve a single slack_channel_id back to its target spec."""
    resp = (
        db.table("slack_channels")
        .select("slack_channel_id,name,client_id")
        .eq("slack_channel_id", slack_channel_id)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        sys.exit(f"ERROR: no slack_channels row for {slack_channel_id}")
    row = rows[0]
    if row.get("client_id"):
        client_resp = (
            db.table("clients")
            .select("full_name")
            .eq("id", row["client_id"])
            .execute()
        )
        name = (client_resp.data or [{}])[0].get("full_name")
        if not name:
            sys.exit(f"ERROR: client_id {row['client_id']} missing full_name")
        return [name], []
    return [], [row["name"]]


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _print_header(args, client_names: list[str], extra_names: list[str]) -> None:
    print("=" * 72)
    print("SLACK BACKFILL INGESTION")
    print("=" * 72)
    print(f"Window:  last {args.days} days")
    print(f"Targets: {len(client_names)} client channels + {len(extra_names)} extra")
    if client_names:
        print(f"  clients: {', '.join(client_names)}")
    if extra_names:
        print(f"  extras:  {', '.join(extra_names)}")
    print()


def _print_dry_run_section(report: RunReport, *, limit: int) -> None:
    print("-" * 72)
    print("CHANNEL RESOLUTION + MEMBERSHIP")
    print("-" * 72)
    print(f"{'identifier':<22} {'slack_channel_id':<14} {'client':<20} {'member':<7} {'status'}")
    print(f"{'-'*22} {'-'*14} {'-'*20} {'-'*7} {'-'*20}")
    for target in report.targets:
        client_label = target.client_name or "—"
        ch_id = target.slack_channel_id or "—"
        status = "ok" if target.resolved else (target.resolution_error or "unresolved")
        member = "yes" if target.bot_is_member else "no"
        if not target.resolved:
            member = "—"
        print(
            f"{target.identifier:<22} {ch_id:<14} {client_label:<20} {member:<7} {status}"
        )
    print()

    print("-" * 72)
    print("PER-CHANNEL MESSAGE COUNTS")
    print("-" * 72)
    totals = {
        "messages_in_window": 0,
        "threads_followed": 0,
        "unresolved_authors": 0,
    }
    for outcome in report.outcomes:
        target = outcome.resolved
        identifier = target.identifier
        if outcome.error:
            print(f"  {identifier:<22} ERROR: {outcome.error}")
            continue
        author_str = ", ".join(
            f"{k}={v}" for k, v in sorted(outcome.author_breakdown.items())
        ) or "—"
        subtype_str = ", ".join(
            f"{k}={v}" for k, v in sorted(outcome.subtype_counts.items())
        ) or "—"
        print(
            f"  {identifier:<22} messages={outcome.messages_in_window:>4}  "
            f"threads={outcome.threads_followed:>3}  authors=[{author_str}]  "
            f"subtypes=[{subtype_str}]"
        )
        totals["messages_in_window"] += outcome.messages_in_window
        totals["threads_followed"] += outcome.threads_followed
        totals["unresolved_authors"] += outcome.unresolved_author_count

    print()
    print("-" * 72)
    print("TOTALS")
    print("-" * 72)
    print(f"  messages across all channels:  {totals['messages_in_window']}")
    print(f"  threads followed:              {totals['threads_followed']}")
    print(f"  unresolved authors:            {totals['unresolved_authors']}")
    print(f"  Slack API calls this run:      {report.total_api_calls}")
    print()

    print("-" * 72)
    print(f"SAMPLES — up to {limit} random messages per channel")
    print("-" * 72)
    for outcome in report.outcomes:
        if outcome.error or not outcome.sample_records:
            continue
        target = outcome.resolved
        print(f"  [{target.identifier}] {target.slack_channel_id}")
        for rec in outcome.sample_records[:limit]:
            text_preview = rec.text[:80].replace("\n", " ")
            print(
                f"    ts={rec.slack_ts:<20} type={rec.message_type:<18} "
                f"author_type={rec.author_type:<12} subtype={rec.message_subtype or '-'}"
            )
            print(f"      text: {text_preview}")
        print()


def _print_apply_summary(report: RunReport) -> None:
    print("-" * 72)
    print("APPLY SUMMARY")
    print("-" * 72)
    total_inserted = 0
    total_updated = 0
    for outcome in report.outcomes:
        if outcome.error:
            print(f"  {outcome.resolved.identifier:<22} error: {outcome.error}")
            continue
        total_inserted += outcome.messages_inserted
        total_updated += outcome.messages_updated
        print(
            f"  {outcome.resolved.identifier:<22} "
            f"inserted={outcome.messages_inserted:>4}  "
            f"updated={outcome.messages_updated:>4}"
        )
    print()
    print(f"  TOTAL inserted:                {total_inserted}")
    print(f"  TOTAL updated:                 {total_updated}")
    print(f"  Slack API calls this run:      {report.total_api_calls}")


def _write_log(report: RunReport) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"run_{ts}.log"
    body = {
        "timestamp_utc": ts,
        "bot_user_id": report.bot_user_id,
        "total_api_calls": report.total_api_calls,
        "channels": [
            {
                "identifier": o.resolved.identifier,
                "slack_channel_id": o.resolved.slack_channel_id,
                "client_name": o.resolved.client_name,
                "bot_is_member": o.resolved.bot_is_member,
                "resolution_error": o.resolved.resolution_error,
                "error": o.error,
                "messages_in_window": o.messages_in_window,
                "threads_followed": o.threads_followed,
                "author_breakdown": o.author_breakdown,
                "subtype_counts": o.subtype_counts,
                "unresolved_author_count": o.unresolved_author_count,
                "messages_inserted": o.messages_inserted,
                "messages_updated": o.messages_updated,
            }
            for o in report.outcomes
        ],
    }
    path.write_text(json.dumps(body, indent=2, default=str))
    return path


if __name__ == "__main__":
    sys.exit(main())
