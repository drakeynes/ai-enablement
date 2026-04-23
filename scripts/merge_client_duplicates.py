"""One-shot merge of auto-created client duplicates back into the
canonical Active++ rows they should have resolved to at ingest time.

Idempotent — re-running after a successful merge is a no-op for the
merge-body steps (the auto row's `metadata.merged_into` flag gates
them). The alternate_emails / alternate_names sync on the real row
runs every invocation and dedupes, so it fills in retroactive gaps
for pairs merged before those fields were added.

Targets (hard-coded for this one-shot):

  - Dhamen Hothi:   dhamenhothi@gmail.com        ← dhamen@flowstatetech.co
  - Javi Pena:      javpen93@gmail.com           ← javier@buildficial.com
  - Nicholas LoScalzo: nicholasvloscalzo@gmail.com ← nicholas@builtwithprecisionai.com
  - Musa Elmaghrabi: legendarywork1@gmail.com    ← musa@infiniteauraai.com
                                                   (auto row full_name "King Musa")

Per-merge operations (all within a single run, non-transactional —
partial failure is recoverable on re-run via the idempotency check):

  1. `call_participants.client_id`: auto → real
  2. `calls.primary_client_id`: auto → real
     Also set `calls.is_retrievable_by_client_agents = true` for those
     calls. The real client is now known; this is a human-directed
     promotion (the asymmetric rule's "only a human promotes").
  3. For every transcript_chunk document linked to those calls:
     `metadata.client_id`: auto → real, and `is_active = true`.
  4. Soft-archive the auto row: `archived_at = now()`, stamp
     `metadata.merged_into` and `metadata.merged_at`.
  5. Add the auto email to the real row's `metadata.alternate_emails`
     (dedup). If the auto row's `full_name` differs from the real's,
     add it to `metadata.alternate_names` too.

The alt-emails and alt-names are the handle future Fathom ingest uses
to resolve the old email or the old name back to the real row —
requires the companion classifier change that consults those fields.

Usage:

    python scripts/merge_client_duplicates.py          # dry-run
    python scripts/merge_client_duplicates.py --apply
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.db import get_client  # noqa: E402


@dataclass(frozen=True)
class MergePair:
    label: str
    real_email: str
    auto_email: str


MERGES: tuple[MergePair, ...] = (
    MergePair("Dhamen Hothi", "dhamenhothi@gmail.com", "dhamen@flowstatetech.co"),
    MergePair("Javi Pena", "javpen93@gmail.com", "javier@buildficial.com"),
    MergePair(
        "Nicholas LoScalzo",
        "nicholasvloscalzo@gmail.com",        # real (Active++), has slack_user_id
        "nicholas@builtwithprecisionai.com",  # auto-created
    ),
    MergePair(
        "Musa Elmaghrabi",
        "legendarywork1@gmail.com",  # real (Active++), has slack_user_id
        "musa@infiniteauraai.com",   # auto-created, appeared as "King Musa"
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes. Dry-run otherwise.")
    args = parser.parse_args(argv)

    db = get_client()

    for pair in MERGES:
        _merge_pair(db, pair, apply=args.apply)

    if not args.apply:
        print("\nDry run — no changes written. Re-run with --apply.")
    return 0


# ---------------------------------------------------------------------------
# Merge one pair
# ---------------------------------------------------------------------------


def _merge_pair(db, pair: MergePair, *, apply: bool) -> None:
    print()
    print("=" * 70)
    print(f"MERGE: {pair.label}")
    print(f"  real: {pair.real_email}")
    print(f"  auto: {pair.auto_email}")
    print("=" * 70)

    real_row = _find_active_client(db, pair.real_email)
    auto_row = _find_any_client(db, pair.auto_email)

    if real_row is None:
        print(f"  SKIP — real {pair.real_email} not found as active client.")
        return
    if auto_row is None:
        print(f"  SKIP — auto {pair.auto_email} not found.")
        return

    auto_metadata = auto_row.get("metadata") or {}
    already_merged = bool(auto_metadata.get("merged_into"))
    real_id = real_row["id"]
    auto_id = auto_row["id"]
    print(f"  real_id: {real_id}")
    print(f"  auto_id: {auto_id}")

    if not already_merged:
        _perform_merge(
            db, pair, real_row, auto_row, real_id, auto_id,
            auto_metadata=auto_metadata, apply=apply,
        )
    else:
        print(
            f"  (merge steps already applied — merged_into="
            f"{auto_metadata['merged_into']}, at {auto_metadata.get('merged_at')})"
        )

    # Always run: sync alternate_emails + alternate_names on the real
    # row. Handles both the fresh-merge case and the retroactive case
    # where a prior run of this script merged but didn't preserve alt
    # names (because the feature didn't exist yet).
    _sync_alternates(db, pair, real_row, auto_row, apply=apply)


def _perform_merge(
    db,
    pair: MergePair,
    real_row: dict[str, Any],
    auto_row: dict[str, Any],
    real_id: str,
    auto_id: str,
    *,
    auto_metadata: dict[str, Any],
    apply: bool,
) -> None:
    # Count what will change (for the dry-run report).
    participants = (
        db.table("call_participants")
        .select("id")
        .eq("client_id", auto_id)
        .execute()
    )
    participant_count = len(participants.data or [])

    auto_calls = (
        db.table("calls")
        .select("id,call_category,classification_confidence,is_retrievable_by_client_agents")
        .eq("primary_client_id", auto_id)
        .execute()
    )
    auto_call_ids = [c["id"] for c in (auto_calls.data or [])]

    matching_docs = _find_transcript_docs_for_calls(db, auto_call_ids)

    print(f"  call_participants to reattribute: {participant_count}")
    print(f"  calls to re-point + flip retrievability: {len(auto_call_ids)}")
    print(f"  transcript_chunk documents to reactivate: {len(matching_docs)}")

    if not apply:
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    if participant_count:
        db.table("call_participants").update({"client_id": real_id}).eq(
            "client_id", auto_id
        ).execute()

    if auto_call_ids:
        db.table("calls").update({
            "primary_client_id": real_id,
            "is_retrievable_by_client_agents": True,
        }).eq("primary_client_id", auto_id).execute()

    for doc in matching_docs:
        merged = dict(doc.get("metadata") or {})
        merged["client_id"] = real_id
        db.table("documents").update({
            "metadata": merged,
            "is_active": True,
        }).eq("id", doc["id"]).execute()

    new_auto_metadata = dict(auto_metadata)
    new_auto_metadata["merged_into"] = real_id
    new_auto_metadata["merged_at"] = now_iso
    db.table("clients").update({
        "archived_at": now_iso,
        "metadata": new_auto_metadata,
    }).eq("id", auto_id).execute()

    print(f"  merge body applied.")


def _sync_alternates(
    db,
    pair: MergePair,
    real_row: dict[str, Any],
    auto_row: dict[str, Any],
    *,
    apply: bool,
) -> None:
    """Ensure the real row's metadata carries:

      - `alternate_emails`: auto's email (dedup)
      - `alternate_names`: auto's full_name if it differs from real's

    Runs every invocation. Idempotent via dedup. Fills in retroactive
    gaps for pairs merged before alternate_names preservation was
    added.
    """
    # Re-fetch the real row to see its current metadata (we may have
    # updated it earlier in this same script run).
    fresh_real = _find_active_client(db, pair.real_email) or real_row
    real_metadata = dict(fresh_real.get("metadata") or {})

    emails = list(real_metadata.get("alternate_emails") or [])
    names = list(real_metadata.get("alternate_names") or [])

    real_full_name = fresh_real.get("full_name") or ""
    auto_full_name = (auto_row.get("full_name") or "").strip()

    changed = False
    if pair.auto_email not in emails:
        emails.append(pair.auto_email)
        changed = True
    if auto_full_name and auto_full_name != real_full_name and auto_full_name not in names:
        names.append(auto_full_name)
        changed = True

    if not changed:
        print(f"  alternates: already synced")
        return

    real_metadata["alternate_emails"] = emails
    real_metadata["alternate_names"] = names
    print(f"  alternates to write:")
    print(f"    alternate_emails = {emails}")
    print(f"    alternate_names  = {names}")

    if not apply:
        return

    db.table("clients").update({
        "metadata": real_metadata,
    }).eq("id", fresh_real["id"]).execute()
    print(f"  alternates updated on real row.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_active_client(db, email: str) -> dict[str, Any] | None:
    resp = (
        db.table("clients")
        .select("id,email,full_name,metadata")
        .eq("email", email)
        .is_("archived_at", "null")
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _find_any_client(db, email: str) -> dict[str, Any] | None:
    resp = (
        db.table("clients")
        .select("id,email,full_name,metadata,archived_at")
        .eq("email", email)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _find_transcript_docs_for_calls(db, call_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch all call_transcript_chunk docs, filter in Python on
    metadata.call_id ∈ call_ids. Not super efficient but we're dealing
    with hundreds of docs, not millions."""
    if not call_ids:
        return []
    call_id_set = set(call_ids)
    resp = (
        db.table("documents")
        .select("id,metadata,is_active")
        .eq("document_type", "call_transcript_chunk")
        .execute()
    )
    return [
        d for d in (resp.data or [])
        if (d.get("metadata") or {}).get("call_id") in call_id_set
    ]


if __name__ == "__main__":
    sys.exit(main())
