"""Weekly per-rep coaching synthesis for the DC Ads calls page (0152).

`generate_rep_coaching(week_start_et)` collects each rep's dc_ads-rubric
reviews for one ET week (Mon–Sun), carries the reviews' quote-evidenced
strengths/weaknesses into the row, and asks Sonnet for 2-3 coaching
recommendations per rep. One model call per rep (the DC team is a handful
of people). Upserts dc_rep_coaching on (week_start, close_user_id).
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

logger = logging.getLogger("ai_enablement.dc_intel.rep_coaching")

PROMPT_VERSION = "coach-v1"

_ET = ZoneInfo("America/New_York")
_MAX_OUTPUT_TOKENS = 1200
_MAX_RECS = 3
# Below this many reviewed calls the synthesis is noise — the row still
# writes (aggregates + carried items), but the prompt is told the n and
# recommendations stay proportionally hedged.
_MIN_CALLS_NOTED = 5

SYSTEM_PROMPT = """\
You are a sales coach for reps dialing Digital College paid-ads opt-ins
(close a ~$300 enrollment on the phone). You receive ONE rep's week of AI
call-review aggregates: per-call rep-execution scores, outcomes, the
why-not-closed reasons they hit, and the quote-evidenced strengths and
weaknesses their reviews surfaced.

Return a single JSON object, nothing else (no fences, no prose):

{
  "recommendations": [
    {"focus": "one-line coaching focus",
     "why": "1-2 sentences, anchored to this week's evidence (quote it)",
     "drill": "one concrete thing to DO on next week's calls"}
  ]
}

Rules:
- 2-3 recommendations, ranked by expected impact on closes.
- Anchor every recommendation in the supplied evidence — quote or
  paraphrase the review items; never invent a pattern the data lacks.
- If the week has few reviewed calls (the context says how many), keep to
  the 1-2 clearest items and say the sample is thin in the "why".
