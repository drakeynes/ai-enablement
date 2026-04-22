"""Orchestrator for the Fathom backlog ingestion pipeline.

Per-call flow:

  1. Classify the parsed record via `ingestion.fathom.classifier.classify`.
  2. If the classifier emitted an `AutoCreateRequest`, do the
     lookup-by-email-first-insert-second dance so repeated calls with
     the same unmatched participant reuse one auto-created client row.
  3. Upsert the `calls` row keyed on `(source='fathom', external_id)`.
     Retrievability rule is asymmetric per conventions §6:
       - first-ingest → set `is_retrievable_by_client_agents` from the
         classifier's floor check
       - re-ingest demote → flip to false automatically
       - re-ingest promote → NEVER flip to true automatically (a human
         must make that call via manual review)
  4. Upsert `call_participants` linking emails to `clients` /
     `team_members` where resolvable.
  5. `call_action_items` is NEVER populated from TXT backlog ingestion —
     see the deferral note in docs/ingestion/metadata-conventions.md §5.
  6. Skip `call_summary` document creation — same deferral reason (the
     TXT exports don't carry summaries).
  7. For client-category calls only, create or update a parent document
     with `document_type='call_transcript_chunk'` plus its N child
     `document_chunks`. The parent document's `is_active` is set from
     the same retrievability value that `calls.is_retrievable_by_
     client_agents` carries — medium-confidence (auto-created) calls
     land with `is_active=false` so chunks exist but don't surface in
     `match_document_chunks`. See `docs/future-ideas.md` →
     "match_document_chunks: enforce calls retrievability via SQL
     join" for the eventual function-side upgrade. Re-ingest that
     already has chunks skips re-chunking (conventions §6) but syncs
     denormalized metadata AND is_active.
  8. For non-client re-ingest of a call that previously had chunks:
     soft-archive the parent document (`is_active=false`). Chunks
     become invisible to `match_document_chunks` automatically.

**Non-atomic but idempotent.** supabase-py writes go through
PostgREST one request at a time; cross-request transactions aren't
available. Every write in this module is upsert-shaped and keyed on
stable identifiers, so a partial failure recovers on re-run without
leaving duplicate rows. See the "Atomic per-call ingest via Postgres
RPC" entry in docs/future-ideas.md for the eventual upgrade path.

Validators (`shared.ingestion.validate`) run before every `documents`
or `document_chunks` write. A validation failure is logged to the
`IngestOutcome` and the specific write is skipped; other writes for
the same call continue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ingestion.fathom.classifier import (
    AMAN_EMAIL,
    AutoCreateRequest,
    ClassificationResult,
    ClientResolver,
    classify,
)
from ingestion.fathom.chunker import Chunk, chunk_transcript
from ingestion.fathom.parser import FathomCallRecord
from shared.ingestion.validate import (
    validate_chunk_metadata,
    validate_document_metadata,
)
from shared.logging import logger

_SOURCE = "fathom"
_TRANSCRIPT_DOC_TYPE = "call_transcript_chunk"
# Classifier categories that are worth indexing to document_chunks for
# retrieval today. Only client calls land in documents/document_chunks
# in V1 — internal and external categories get a `calls` row but no
# chunks. CSM Co-Pilot will extend this in a later session.
_INDEXABLE_CATEGORIES: frozenset[str] = frozenset({"client"})

# For cost-estimate reporting in the CLI. Update if Anthropic/OpenAI
# change prices (OpenAI text-embedding-3-small as of 2026-04).
_EMBEDDING_COST_USD_PER_MILLION_TOKENS = 0.02
_EMBEDDING_TOKENS_PER_CHUNK_ESTIMATE = 500


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestOutcome:
    """What happened for one call."""

    external_id: str
    call_id: str | None
    category: str
    call_type: str | None
    confidence: float
    method: str
    primary_client_id: str | None
    primary_client_name: str | None
    auto_created_client_id: str | None
    auto_created_client_email: str | None
    participants_linked_to_clients: int
    participants_linked_to_team: int
    document_id: str | None
    chunks_written: int
    chunks_reused: int
    retrievable: bool
    retrievable_before: bool | None
    action: str
    validation_failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class TeamMemberResolver:
    """Resolve team member emails to `team_members.id`. Case-insensitive."""

    def __init__(self, id_by_email: dict[str, str]):
        self._map: dict[str, str] = {e.lower(): tmid for e, tmid in id_by_email.items()}

    def lookup(self, email: str) -> str | None:
        if not email:
            return None
        return self._map.get(email.lower())


# ---------------------------------------------------------------------------
# Resolver loading
# ---------------------------------------------------------------------------


def load_resolvers(db) -> tuple[ClientResolver, TeamMemberResolver, dict[str, str]]:
    """Single-SELECT-each prefetch of the lookup tables.

    Returns `(client_resolver, team_member_resolver, client_id_to_name)`.
    The name map is used for dry-run display (matched client names).
    """
    client_resp = (
        db.table("clients")
        .select("id,email,full_name")
        .is_("archived_at", "null")
        .execute()
    )
    team_resp = db.table("team_members").select("id,email").is_("archived_at", "null").execute()

    client_id_by_email: dict[str, str] = {}
    client_id_to_name: dict[str, str] = {}
    for row in client_resp.data or []:
        client_id_by_email[row["email"]] = row["id"]
        client_id_to_name[row["id"]] = row["full_name"]

    team_id_by_email: dict[str, str] = {}
    for row in team_resp.data or []:
        team_id_by_email[row["email"]] = row["id"]

    return (
        ClientResolver(client_id_by_email),
        TeamMemberResolver(team_id_by_email),
        client_id_to_name,
    )


# ---------------------------------------------------------------------------
# Per-call entry point
# ---------------------------------------------------------------------------


def ingest_call(
    record: FathomCallRecord,
    db,
    *,
    client_resolver: ClientResolver,
    team_resolver: TeamMemberResolver,
    embed_fn: Callable[[str], list[float]] | None = None,
    file_size_bytes: int | None = None,
    dry_run: bool = True,
) -> IngestOutcome:
    """Run the full per-call flow. See module docstring."""
    validation_failures: list[str] = []
    errors: list[str] = []

    classification = classify(
        record, client_resolver, file_size_bytes=file_size_bytes
    )

    auto_created_id: str | None = None
    auto_created_email: str | None = None
    if classification.should_auto_create_client and not dry_run:
        auto_created_id, auto_created_email = _lookup_or_create_auto_client(
            db,
            classification.should_auto_create_client,
            client_resolver,
            record,
        )
        # Promote classification's primary_client_id to the resolved id
        # so downstream writes carry it. Confidence stays medium —
        # per conventions §5 step 4, only a known-client match promotes.
        classification = _with_primary_client_id(classification, auto_created_id)

    if dry_run:
        return _dry_run_outcome(
            record, classification, client_resolver, auto_created_email
        )

    call_id, was_pre_existing, retrievable_before, final_retrievable = _upsert_call_row(
        db, record, classification
    )

    linked_clients, linked_team = _upsert_participants(
        db, call_id, record, client_resolver, team_resolver
    )

    document_id: str | None = None
    chunks_written = 0
    chunks_reused = 0

    if classification.call_category in _INDEXABLE_CATEGORIES:
        # Index the transcript chunks. Existing doc → sync metadata,
        # reuse chunks unless there are none. No existing doc → create
        # doc + chunks.
        doc_metadata = _build_document_metadata(record, classification, call_id)
        document_id, chunks_written, chunks_reused, doc_validation_failures = (
            _ensure_transcript_chunks(
                db, record, call_id, classification, embed_fn, doc_metadata,
                retrievable=final_retrievable,
            )
        )
        validation_failures.extend(doc_validation_failures)
    else:
        # Non-client call. If a prior client-classification wrote a
        # document for this call, soft-archive it so chunks stop
        # appearing in client-mode retrieval.
        document_id = _soft_archive_transcript_document_if_exists(db, call_id)

    action = "updated" if was_pre_existing else "inserted"

    return IngestOutcome(
        external_id=record.external_id,
        call_id=call_id,
        category=classification.call_category,
        call_type=classification.call_type,
        confidence=classification.classification_confidence,
        method=classification.classification_method,
        primary_client_id=classification.primary_client_id,
        primary_client_name=None,  # filled by CLI-side enrichment
        auto_created_client_id=auto_created_id,
        auto_created_client_email=auto_created_email,
        participants_linked_to_clients=linked_clients,
        participants_linked_to_team=linked_team,
        document_id=document_id,
        chunks_written=chunks_written,
        chunks_reused=chunks_reused,
        retrievable=final_retrievable,
        retrievable_before=retrievable_before,
        action=action,
        validation_failures=validation_failures,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Auto-create client
# ---------------------------------------------------------------------------


def _lookup_or_create_auto_client(
    db,
    request: AutoCreateRequest,
    resolver: ClientResolver,
    record: FathomCallRecord,
) -> tuple[str, str]:
    """Lookup by email first; only insert if missing. Update the
    in-memory resolver so subsequent calls in the same batch reuse the
    row rather than double-insert.

    Metadata carries a breadcrumb back to the triggering call — the
    reviewer workflow (see `docs/future-ideas.md` → "Auto-created
    client review workflow") uses these fields to find the recording
    that prompted the auto-create.
    """
    email = request.email.lower()

    # First: check if this email already exists in clients, archived or not.
    resp = (
        db.table("clients").select("id,archived_at").eq("email", email).execute()
    )
    existing_active = next(
        (r for r in (resp.data or []) if r.get("archived_at") is None),
        None,
    )
    if existing_active is not None:
        resolver._map[email] = existing_active["id"]  # noqa: SLF001
        return existing_active["id"], email

    auto_metadata = _build_auto_create_metadata(request, record)

    # Second: if an archived row exists, reactivate it rather than insert
    # a new one. Preserves history under the partial unique index.
    existing_archived = next((r for r in (resp.data or [])), None)
    if existing_archived is not None:
        db.table("clients").update({
            "archived_at": None,
            "tags": ["needs_review"],
            "metadata": auto_metadata,
        }).eq("id", existing_archived["id"]).execute()
        resolver._map[email] = existing_archived["id"]  # noqa: SLF001
        return existing_archived["id"], email

    # Third: actually insert.
    payload = {
        "email": email,
        "full_name": request.display_name or email.split("@", 1)[0],
        "status": "active",
        "tags": ["needs_review"],
        "metadata": auto_metadata,
    }
    insert_resp = db.table("clients").insert(payload).execute()
    new_id = insert_resp.data[0]["id"]
    resolver._map[email] = new_id  # noqa: SLF001
    return new_id, email


def _build_auto_create_metadata(
    request: AutoCreateRequest, record: FathomCallRecord
) -> dict[str, Any]:
    return {
        "auto_created_from_call_ingestion": True,
        "auto_created_from_call_external_id": record.external_id,
        "auto_created_from_call_title": record.title,
        "auto_create_reason": request.reason,
        "auto_created_at": datetime.now(timezone.utc).isoformat(),
    }


def _with_primary_client_id(
    classification: ClassificationResult, new_id: str
) -> ClassificationResult:
    """Return a copy of the classification with primary_client_id set."""
    from dataclasses import replace
    return replace(classification, primary_client_id=new_id)


# ---------------------------------------------------------------------------
# calls row upsert + retrievability floor
# ---------------------------------------------------------------------------


def _upsert_call_row(
    db, record: FathomCallRecord, classification: ClassificationResult
) -> tuple[str, bool, bool | None, bool]:
    """Insert or update the calls row. Returns
    (call_id, was_pre_existing, retrievable_before, final_retrievable)."""
    existing_resp = (
        db.table("calls")
        .select("id,is_retrievable_by_client_agents")
        .eq("source", _SOURCE)
        .eq("external_id", record.external_id)
        .execute()
    )
    existing = (existing_resp.data or [None])[0]

    new_should_retrieve = classification.should_be_retrievable
    retrievable_before: bool | None = None
    if existing is None:
        # First ingest — retrievability follows the classifier's floor.
        final_retrievable = new_should_retrieve
    else:
        retrievable_before = bool(existing["is_retrievable_by_client_agents"])
        if retrievable_before and not new_should_retrieve:
            # Demote — classifier floor no longer passes.
            final_retrievable = False
        else:
            # Never auto-promote. If it was false, it stays false until
            # a human reviews. If it was true and still passes, keep true.
            final_retrievable = retrievable_before and new_should_retrieve

    payload = {
        "source": _SOURCE,
        "external_id": record.external_id,
        "title": record.title,
        "call_category": classification.call_category,
        "call_type": classification.call_type,
        "classification_confidence": classification.classification_confidence,
        "classification_method": classification.classification_method,
        "primary_client_id": classification.primary_client_id,
        "started_at": record.started_at.isoformat(),
        "duration_seconds": record.duration_seconds,
        "recording_url": record.recording_url,
        "transcript": record.transcript,
        "is_retrievable_by_client_agents": final_retrievable,
        "raw_payload": _raw_payload(record),
    }

    if existing is None:
        resp = db.table("calls").insert(payload).execute()
        call_id = resp.data[0]["id"]
        return call_id, False, None, final_retrievable

    call_id = existing["id"]
    db.table("calls").update(payload).eq("id", call_id).execute()
    return call_id, True, retrievable_before, final_retrievable


def _raw_payload(record: FathomCallRecord) -> dict[str, Any]:
    """Capture source context in the jsonb column.

    The TXT export has no structured API response; we preserve the raw
    text verbatim so downstream extractions (future action items,
    summaries) can re-parse without re-fetching from Fathom.
    """
    source_filename = record.source_path.name if record.source_path else None
    return {
        "source_format": "txt",
        "source_filename": source_filename,
        "raw_text": record.raw_text,
        "parse_warnings": list(record.parse_warnings),
    }


# ---------------------------------------------------------------------------
# call_participants upsert
# ---------------------------------------------------------------------------


def _upsert_participants(
    db,
    call_id: str,
    record: FathomCallRecord,
    client_resolver: ClientResolver,
    team_resolver: TeamMemberResolver,
) -> tuple[int, int]:
    """Insert or refresh one call_participants row per attendee.

    Returns (matched_to_clients, matched_to_team) for the outcome
    report. Uses `on_conflict=(call_id, email)` so re-ingest doesn't
    duplicate rows.
    """
    recorded_by_email = (
        record.recorded_by.email.lower() if record.recorded_by else None
    )

    linked_clients = 0
    linked_team = 0
    payloads: list[dict[str, Any]] = []
    for pt in record.participants:
        email_lower = pt.email.lower()
        client_id = client_resolver.lookup(email_lower)
        team_id = team_resolver.lookup(email_lower)
        if client_id:
            linked_clients += 1
        if team_id:
            linked_team += 1
        participant_role = "host" if email_lower == recorded_by_email else "attendee"
        payloads.append({
            "call_id": call_id,
            "email": email_lower,
            "display_name": pt.display_name,
            "client_id": client_id,
            "team_member_id": team_id,
            "participant_role": participant_role,
        })

    if payloads:
        db.table("call_participants").upsert(
            payloads, on_conflict="call_id,email"
        ).execute()

    return linked_clients, linked_team


# ---------------------------------------------------------------------------
# Transcript document + chunks
# ---------------------------------------------------------------------------


def _ensure_transcript_chunks(
    db,
    record: FathomCallRecord,
    call_id: str,
    classification: ClassificationResult,
    embed_fn: Callable[[str], list[float]] | None,
    doc_metadata: dict[str, Any],
    *,
    retrievable: bool,
) -> tuple[str | None, int, int, list[str]]:
    """Idempotent chunk-and-embed for a client call.

    `retrievable` is the post-asymmetric-rule retrievability value for
    the parent `calls` row. It maps 1:1 to `documents.is_active` for the
    transcript_chunk document — today's invariant is "a transcript_chunk
    document surfaces via `match_document_chunks` iff its call is
    retrievable." Option (b) in `docs/future-ideas.md` moves the same
    check into the SQL function via a join; until then the pipeline
    enforces it at write time.

    Behavior:
      - No existing parent doc → insert parent (with `is_active =
        retrievable`), chunk, embed, insert all chunks.
      - Existing parent doc with chunks → sync metadata, sync is_active
        to the new retrievability, reuse chunks (conventions §6 forbids
        re-embedding on re-classification).
      - Existing parent doc with 0 chunks (partial-failure recovery) →
        sync metadata, sync is_active, chunk + embed + insert.

    Returns `(document_id, chunks_written, chunks_reused, validation_failures)`.
    """
    validation_failures: list[str] = []

    try:
        validate_document_metadata(
            doc_metadata, source=_SOURCE, document_type=_TRANSCRIPT_DOC_TYPE
        )
    except ValueError as exc:
        validation_failures.append(f"document: {exc}")
        logger.error("Document validation failed for call %s: %s", call_id, exc)
        return None, 0, 0, validation_failures

    existing = _find_transcript_document(db, call_id)

    if existing is None:
        doc_id = _insert_transcript_document(
            db, record, classification, doc_metadata, is_active=retrievable
        )
    else:
        doc_id = existing["id"]
        _sync_document_metadata(db, doc_id, existing, doc_metadata)
        # Sync is_active with the asymmetric retrievability result.
        # `retrievable` already respects the no-auto-promote rule,
        # so it's safe to pass through directly.
        if existing.get("is_active", True) != retrievable:
            db.table("documents").update(
                {"is_active": retrievable}
            ).eq("id", doc_id).execute()

    existing_chunk_count = _count_chunks(db, doc_id)
    if existing_chunk_count > 0:
        return doc_id, 0, existing_chunk_count, validation_failures

    # Produce and insert chunks.
    chunks = chunk_transcript(record.utterances)
    if not chunks:
        return doc_id, 0, 0, validation_failures

    written = _insert_chunks(
        db, doc_id, chunks, embed_fn, validation_failures
    )
    return doc_id, written, 0, validation_failures


def _build_document_metadata(
    record: FathomCallRecord,
    classification: ClassificationResult,
    call_id: str,
) -> dict[str, Any]:
    """Build the `documents.metadata` jsonb per conventions §2.

    `call_id` is the `calls.id` UUID (per the conventions doc: "Links
    back to calls.id"). Required keys per the validator: client_id,
    call_id, call_category, started_at.
    """
    return {
        "client_id": classification.primary_client_id,
        "call_id": call_id,
        "call_category": classification.call_category,
        "call_type": classification.call_type,
        "started_at": record.started_at.isoformat(),
        "duration_seconds": record.duration_seconds,
        "participant_emails": [pt.email for pt in record.participants],
        "speaker_list": _unique_speakers(record),
        "source_url": record.recording_url,
        "classification_confidence": classification.classification_confidence,
        "classification_method": classification.classification_method,
    }


def _unique_speakers(record: FathomCallRecord) -> list[str]:
    seen: set[str] = set()
    speakers: list[str] = []
    for u in record.utterances:
        if u.speaker and u.speaker not in seen:
            seen.add(u.speaker)
            speakers.append(u.speaker)
    return speakers


def _find_transcript_document(db, call_id: str) -> dict[str, Any] | None:
    """Find the parent transcript_chunk document for a given call, if any."""
    resp = (
        db.table("documents")
        .select("id,is_active,metadata")
        .eq("source", _SOURCE)
        .eq("document_type", _TRANSCRIPT_DOC_TYPE)
        .execute()
    )
    for row in resp.data or []:
        if (row.get("metadata") or {}).get("call_id") == call_id:
            return row
    return None


def _insert_transcript_document(
    db,
    record: FathomCallRecord,
    classification: ClassificationResult,
    metadata: dict[str, Any],
    *,
    is_active: bool,
) -> str:
    """Insert the parent call_transcript_chunk document.

    `is_active` is passed in rather than hard-coded True so a
    medium-confidence client call (auto-created participant, awaiting
    human review) lands with `is_active = false` — its chunks exist in
    the DB for future promotion but don't surface through
    `match_document_chunks` yet.
    """
    payload = {
        "source": _SOURCE,
        "external_id": record.external_id,
        "title": record.title,
        "content": record.transcript,
        "document_type": _TRANSCRIPT_DOC_TYPE,
        "metadata": metadata,
        "is_active": is_active,
    }
    resp = db.table("documents").insert(payload).execute()
    return resp.data[0]["id"]


def _sync_document_metadata(
    db, doc_id: str, existing: dict[str, Any], new_metadata: dict[str, Any]
) -> None:
    """Refresh denormalized fields on an existing document's metadata.

    Per conventions §6: re-classification updates the calls row's
    classification fields; the documents.metadata copy must follow so
    retrieval results reflect the current classification.
    """
    existing_metadata = existing.get("metadata") or {}
    merged = existing_metadata | new_metadata
    if merged == existing_metadata:
        return
    db.table("documents").update({"metadata": merged}).eq("id", doc_id).execute()


def _count_chunks(db, document_id: str) -> int:
    """Count chunks under a given document via PostgREST's `count=exact`.

    Using the count header rather than `len(resp.data)` — the row-data
    path can come back empty even when rows exist (observed on a
    partial-failure recovery run against a populated table) which
    would erroneously push the pipeline into a re-chunk + re-insert
    path and crash on the `(document_id, chunk_index)` unique index.
    """
    resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .execute()
    )
    return resp.count or 0


def _insert_chunks(
    db,
    document_id: str,
    chunks: list[Chunk],
    embed_fn: Callable[[str], list[float]] | None,
    validation_failures: list[str],
) -> int:
    """Validate and insert each chunk with its embedding.

    `embed_fn` is injected so the pipeline stays testable without an
    OpenAI key. The CLI plumbs `shared.kb_query.embed` into it.
    """
    if embed_fn is None:
        raise RuntimeError(
            "embed_fn is required for --apply runs; pass shared.kb_query.embed."
        )

    written = 0
    for chunk in chunks:
        try:
            validate_chunk_metadata(
                chunk.metadata, source=_SOURCE, document_type=_TRANSCRIPT_DOC_TYPE
            )
        except ValueError as exc:
            validation_failures.append(f"chunk index {chunk.chunk_index}: {exc}")
            logger.error(
                "Chunk validation failed for document %s chunk %d: %s",
                document_id, chunk.chunk_index, exc,
            )
            continue

        try:
            embedding = embed_fn(chunk.content)
        except Exception as exc:  # pragma: no cover — network path
            logger.error(
                "Embedding failed for document %s chunk %d: %s",
                document_id, chunk.chunk_index, exc,
            )
            continue

        # Idempotent insert: on conflict (document_id, chunk_index) do
        # nothing. Protects the pipeline from re-run after a partial
        # failure where some chunks landed and _count_chunks might
        # not have caught it before we got here.
        db.table("document_chunks").upsert(
            {
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "embedding": embedding,
                "metadata": chunk.metadata,
            },
            on_conflict="document_id,chunk_index",
            ignore_duplicates=True,
        ).execute()
        written += 1
    return written


def _soft_archive_transcript_document_if_exists(db, call_id: str) -> str | None:
    """Flip is_active=false on the parent document for this call, if any.

    Called when a re-classification moves the call out of client —
    keeps stale chunks out of client-mode retrieval via the
    is_active filter in match_document_chunks.
    """
    existing = _find_transcript_document(db, call_id)
    if existing is None:
        return None
    if existing.get("is_active") is False:
        return existing["id"]
    db.table("documents").update({"is_active": False}).eq("id", existing["id"]).execute()
    return existing["id"]


# ---------------------------------------------------------------------------
# Dry-run outcome
# ---------------------------------------------------------------------------


def _dry_run_outcome(
    record: FathomCallRecord,
    classification: ClassificationResult,
    client_resolver: ClientResolver,
    auto_created_email: str | None,
) -> IngestOutcome:
    """Build an IngestOutcome for a dry-run — no DB writes performed."""
    linked_clients = sum(
        1 for pt in record.participants if client_resolver.lookup(pt.email) is not None
    )
    return IngestOutcome(
        external_id=record.external_id,
        call_id=None,
        category=classification.call_category,
        call_type=classification.call_type,
        confidence=classification.classification_confidence,
        method=classification.classification_method,
        primary_client_id=classification.primary_client_id,
        primary_client_name=None,
        auto_created_client_id=None,
        auto_created_client_email=(
            classification.should_auto_create_client.email
            if classification.should_auto_create_client
            else None
        ),
        participants_linked_to_clients=linked_clients,
        participants_linked_to_team=0,
        document_id=None,
        chunks_written=0,
        chunks_reused=0,
        retrievable=classification.should_be_retrievable,
        retrievable_before=None,
        action="dry-run",
    )


# ---------------------------------------------------------------------------
# Embedding cost estimate
# ---------------------------------------------------------------------------


def estimate_embedding_cost_usd(chunks_written: int) -> float:
    """Rough estimate: `chunks_written × ~500 tokens × $0.02/1M`."""
    tokens = chunks_written * _EMBEDDING_TOKENS_PER_CHUNK_ESTIMATE
    return tokens * _EMBEDDING_COST_USD_PER_MILLION_TOKENS / 1_000_000
