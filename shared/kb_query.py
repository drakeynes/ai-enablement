"""Knowledge-base retrieval.

Two entry points:
  - `search_global(query, ...)`     — course content, FAQs, SOPs, methodology, onboarding
  - `search_for_client(query, ...)` — adds that client's call summaries to the mix

Both wrap the `match_document_chunks` Postgres function defined in
migration 0008. Agents never touch `document_chunks` directly; they go
through this module. The function enforces the call_summary safety gate
so a bug in a caller cannot leak one client's calls into another
client's retrieval.

See docs/schema/document_chunks.md for the search function's full
contract.

Example:

    from shared.kb_query import search_global, search_for_client

    chunks = search_global(
        "how do I set up my first sales call?",
        k=6,
        document_types=["course_lesson", "faq"],
    )

    chunks = search_for_client(
        "what did we discuss last call?",
        client_id=client.id,
        k=8,
        include_global=True,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from openai import OpenAI

from shared.db import get_client

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


@dataclass(frozen=True)
class Chunk:
    """One retrieved chunk, ready to drop into a prompt."""

    chunk_id: str
    document_id: str
    document_type: str
    document_title: str
    document_created_at: datetime
    content: str
    chunk_index: int
    similarity: float
    metadata: dict[str, Any]


@lru_cache(maxsize=1)
def _openai_client() -> OpenAI:
    return OpenAI()


@lru_cache(maxsize=512)
def _embed_cached(text: str) -> tuple[float, ...]:
    response = _openai_client().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return tuple(response.data[0].embedding)


def embed(text: str) -> list[float]:
    """Return the embedding for `text`.

    Uses OpenAI `text-embedding-3-small` (1536 dims, matches
    `document_chunks.embedding`). Cached in-process for exact-match
    queries — safe to call repeatedly during a single request.
    """
    return list(_embed_cached(text))


def search_global(
    query: str,
    *,
    k: int = 8,
    document_types: list[str] | None = None,
    tags: list[str] | None = None,
    min_similarity: float = 0.0,
) -> list[Chunk]:
    """Top-k retrieval across globally-retrievable documents.

    Filters to `documents.is_active = true`. Never returns
    `call_summary` chunks — those require a client id and go through
    `search_for_client`.
    """
    return _rpc_match(
        embedding=embed(query),
        match_count=k,
        document_types=document_types,
        tags=tags,
        min_similarity=min_similarity,
        client_id=None,
        include_global=True,
    )


def search_for_client(
    query: str,
    client_id: str,
    *,
    k: int = 8,
    include_global: bool = True,
    document_types: list[str] | None = None,
    tags: list[str] | None = None,
    min_similarity: float = 0.0,
) -> list[Chunk]:
    """Top-k retrieval for a specific client.

    Always includes `call_summary` chunks whose
    `documents.metadata->>'client_id'` matches `client_id`. With
    `include_global = True` (default), also mixes in matches from
    non-call-summary active documents; the combined list is capped at
    `k` and ranked by similarity.
    """
    return _rpc_match(
        embedding=embed(query),
        match_count=k,
        document_types=document_types,
        tags=tags,
        min_similarity=min_similarity,
        client_id=client_id,
        include_global=include_global,
    )


def _rpc_match(
    *,
    embedding: list[float],
    match_count: int,
    document_types: list[str] | None,
    tags: list[str] | None,
    min_similarity: float,
    client_id: str | None,
    include_global: bool,
) -> list[Chunk]:
    response = (
        get_client()
        .rpc(
            "match_document_chunks",
            {
                "query_embedding": embedding,
                "match_count": match_count,
                "document_types": document_types,
                "tags": tags,
                "min_similarity": min_similarity,
                "client_id": client_id,
                "include_global": include_global,
            },
        )
        .execute()
    )
    return [_row_to_chunk(row) for row in (response.data or [])]


def _row_to_chunk(row: dict[str, Any]) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        document_type=row["document_type"],
        document_title=row["document_title"],
        document_created_at=datetime.fromisoformat(row["document_created_at"]),
        content=row["content"],
        chunk_index=row["chunk_index"],
        similarity=float(row["similarity"]),
        metadata=row.get("metadata") or {},
    )
