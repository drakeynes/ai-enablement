"""Backfill `call_summary` documents for the 15 client calls ingested by the
M1.2.5 cron sweep.

Why this exists:

  M1.2.5's first cron run (2026-04-27) ingested 29 calls successfully — but
  the 15 client-category calls all landed without a `call_summary` document
  because the adapter's `_extract_summary_text` didn't recognize Fathom's
  actual key (`markdown_formatted` vs the spec-driven `markdown`/`text`/
  /etc. fallback list). Adapter fixed in the same commit that adds this
  script. This script repairs the in-flight gap.

What it does:

  1. Read `webhook_deliveries` rows with `source='fathom_cron'` AND
     `processing_status='processed'` — those carry the full raw payload
     in jsonb.
  2. For each: filter to ones whose call already has a `call_transcript_chunk`
     document but NO `call_summary` document (the bug-affected set).
  3. Re-run `record_from_webhook` (now with the markdown_formatted fix) →
     `pipeline.ingest_call`. The pipeline is idempotent on every existing
     row (transcript chunks reused, action_items delete-and-replace lands
     the same data, calls UPSERT no-ops), and writes the missing summary
     document fresh.
  4. Verify: count `call_summary` docs before and after, log per-call.

Cost: one OpenAI embedding call per summary (single chunk per summary in V1).
~15 embeddings → < $0.001.

No Fathom API calls — we re-use the payload jsonb already in cloud.

Idempotent: re-running after a successful run is a no-op (the existing
summary doc + chunk would be reused, no fresh embedding cost).

Run:
    .venv/bin/python scripts/backfill_summary_docs_for_fathom_cron.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv
load_dotenv(_REPO / ".env.local")

from shared.db import get_client  # noqa: E402
from shared.kb_query import embed  # noqa: E402
from ingestion.fathom.pipeline import ingest_call, load_resolvers  # noqa: E402
from ingestion.fathom.webhook_adapter import record_from_webhook  # noqa: E402


def _candidates(db) -> list[dict]:
    """Find webhook_deliveries rows whose calls have no summary doc yet.

    Filters down to the bug-affected set: client-category calls ingested
    via the cron path, with a transcript_chunk doc present but no
    summary doc. This is exactly the set M1.2.5 fixed-and-noted.
    """
    # Pull all processed fathom_cron deliveries
    deliveries = (
        db.table("webhook_deliveries")
        .select("webhook_id,call_external_id,payload")
        .eq("source", "fathom_cron")
        .eq("processing_status", "processed")
        .execute()
    ).data or []
    print(f"  fathom_cron processed rows: {len(deliveries)}")

    # Of those, which already have a call_summary doc? Skip them.
    ext_ids = [d["call_external_id"] for d in deliveries if d.get("call_external_id")]
    if not ext_ids:
        return []
    summary_docs = (
        db.table("documents")
        .select("external_id")
        .eq("source", "fathom")
        .eq("document_type", "call_summary")
        .in_("external_id", ext_ids)
        .execute()
    ).data or []
    have_summary = {row["external_id"] for row in summary_docs}
    print(f"  external_ids already with call_summary: {len(have_summary)}")

    # Of the rest, which are client-category? Non-client calls don't get
    # summary docs by design (`_INDEXABLE_CATEGORIES = {"client"}`).
    rows = (
        db.table("calls")
        .select("external_id,call_category")
        .eq("source", "fathom")
        .in_("external_id", ext_ids)
        .execute()
    ).data or []
    client_ext_ids = {r["external_id"] for r in rows if r["call_category"] == "client"}
    print(f"  client-category calls in cron set: {len(client_ext_ids)}")

    candidates = [
        d for d in deliveries
        if d.get("call_external_id") in client_ext_ids
        and d.get("call_external_id") not in have_summary
    ]
    return candidates


def _summary_doc_count(db) -> int:
    return (
        db.table("documents")
        .select("id", count="exact")
        .eq("source", "fathom")
        .eq("document_type", "call_summary")
        .execute()
    ).count or 0


def main() -> int:
    db = get_client()

    print("=" * 78)
    print("Backfill call_summary docs for M1.2.5 cron-ingested calls")
    print("=" * 78)

    print("\nStep 1: identify candidate deliveries")
    candidates = _candidates(db)
    print(f"  → {len(candidates)} calls need a summary backfill")

    if not candidates:
        print("\nNothing to do. Exiting.")
        return 0

    summary_before = _summary_doc_count(db)
    print(f"\n  call_summary docs in cloud before: {summary_before}")

    print("\nStep 2: load resolvers (one-shot, reused across all backfills)")
    client_resolver, team_resolver, _ = load_resolvers(db)

    print("\nStep 3: re-run each through adapter + pipeline")
    successes: list[str] = []
    failures: list[tuple[str, str]] = []
    for d in candidates:
        ext_id = d["call_external_id"]
        payload = d["payload"]
        try:
            record = record_from_webhook(payload)
            if not record.summary_text:
                # Adapter couldn't extract — shouldn't happen post-fix
                # against these payloads, but log defensively.
                failures.append((ext_id, "adapter returned summary_text=None"))
                print(f"  [SKIP] {ext_id} — no summary_text after adapter (would be a separate bug)")
                continue
            outcome = ingest_call(
                record, db,
                client_resolver=client_resolver,
                team_resolver=team_resolver,
                embed_fn=embed,
                file_size_bytes=None,
                dry_run=False,
            )
            successes.append(ext_id)
            print(f"  [OK]   {ext_id}  action={outcome.action}  summary_chars={len(record.summary_text)}")
        except Exception as exc:
            failures.append((ext_id, repr(exc)))
            print(f"  [FAIL] {ext_id}  — {exc}")

    summary_after = _summary_doc_count(db)
    print(f"\n  call_summary docs in cloud after:  {summary_after}  (delta +{summary_after - summary_before})")

    print("\nStep 4: per-call verification")
    if successes:
        # Pull the new summary docs to confirm they actually landed
        verif = (
            db.table("documents")
            .select("external_id,is_active,content")
            .eq("source", "fathom")
            .eq("document_type", "call_summary")
            .in_("external_id", successes)
            .execute()
        ).data or []
        verif_map = {r["external_id"]: r for r in verif}
        for ext in successes:
            row = verif_map.get(ext)
            if not row:
                print(f"  [MISSING] {ext}  — no summary doc found post-ingest!")
                continue
            content_len = len(row.get("content") or "")
            print(f"  {ext}  is_active={row.get('is_active')}  content_chars={content_len}")

    print("\n" + "=" * 78)
    print(f"BACKFILL COMPLETE — {len(successes)} succeeded, {len(failures)} failed")
    print("=" * 78)
    if failures:
        for ext, err in failures:
            print(f"  fail: {ext} — {err}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
