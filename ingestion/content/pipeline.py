"""Orchestrator for the filesystem content ingestion pipeline.

Per-file flow:

  1. Parse the HTML file via `ingestion.content.parser`.
  2. Derive tags from the file path relative to the content root via
     `ingestion.content.tagger`.
  3. Compute a sha256 hash of the raw file bytes. Stored in
     `documents.metadata.source_content_hash` so re-runs can tell
     unchanged files from content-changed ones and skip re-embedding
     when nothing changed.
  4. Upsert the `documents` row on `(source='manual',
     external_id=<relative_path>)`. Behavior branches:
       - First ingest: insert document, chunk + embed, insert chunks.
       - Re-ingest with same hash: skip chunking AND skip embedding.
       - Re-ingest with different hash: update document, delete
         existing chunks for the document_id, chunk + embed, insert.
  5. Validator (`shared.ingestion.validate`) runs before every
     documents / document_chunks write. Manual source has no required
     metadata keys, so a happy-path lesson passes silently.

Chunk metadata is deliberately passed through as `{}` — there's no
pinned chunk-spec for (manual, course_lesson) in the conventions doc
yet, and the chunker's `chunk_word_count` is duplicable from the
content itself. When we add chunk-level conventions for manual docs,
update this function and the validator together.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ingestion.content.chunker import Chunk, chunk_text
from ingestion.content.parser import ContentRecord, parse_file
from ingestion.content.tagger import tags_for_path
from shared.ingestion.validate import validate_document_metadata
from shared.logging import logger

_SOURCE = "manual"
_DOCUMENT_TYPE = "course_lesson"

# Content authors mark retired lessons by prefixing the filename with
# "NOT IN USE" (observed across SALES PROCESS MODULE/ and MARKET
# SELECTION MODULE/). We respect the marker — ingest the rows so the
# content is preserved in the DB, but:
#   - append the `not_in_use` tag
#   - set `is_active=false` so they're invisible to match_document_chunks
#
# If the content ever comes out of retirement, flip is_active=true and
# drop the tag manually (or rename the file + re-ingest).
_NOT_IN_USE_TAG = "not_in_use"


def _is_not_in_use(source_path: Path) -> bool:
    """Filename (stem) starts with `not in use` — case-insensitive."""
    return source_path.stem.lower().startswith("not in use")

# Cost-estimate constants — mirror the Fathom pipeline's accounting.
# text-embedding-3-small at $0.02 per 1M tokens, ~500 tokens per chunk.
_EMBEDDING_COST_USD_PER_MILLION_TOKENS = 0.02
_EMBEDDING_TOKENS_PER_CHUNK_ESTIMATE = 500


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentIngestOutcome:
    source_path: Path
    external_id: str
    title: str
    tags: list[str]
    word_count: int
    chunk_count: int
    content_hash: str
    document_id: str | None
    chunks_written: int
    chunks_reused: int
    action: str
    validation_failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-file entry point
# ---------------------------------------------------------------------------


def ingest_file(
    source_path: Path,
    content_root: Path,
    db,
    *,
    embed_fn: Callable[[str], list[float]] | None = None,
    dry_run: bool = True,
) -> ContentIngestOutcome:
    """Parse, tag, and ingest one HTML lesson. See module docstring."""
    source_path = source_path.resolve()
    content_root = content_root.resolve()
    relative_path = source_path.relative_to(content_root)

    record = parse_file(source_path)
    tags = tags_for_path(relative_path)
    content_hash = _content_hash(source_path)

    # Retired-content flag. When a filename starts with "NOT IN USE",
    # tag the row and mark it inactive — chunks still get written so
    # the content is queryable after manual promotion, but
    # match_document_chunks won't surface them in live retrieval.
    retired = _is_not_in_use(source_path)
    if retired:
        tags = tags + [_NOT_IN_USE_TAG]
    is_active = not retired

    chunks = chunk_text(record.text)

    if dry_run:
        return _dry_run_outcome(record, relative_path, tags, content_hash, chunks)

    doc_metadata = _build_document_metadata(record, content_hash)
    validation_failures: list[str] = []
    try:
        validate_document_metadata(
            doc_metadata, source=_SOURCE, document_type=_DOCUMENT_TYPE
        )
    except ValueError as exc:
        validation_failures.append(f"document: {exc}")
        logger.error("Document validation failed for %s: %s", relative_path, exc)
        return _failed_outcome(
            record, relative_path, tags, content_hash, chunks, validation_failures
        )

    existing = _find_existing(db, str(relative_path))
    if existing is None:
        document_id = _insert_document(
            db, record, relative_path, tags, doc_metadata, is_active=is_active
        )
        chunks_written = _insert_chunks(db, document_id, chunks, embed_fn)
        return ContentIngestOutcome(
            source_path=source_path,
            external_id=str(relative_path),
            title=record.title,
            tags=tags,
            word_count=len(record.text.split()),
            chunk_count=len(chunks),
            content_hash=content_hash,
            document_id=document_id,
            chunks_written=chunks_written,
            chunks_reused=0,
            action="inserted",
            validation_failures=validation_failures,
        )

    document_id = existing["id"]
    existing_hash = (existing.get("metadata") or {}).get("source_content_hash")

    if existing_hash == content_hash:
        # Content unchanged — touch nothing. Chunks from the prior
        # ingest remain in place.
        chunk_count = _count_chunks(db, document_id)
        return ContentIngestOutcome(
            source_path=source_path,
            external_id=str(relative_path),
            title=record.title,
            tags=tags,
            word_count=len(record.text.split()),
            chunk_count=chunk_count,
            content_hash=content_hash,
            document_id=document_id,
            chunks_written=0,
            chunks_reused=chunk_count,
            action="skipped_unchanged",
            validation_failures=validation_failures,
        )

    # Content changed — update document, replace chunks.
    _update_document(db, document_id, record, tags, doc_metadata, is_active=is_active)
    _delete_chunks(db, document_id)
    chunks_written = _insert_chunks(db, document_id, chunks, embed_fn)
    return ContentIngestOutcome(
        source_path=source_path,
        external_id=str(relative_path),
        title=record.title,
        tags=tags,
        word_count=len(record.text.split()),
        chunk_count=len(chunks),
        content_hash=content_hash,
        document_id=document_id,
        chunks_written=chunks_written,
        chunks_reused=0,
        action="updated_content_changed",
        validation_failures=validation_failures,
    )


# ---------------------------------------------------------------------------
# Metadata / hashing
# ---------------------------------------------------------------------------


def _content_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_document_metadata(record: ContentRecord, content_hash: str) -> dict[str, Any]:
    """Five keys, aligned with the `manual` source convention."""
    return {
        "source_content_hash": content_hash,
        "source_filename": record.source_path.name,
        "raw_bytes_len": record.raw_bytes_len,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _find_existing(db, external_id: str) -> dict[str, Any] | None:
    resp = (
        db.table("documents")
        .select("id,metadata,is_active")
        .eq("source", _SOURCE)
        .eq("external_id", external_id)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _insert_document(
    db,
    record: ContentRecord,
    relative_path: Path,
    tags: list[str],
    metadata: dict[str, Any],
    *,
    is_active: bool,
) -> str:
    payload = {
        "source": _SOURCE,
        "external_id": str(relative_path),
        "title": record.title,
        "content": record.text,
        "document_type": _DOCUMENT_TYPE,
        "tags": tags,
        "metadata": metadata,
        "is_active": is_active,
    }
    resp = db.table("documents").insert(payload).execute()
    return resp.data[0]["id"]


def _update_document(
    db,
    document_id: str,
    record: ContentRecord,
    tags: list[str],
    metadata: dict[str, Any],
    *,
    is_active: bool,
) -> None:
    payload = {
        "title": record.title,
        "content": record.text,
        "tags": tags,
        "metadata": metadata,
        "is_active": is_active,
    }
    db.table("documents").update(payload).eq("id", document_id).execute()


def _count_chunks(db, document_id: str) -> int:
    resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .execute()
    )
    return resp.count or 0


def _delete_chunks(db, document_id: str) -> None:
    db.table("document_chunks").delete().eq("document_id", document_id).execute()


def _insert_chunks(
    db,
    document_id: str,
    chunks: list[Chunk],
    embed_fn: Callable[[str], list[float]] | None,
) -> int:
    """Embed + insert each chunk. Chunk metadata is left as {} —
    see module docstring for why."""
    if not chunks:
        return 0
    if embed_fn is None:
        raise RuntimeError(
            "embed_fn is required for --apply runs; pass shared.kb_query.embed."
        )
    written = 0
    for chunk in chunks:
        try:
            embedding = embed_fn(chunk.content)
        except Exception as exc:  # pragma: no cover — network path
            logger.error(
                "Embedding failed for document %s chunk %d: %s",
                document_id, chunk.chunk_index, exc,
            )
            continue
        db.table("document_chunks").upsert(
            {
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "embedding": embedding,
                "metadata": {},
            },
            on_conflict="document_id,chunk_index",
            ignore_duplicates=True,
        ).execute()
        written += 1
    return written


# ---------------------------------------------------------------------------
# Dry-run outcome builders
# ---------------------------------------------------------------------------


def _dry_run_outcome(
    record: ContentRecord,
    relative_path: Path,
    tags: list[str],
    content_hash: str,
    chunks: list[Chunk],
) -> ContentIngestOutcome:
    return ContentIngestOutcome(
        source_path=record.source_path,
        external_id=str(relative_path),
        title=record.title,
        tags=tags,
        word_count=len(record.text.split()),
        chunk_count=len(chunks),
        content_hash=content_hash,
        document_id=None,
        chunks_written=0,
        chunks_reused=0,
        action="dry-run",
    )


def _failed_outcome(
    record: ContentRecord,
    relative_path: Path,
    tags: list[str],
    content_hash: str,
    chunks: list[Chunk],
    validation_failures: list[str],
) -> ContentIngestOutcome:
    return ContentIngestOutcome(
        source_path=record.source_path,
        external_id=str(relative_path),
        title=record.title,
        tags=tags,
        word_count=len(record.text.split()),
        chunk_count=len(chunks),
        content_hash=content_hash,
        document_id=None,
        chunks_written=0,
        chunks_reused=0,
        action="validation_failed",
        validation_failures=validation_failures,
    )


# ---------------------------------------------------------------------------
# Cost estimate
# ---------------------------------------------------------------------------


def estimate_embedding_cost_usd(chunks_written: int) -> float:
    tokens = chunks_written * _EMBEDDING_TOKENS_PER_CHUNK_ESTIMATE
    return tokens * _EMBEDDING_COST_USD_PER_MILLION_TOKENS / 1_000_000
