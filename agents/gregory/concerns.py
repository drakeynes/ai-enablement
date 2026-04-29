"""Gregory brain — concerns generation.

Pulls recent call_summary documents + open action items for one client
and asks Claude to surface 0–5 qualitative watchpoints. Returns the
concerns list in the locked factors.concerns[] shape.

Gating: the entire Claude call is gated behind the
GREGORY_CONCERNS_ENABLED env var. With ~22 call_summary docs across 132
active clients today, ~85% of clients have no input for Claude to read.
Default off; flip on via env var (deploy-flippable, no commit needed)
once summary coverage densifies.

When the flag is off, returns an empty list. When the flag is on but
the client has no summaries AND no open action items, also returns an
empty list (don't burn tokens for empty input).
"""

from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from agents.gregory.prompts import (
    CONCERNS_SYSTEM_PROMPT,
    build_concerns_user_message,
)
from shared.claude_client import complete

# Read once at module load. Set GREGORY_CONCERNS_ENABLED=true in Vercel
# env vars (or .env.local for local) to enable the Claude call.
CONCERNS_ENABLED = os.environ.get("GREGORY_CONCERNS_ENABLED", "").lower() in {
    "1",
    "true",
    "yes",
}

# Cap on how many recent summaries we hand Claude. 5 is enough context
# for a CSM-grade watchpoint read; more is diminishing returns + more
# tokens.
SUMMARY_FETCH_LIMIT = 5


class Concern(TypedDict, total=False):
    text: str
    severity: str
    source_call_ids: list[str]


def _fetch_recent_summaries(db: Any, client_id: str) -> list[dict]:
    """Most recent N call_summary documents for this client. Filters
    on metadata.client_id (the client-scoped identifier on call_summary
    docs — same field call-facing agents like Ella filter on)."""
    resp = (
        db.table("documents")
        .select("title, content, metadata, created_at")
        .eq("document_type", "call_summary")
        .filter("metadata->>client_id", "eq", client_id)
        .order("created_at", desc=True)
        .limit(SUMMARY_FETCH_LIMIT)
        .execute()
    )
    rows = resp.data or []
    summaries = []
    for row in rows:
        meta = row.get("metadata") or {}
        summaries.append(
            {
                "call_id": meta.get("call_id"),
                "started_at": meta.get("started_at"),
                "title": row.get("title"),
                "content": row.get("content"),
            }
        )
    return summaries


def _fetch_open_action_items(db: Any, client_id: str) -> list[dict]:
    """Open action items owned by this client. Owner type ('client')
    is implicit since we filter on owner_client_id."""
    resp = (
        db.table("call_action_items")
        .select("description, due_date, owner_type")
        .eq("owner_client_id", client_id)
        .eq("status", "open")
        .order("due_date", desc=False, nullsfirst=False)
        .execute()
    )
    return list(resp.data or [])


def _fetch_client_full_name(db: Any, client_id: str) -> str:
    resp = (
        db.table("clients").select("full_name").eq("id", client_id).single().execute()
    )
    return (resp.data or {}).get("full_name") or "Unknown client"


def generate_concerns(
    db: Any,
    client_id: str,
    run_id: str | None = None,
) -> list[Concern]:
    """Generate concerns for one client. Returns an empty list when:
      - GREGORY_CONCERNS_ENABLED is off (default)
      - The client has no summaries AND no open action items (nothing
        for Claude to read)
      - Claude returns malformed JSON (we log and degrade — empty list
        beats partial bad data writing to the factors jsonb)

    Costs / token usage land on the agent_runs row identified by run_id
    via shared.claude_client.complete's run-aware accounting.
    """
    if not CONCERNS_ENABLED:
        return []

    summaries = _fetch_recent_summaries(db, client_id)
    action_items = _fetch_open_action_items(db, client_id)

    if not summaries and not action_items:
        # Nothing for Claude to reason over. Skip the call.
        return []

    client_full_name = _fetch_client_full_name(db, client_id)
    user_message = build_concerns_user_message(
        client_full_name=client_full_name,
        call_summaries=summaries,
        open_action_items=action_items,
    )

    result = complete(
        system=CONCERNS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        run_id=run_id,
    )

    return _parse_concerns_response(result.text)


def _parse_concerns_response(text: str) -> list[Concern]:
    """Parse Claude's response into a Concern list. Defends against
    JSON-fenced output by stripping leading/trailing markdown if
    present, then loading. On any parse failure, returns []."""
    cleaned = text.strip()

    # Strip markdown code fences if Claude included them despite the
    # "no markdown" instruction. Cheap defense; doesn't change behavior
    # when the response is clean JSON.
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return []

    raw_concerns = parsed.get("concerns") if isinstance(parsed, dict) else None
    if not isinstance(raw_concerns, list):
        return []

    out: list[Concern] = []
    for item in raw_concerns:
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if not isinstance(text_value, str) or not text_value.strip():
            continue
        concern: Concern = {"text": text_value.strip()}
        severity = item.get("severity")
        if isinstance(severity, str) and severity in {"low", "medium", "high"}:
            concern["severity"] = severity
        source_ids = item.get("source_call_ids")
        if isinstance(source_ids, list):
            concern["source_call_ids"] = [
                sid for sid in source_ids if isinstance(sid, str)
            ]
        out.append(concern)

    return out