- Specific and directive, not generic ("ask for the sale after handling
  the price objection, don't offer a call-back" — never "improve closing
  skills").
"""


def _week_bounds_utc(week_start: date) -> tuple[str, str]:
    start = datetime.combine(week_start, time.min, tzinfo=_ET)
    end = datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=_ET)
    return start.isoformat(), end.isoformat()


def generate_rep_coaching(
    week_start_et: str,
    *,
    db: Any | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate + persist coaching rows for every rep with reviewed calls
    in the ET week starting `week_start_et` (a Monday). Idempotent per rep."""
    db = db or get_client()
    week_start = date.fromisoformat(week_start_et)
    start_utc, end_utc = _week_bounds_utc(week_start)

    existing_ids: set[str] = set()
    if not force:
        existing = (
            db.table("dc_rep_coaching")
            .select("close_user_id")
            .eq("week_start", week_start_et)
            .execute()
        )
        existing_ids = {r["close_user_id"] for r in (existing.data or [])}

    # The week's dc_ads-rubric reviews joined to their calls' rep identity.
    calls = (
        db.table("close_calls")
        .select("close_id, user_id, raw_payload")
        .gte("activity_at", start_utc)
        .lt("activity_at", end_utc)
        .gte("duration", 90)
        .not_.is_("user_id", "null")
        .execute()
        .data
        or []
    )
    call_rep = {
        c["close_id"]: (
            c["user_id"],
            ((c.get("raw_payload") or {}).get("user_name") or c["user_id"]),
        )
        for c in calls
    }
    if not call_rep:
        return {"week_start": week_start_et, "reps": 0, "skipped": []}

    reviews = (
        db.table("setter_call_reviews")
        .select(
            "close_call_id, rep_score, rep_score_reason, closed, why_not_closed,"
            "main_objection, setter_strengths, setter_weaknesses, lead_score, intent"
        )
        .eq("call_type", "dc_ads")
        .in_("close_call_id", list(call_rep.keys()))
        .execute()
        .data
        or []
    )

    by_rep: dict[str, dict[str, Any]] = {}
    for r in reviews:
        user_id, user_name = call_rep[r["close_call_id"]]
        rep = by_rep.setdefault(
            user_id, {"user_name": user_name, "reviews": []}
        )
        rep["reviews"].append(r)

    # Resolve display names via team_members where linked.
    if by_rep:
        tms = (
            db.table("team_members")
            .select("close_user_id, full_name")
            .in_("close_user_id", list(by_rep.keys()))
            .execute()
            .data
            or []
        )
        for tm in tms:
            if tm["close_user_id"] in by_rep and tm.get("full_name"):
                by_rep[tm["close_user_id"]]["user_name"] = tm["full_name"]

    results, skipped = [], []
    for user_id, rep in by_rep.items():
        if user_id in existing_ids:
            skipped.append(user_id)
            continue
        rows = rep["reviews"]
        scores = [r["rep_score"] for r in rows if r.get("rep_score") is not None]
        strengths = [s for r in rows for s in (r.get("setter_strengths") or [])]
        weaknesses = [w for r in rows for w in (r.get("setter_weaknesses") or [])]
        context = {
            "rep": rep["user_name"],
            "weekStart": week_start_et,
            "reviewedCalls": len(rows),
            "sampleThin": len(rows) < _MIN_CALLS_NOTED,
            "avgRepScore": round(sum(scores) / len(scores), 1) if scores else None,
            "closes": sum(1 for r in rows if r.get("closed")),
            "whyNotClosed": _tally(r.get("why_not_closed") for r in rows if not r.get("closed")),
            "mainObjections": [r["main_objection"] for r in rows if r.get("main_objection")][:10],
            "strengths": strengths[:12],
            "weaknesses": weaknesses[:12],
            "perCall": [
                {"repScore": r.get("rep_score"), "leadScore": r.get("lead_score"),
                 "intent": r.get("intent"), "closed": r.get("closed"),
                 "reason": r.get("rep_score_reason")}
                for r in rows
            ][:25],
        }
        result = complete(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(context, default=str)}],
            model=DEFAULT_MODEL,
            max_tokens=_MAX_OUTPUT_TOKENS,
            run_id=None,
        )
        recs = _parse_recs(result.text, rep["user_name"])
        row = {
            "week_start": week_start_et,
            "close_user_id": user_id,
            "rep_name": rep["user_name"],
            "calls_reviewed": len(rows),
            "avg_rep_score": round(sum(scores) / len(scores), 1) if scores else None,
            "closes": sum(1 for r in rows if r.get("closed")),
            "strengths": strengths[:12],
            "weaknesses": weaknesses[:12],
            "recommendations": recs,
            "model": DEFAULT_MODEL,
            "prompt_version": PROMPT_VERSION,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": float(result.cost_usd),
        }
        db.table("dc_rep_coaching").upsert(
            row, on_conflict="week_start,close_user_id"
        ).execute()
        logger.info(
            "dc_intel.rep_coaching.persisted week=%s rep=%s calls=%d",
            week_start_et, rep["user_name"], len(rows),
        )
        results.append({"rep": rep["user_name"], "calls": len(rows)})

    return {"week_start": week_start_et, "reps": len(results), "generated": results, "skipped": skipped}


def _tally(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        if v:
            out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _parse_recs(text: str, rep_name: str) -> list[dict[str, str]]:
    candidate = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"coaching non-JSON for {rep_name}: {exc}") from exc
    recs = parsed.get("recommendations") if isinstance(parsed, dict) else None
    if not isinstance(recs, list) or not recs:
        raise RuntimeError(f"coaching missing recommendations for {rep_name}")
    cleaned = []
    for r in recs[:_MAX_RECS]:
        if not isinstance(r, dict) or not (r.get("focus") or "").strip():
            continue
        cleaned.append(
            {
                "focus": str(r["focus"]).strip(),
                "why": str(r.get("why") or "").strip(),
                "drill": str(r.get("drill") or "").strip(),
            }
        )
    if not cleaned:
        raise RuntimeError(f"coaching recommendations all malformed for {rep_name}")
    return cleaned
