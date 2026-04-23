"""Retrieval layer for Ella.

Wraps `shared.kb_query.search_for_client` with a client-specific
context bundle — the chunks plus the client profile + primary CSM
metadata the prompt construction layer needs to address the client
by name and route escalations correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.db import get_client
from shared.kb_query import Chunk, search_for_client


@dataclass(frozen=True)
class ContextBundle:
    """Everything the agent needs to answer one client question."""

    chunks: list[Chunk]
    client: dict[str, Any]
    primary_csm: dict[str, Any] | None


def retrieve_context_for_client(
    client_id: str,
    query: str,
    *,
    k: int = 8,
    include_global: bool = True,
) -> ContextBundle:
    """Pull top-k chunks for this client's query plus profile context.

    Delegates retrieval to `shared.kb_query.search_for_client` (which
    handles the safety invariants via `match_document_chunks`).
    Performs two lightweight follow-up SELECTs to fetch the client's
    profile and their primary CSM for prompt construction.
    """
    chunks = search_for_client(
        query,
        client_id=client_id,
        k=k,
        include_global=include_global,
    )

    db = get_client()
    client = _fetch_client(db, client_id)
    primary_csm = _fetch_primary_csm(db, client_id)

    return ContextBundle(chunks=chunks, client=client, primary_csm=primary_csm)


def _fetch_client(db, client_id: str) -> dict[str, Any]:
    resp = db.table("clients").select("*").eq("id", client_id).execute()
    rows = resp.data or []
    return rows[0] if rows else {}


def _fetch_primary_csm(db, client_id: str) -> dict[str, Any] | None:
    """Walk `client_team_assignments` → `team_members` for the client's
    current primary_csm, if any. Returns None when no active primary
    is assigned (rare today; `scripts/seed_clients.py` sets the
    majority)."""
    assignments = (
        db.table("client_team_assignments")
        .select("team_member_id")
        .eq("client_id", client_id)
        .eq("role", "primary_csm")
        .is_("unassigned_at", "null")
        .execute()
    )
    if not assignments.data:
        return None
    tm_id = assignments.data[0]["team_member_id"]
    tm_resp = db.table("team_members").select("*").eq("id", tm_id).execute()
    tm_rows = tm_resp.data or []
    return tm_rows[0] if tm_rows else None
