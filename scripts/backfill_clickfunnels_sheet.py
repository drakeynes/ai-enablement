"""Backfill ClickFunnels submissions from the Google-Sheet log.

The CF → Make → Google Sheet leg logged every submission from the
Typeform→ClickFunnels switch (2026-08-28) until (and past) the webhook
go-live (2026-09-02). This script replays sheet rows through the LIVE
production endpoint (`/api/clickfunnels_events`), so backfilled rows take
the exact same capture→normalize path as live deliveries and dedupe
against them (shared Event ID → same `cf:<event_id>` response id;
`typeform_responses` upserts on it).

Sheet columns (verified 2026-09-02):
  First Name, Last Name, Email, Phone (11-digit, no +),
  Time Lead Came In (ET, minute resolution),
  Local Time (misnamed — actually Make's UTC ISO receive time),
  utm_source/medium/campaign/term/content, ad_id, adset_id, campaign_id,
  Event ID, Ip Address, Fbp, Fbc,
  "Can you afford at least $200 in AI tools" (Yes/No).

`submitted_at` uses the Local Time ISO value when present (it trails the
true submit by seconds), else converts Time Lead Came In ET→UTC.
The sheet has no `funnel` column; all rows belong to the Aman VSL
funnel, so `--funnel` defaults to that label (form `cf:aman-vsl-funnel`).

Usage:
  python scripts/backfill_clickfunnels_sheet.py --csv /path/to/sheet.csv --smoke
  python scripts/backfill_clickfunnels_sheet.py --csv /path/to/sheet.csv --apply

Reads CLICKFUNNELS_WEBHOOK_SECRET from the environment or .env.local.
Idempotent: re-running re-POSTs identical bodies, which dedupe at the
capture layer (body hash) and the response layer (event id).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_ENDPOINT = "https://ai-enablement-sigma.vercel.app/api/clickfunnels_events"
DEFAULT_FUNNEL = "Aman VSL Funnel"
_ET = ZoneInfo("America/New_York")

_COLUMN_MAP = {
    "Email": "email",
    "Ip Address": "client_ip_address",
    "Fbp": "fbp",
    "Fbc": "fbc",
    "Event ID": "event_id",
    "utm_source": "utm_source",
    "utm_medium": "utm_medium",
    "utm_campaign": "utm_campaign",
    "utm_term": "utm_term",
    "utm_content": "utm_content",
    "ad_id": "ad_id",
    "adset_id": "adset_id",
    "campaign_id": "campaign_id",
    "Can you afford at least $200 in AI tools": "has_budget_200",
}


def _load_secret() -> str:
    secret = os.environ.get("CLICKFUNNELS_WEBHOOK_SECRET", "")
    if not secret:
        env_path = Path(__file__).resolve().parent.parent / ".env.local"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("CLICKFUNNELS_WEBHOOK_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"')
                    break
    if not secret:
        sys.exit("CLICKFUNNELS_WEBHOOK_SECRET not in env or .env.local")
    return secret


def _submitted_at(row: dict[str, str]) -> str | None:
    local = (row.get("Local Time") or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", local):
        return local
    came_in = (row.get("Time Lead Came In") or "").strip()
    try:
        naive = datetime.strptime(came_in, "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=_ET).astimezone(ZoneInfo("UTC")).isoformat()


def row_to_payload(row: dict[str, str], funnel: str) -> dict[str, str] | None:
    submitted = _submitted_at(row)
    if not submitted:
        return None
    payload: dict[str, str] = {
        col_out: row[col_in].strip()
        for col_in, col_out in _COLUMN_MAP.items()
        if (row.get(col_in) or "").strip()
    }
    digits = re.sub(r"\D", "", row.get("Phone") or "")
    if digits:
        payload["phone"] = "+" + digits
    name = f"{(row.get('First Name') or '').strip()} {(row.get('Last Name') or '').strip()}".strip()
    if name:
        payload["name"] = name
    if not payload.get("email") and not payload.get("phone"):
        return None
    payload["submitted_at"] = submitted
    payload["funnel"] = funnel
    payload["_backfill_source"] = "google_sheet_2026-09-02"
    return payload


def post(endpoint: str, secret: str, payload: dict[str, str]) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Relay-Secret": secret},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="Sheet exported as CSV")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--funnel", default=DEFAULT_FUNNEL)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="replay only the first usable row")
    mode.add_argument("--apply", action="store_true", help="replay every usable row")
    args = ap.parse_args()

    secret = _load_secret()
    rows = list(csv.DictReader(open(args.csv)))
    stats = {"posted": 0, "captured": 0, "deduplicated": 0, "skipped_unusable": 0, "errors": 0}
    for row in rows:
        payload = row_to_payload(row, args.funnel)
        if payload is None:
            stats["skipped_unusable"] += 1
            continue
        try:
            out = post(args.endpoint, secret, payload)
            stats["posted"] += 1
            stats["captured" if out.get("captured") else "deduplicated"] += 1
        except Exception as exc:  # keep going; re-run heals via idempotency
            stats["errors"] += 1
            print(f"  ERROR on event_id={payload.get('event_id', '?')[:12]}: {exc}")
        if args.smoke:
            print("smoke payload keys:", sorted(payload.keys()))
            print("smoke response:", out)
            break
        if stats["posted"] % 50 == 0:
            print(f"  … {stats['posted']} posted")
        time.sleep(0.1)
    print("done:", stats)


if __name__ == "__main__":
    main()
