"""Backfill team_members.slack_user_id via Slack's users.lookupByEmail.

One-shot (and re-runnable) script. Iterates every active team_members
row, calls Slack to resolve email → user_id, updates the row. Prints
per-email status so misses get surfaced immediately.

Re-running is safe: rows that already have slack_user_id set are
skipped unless `--overwrite` is passed.

Usage:

    python scripts/backfill_team_slack_ids.py          # dry-run (no writes)
    python scripts/backfill_team_slack_ids.py --apply  # writes
    python scripts/backfill_team_slack_ids.py --apply --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.slack.client import SlackAPIError, SlackClient  # noqa: E402
from shared.db import get_client  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write updates. Without, dry-run.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-lookup and overwrite even if slack_user_id is already set.",
    )
    args = parser.parse_args(argv)

    db = get_client()
    slack = SlackClient()

    resp = (
        db.table("team_members")
        .select("id,email,full_name,slack_user_id")
        .is_("archived_at", "null")
        .execute()
    )
    team = resp.data or []
    print(f"Loaded {len(team)} active team_members rows.")
    print()

    found = 0
    skipped_has_id = 0
    not_in_slack: list[str] = []
    errors: list[tuple[str, str]] = []

    for row in sorted(team, key=lambda r: r["email"]):
        email = row["email"]
        existing_id = row.get("slack_user_id")

        if existing_id and not args.overwrite:
            print(f"  SKIP  {email:<30} already set: {existing_id}")
            skipped_has_id += 1
            continue

        try:
            lookup = slack.users_lookup_by_email(email)
        except SlackAPIError as exc:
            if exc.error == "users_not_found":
                print(f"  MISS  {email:<30} not in Slack workspace")
                not_in_slack.append(email)
                continue
            print(f"  ERR   {email:<30} slack error: {exc.error}")
            errors.append((email, exc.error))
            continue

        slack_user = lookup.get("user") or {}
        user_id = slack_user.get("id")
        if not user_id:
            print(f"  ERR   {email:<30} no id in response: {lookup!r}")
            errors.append((email, "malformed_response"))
            continue

        print(f"  OK    {email:<30} → {user_id}  ({slack_user.get('real_name') or slack_user.get('name')})")
        found += 1

        if args.apply:
            db.table("team_members").update({"slack_user_id": user_id}).eq("id", row["id"]).execute()

    print()
    print("-" * 60)
    print(f"Found:           {found}")
    print(f"Skipped (had id):{skipped_has_id}")
    print(f"Not in Slack:    {len(not_in_slack)}")
    print(f"Errors:          {len(errors)}")
    if not_in_slack:
        print(f"  misses:        {not_in_slack}")
    if errors:
        print(f"  errors:        {errors}")
    if not args.apply:
        print("\nDry run only — no changes written. Re-run with --apply to commit.")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
