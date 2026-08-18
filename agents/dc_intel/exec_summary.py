"""Daily executive summary for the DC Ads page (0152).

`generate_exec_summary(for_date_et)` builds a compact aggregate context —
the last 8 daily-table rows (the summarized day + a 7-day baseline), the
day's and week's call-review aggregates, and spend — asks Sonnet for the
five exec answers, validates, and upserts dc_ads_exec_summaries.

The model sees ONLY aggregates. Grounding rules are explicit in the
prompt: no claims the numbers can't support, small-n caution, and the
traffic-vs-sales verdict must cite which numbers drove it.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from shared.claude_client import DEFAULT_MODEL, complete
from shared.db import get_client

logger = logging.getLogger("ai_enablement.dc_intel.exec_summary")

PROMPT_VERSION = "exec-v1"

_ET = ZoneInfo("America/New_York")
_MAX_OUTPUT_TOKENS = 1500

_REQUIRED_KEYS = ("going_well", "going_wrong", "traffic_or_sales", "changed", "test_next")
_LIST_KEYS = ("going_well", "going_wrong", "changed", "test_next")
_MAX_ITEMS = 4

SYSTEM_PROMPT = """\
You are the daily executive analyst for a Digital College paid-ads sales
operation (Meta ads → landing page form → reps dial the opt-ins and close a
~$300 enrollment on the phone). You receive ONLY aggregates: the last 8
days of the funnel table (opt-ins, qualified, SMS, connects, HVC, units,
spend, AI lead-quality averages), plus AI call-review aggregates for the
summarized day and the trailing week (score averages, why-not-closed
distribution, archetype mix, missed-sale/great-save counts).

Return a single JSON object, nothing else (no fences, no prose):

{
  "going_well": ["...", "..."],
  "going_wrong": ["...", "..."],
  "traffic_or_sales": "...",
  "changed": ["...", "..."],
  "test_next": ["...", "..."]
}

Rules:
- going_well / going_wrong: 1-4 items each, one sentence each, every item
  anchored to a number in the context (quote the number). No generic
  filler — if little happened, say less.
- traffic_or_sales: 2-3 sentences answering "is the problem traffic or
  sales right now?" — citing the specific numbers that drove the verdict
  (e.g. lead-quality average vs rep-execution average, why-not-closed mix).
  If the data is too thin to call, say exactly that.
- changed: 0-3 items — real day-over-baseline shifts (rate or mix changes),
  each with the before/after numbers. Empty list when nothing moved.
- test_next: 1-3 concrete, testable suggestions that follow from the data
  (ad angle, LP copy, dial timing, coaching focus). No platitudes.
- Recent cohort days are IMMATURE by design (stages keep climbing for
  days) — never call a fresh day's low downstream numbers a decline.
- Review coverage may be small (scoring started 2026-08-18). With n under
  ~10 reviewed calls, qualify every review-based claim with the n.
- Be direct. No hedging boilerplate, no restating the table.
"""


def _et_day_bounds_utc(day_et: date) -> tuple[str, str]:
    start = datetime.combine(day_et, time.min, tzinfo=_ET)
    end = datetime.combine(day_et + timedelta(days=1), time.min, tzinfo=_ET)
    return start.isoformat(), end.isoformat()


def _trim_intel(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the aggregate fields of a dc_ads_call_reviews() payload."""
    if not payload:
        return {}
    return {
        "reviewedCalls": (payload.get("avg") or {}).get("n"),
        "avg": payload.get("avg"),
        "whyNotClosed": payload.get("whyNotClosed"),
        "lostTotal": payload.get("lostTotal"),
        "archetypes": payload.get("archetypes"),
        "missedSales": payload.get("missedTotal"),
        "greatSaves": payload.get("savesTotal"),
    }


def generate_exec_summary(
    for_date_et: str,
    *,
    db: Any | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate + persist the exec summary for one ET day. Idempotent."""
    db = db or get_client()

    if not force:
        existing = (
            db.table("dc_ads_exec_summaries")
            .select("for_date")
            .eq("for_date", for_date_et)
            .execute()
        )
        if existing.data:
            logger.info("dc_intel.exec_summary.skip_existing for_date=%s", for_date_et)
            return {"for_date": for_date_et, "skipped": True}

    day = date.fromisoformat(for_date_et)
    day_start, day_end = _et_day_bounds_utc(day)
    week_start, _ = _et_day_bounds_utc(day - timedelta(days=7))

    daily = db.rpc("dc_ads_daily", {"p_end_et": for_date_et, "p_days": 8}).execute().data or []
    # Strip the wide speed columns — the exec context wants the stage story.
    daily_slim = [
        {
            k: r.get(k)
            for k in (
                "etDate", "optIns", "qualified", "sms", "smsMql", "connected",
                "hvc", "units", "closed", "cashUsd", "dials",
                "aiQ", "aiQN", "aiQQual", "aiQQualN",
            )
        }
        for r in daily
    ]
    intel_day = db.rpc(
        "dc_ads_call_reviews", {"p_start": day_start, "p_end": day_end}
    ).execute().data
    intel_week = db.rpc(
        "dc_ads_call_reviews", {"p_start": week_start, "p_end": day_end}
    ).execute().data

    spend_rows = (
        db.table("cortana_campaign_daily")
        .select("day, spent")
        .gte("day", (day - timedelta(days=7)).isoformat())
        .lte("day", for_date_et)
        .execute()
        .data
        or []
    )
    spend_by_day: dict[str, float] = {}
    for r in spend_rows:
        spend_by_day[r["day"]] = spend_by_day.get(r["day"], 0.0) + (r.get("spent") or 0)

    context = {
        "summarizedDay": for_date_et,
        "dailyTable_newestFirst": daily_slim,
        "spendByDay": spend_by_day,
        "callReviews_day": _trim_intel(intel_day),
        "callReviews_trailing7d": _trim_intel(intel_week),
    }

    result = complete(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(context, default=str)}],
        model=DEFAULT_MODEL,
        max_tokens=_MAX_OUTPUT_TOKENS,
        run_id=None,
    )
    summary = _parse_and_validate(result.text, for_date_et)

    row = {
        "for_date": for_date_et,
        "summary": summary,
        "model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": float(result.cost_usd),
    }
    resp = db.table("dc_ads_exec_summaries").upsert(row, on_conflict="for_date").execute()
    logger.info(
        "dc_intel.exec_summary.persisted for_date=%s cost=$%s", for_date_et, row["cost_usd"]
    )
    return resp.data[0] if resp.data else row


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _parse_and_validate(text: str, for_date_et: str) -> dict[str, Any]:
    candidate = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"exec summary non-JSON for {for_date_et}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise TypeError(f"exec summary not an object for {for_date_et}")
    missing = set(_REQUIRED_KEYS) - set(parsed)
    if missing:
        raise RuntimeError(f"exec summary missing keys for {for_date_et}: {sorted(missing)}")
    for key in _LIST_KEYS:
        if not isinstance(parsed[key], list):
            raise TypeError(f"exec summary {key} not a list for {for_date_et}")
        parsed[key] = [str(v).strip() for v in parsed[key][:_MAX_ITEMS] if str(v).strip()]
    if not isinstance(parsed["traffic_or_sales"], str) or not parsed["traffic_or_sales"].strip():
        raise RuntimeError(f"exec summary traffic_or_sales empty for {for_date_et}")
    return {k: parsed[k] for k in _REQUIRED_KEYS}
