"""Archive 3 misclassified clients + reclassify their calls.

End-of-cleanup pass. The Fathom classifier auto-created 3 client rows
that turned out to be misclassifications:

  1. Andy Gonzalez (DB: 'Andrés González' / andy@thecyberself.com)
     — hiring interview, not a real client.
     Calls reclassify to category='external' (auto-clears
     primary_client_id, auto-sets is_retrievable_by_client_agents=false).

  2. Aman (no last name) — internal team chat with Scott from before
     Aman was on team_members.
     Calls reclassify to category='internal' (same auto-clear /
     auto-derive behavior).

  3. Branden Bledsoe (Drake's spec said "Brendan" — DB has "Branden")
     — Isabel Bledsoe's representative joining her offboarding call.
     Calls keep category='client'; primary_client_id repointed to
     Isabel Bledsoe. Drake explicitly opted to NOT add Branden's email
     to Isabel's metadata.alternate_emails.

After all calls are reclassified, soft-archive each client row:

    UPDATE clients SET archived_at=now(), metadata=metadata ||
      jsonb_build_object(
        'archived_via', 'm5_cleanup_misclassification_archive',
        'archived_at_iso', '<iso>',
        'misclassification_type', '<external_hiring|internal_team|representative_of_other_client>',
        'rerouted_to_client_id', '<isabel uuid>'  -- Branden only
      )

Two-phase apply via flags so a hard stop can sit between them:

  --apply-calls       Reclassify all calls. Idempotent.
  --apply-archives    Soft-archive the 3 client rows. Idempotent
                      (skips clients with archived_at already set).

Default (no flags): dry-run, no writes, full report only.

Attribution:
  - Calls: update_call_classification RPC with p_changed_by =
    Gregory Bot UUID. The history table has no `note` column so the
    UUID is the only attribution surface — Gregory Bot is exclusive
    to system writes, so this still distinguishes "the cleanup script
    did it" from "a human edited via the dashboard".
  - Client archives: metadata.archived_via='m5_cleanup_misclassification_archive'.
    SQL-joinable for audit.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.db import get_client  # noqa: E402

GREGORY_BOT_UUID = "cfcea32a-062d-4269-ae0f-959adac8f597"
ARCHIVED_VIA = "m5_cleanup_misclassification_archive"


# Each entry: (display_label, name_candidates, new_call_category, misclass_type)
# `new_call_category` of None means "keep as 'client', repoint primary_client_id"
# (Branden's case). The reroute target is set by name lookup at runtime.
@dataclass
class TargetSpec:
    display_label: str
    name_candidates: list[str]  # ilike patterns to try until exactly 1 match
    new_call_category: str | None  # None → keep category, repoint primary
    misclass_type: str
    reroute_to_full_name: str | None = None  # Branden only — repoint to Isabel


TARGETS: list[TargetSpec] = [
    TargetSpec(
        display_label="Andy Gonzalez (hiring interview)",
        name_candidates=["Andy Gonzalez", "Andrés González", "Andres Gonzalez"],
        new_call_category="external",
        misclass_type="external_hiring",
    ),
    TargetSpec(
        display_label="Aman (internal teammate)",
        name_candidates=["Aman"],  # exact full_name match enforced post-query
        new_call_category="internal",
        misclass_type="internal_team",
    ),
    TargetSpec(
        display_label="Branden Bledsoe (representative for Isabel Bledsoe)",
        name_candidates=["Brendan Bledsoe", "Branden Bledsoe"],
        new_call_category=None,  # keep client; repoint primary_client_id
        misclass_type="representative_of_other_client",
        reroute_to_full_name="Isabel Bledsoe",
    ),
]


@dataclass
class ResolvedTarget:
    spec: TargetSpec
    client: dict  # the resolved Gregory client row
    calls: list[dict]  # all calls where primary_client_id = client.id
    reroute_client: dict | None  # Isabel's row, for Branden
    document_count: int  # documents linked to any of these calls
    skip_reason: str | None = None  # set if resolution failed
    anomalies: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def _resolve_target_client(db, spec: TargetSpec) -> tuple[dict | None, list[str]]:
    """Try each name candidate; return (resolved_row, anomaly_strings).

    Returns the FIRST candidate that yields exactly 1 non-archived match.
    For 'Aman' (single-word name), enforces exact full_name match (case-
    insensitive) post-ilike to avoid Amanda / Amanpreet / etc.
    """
    anomalies: list[str] = []
    for name in spec.name_candidates:
        resp = (
            db.table("clients")
            .select("id, full_name, email, status, metadata, archived_at")
            .ilike("full_name", f"%{name}%")
            .is_("archived_at", "null")
            .execute()
        )
        rows = resp.data or []

        # Aman: enforce exact equality (case-insensitive) since 'Aman' is
        # a substring of many longer first names.
        if name.lower() == "aman":
            rows = [
                r for r in rows if (r.get("full_name") or "").strip().lower() == "aman"
            ]

        if len(rows) == 1:
            return rows[0], anomalies
        if len(rows) > 1:
            anomalies.append(
                f"Name candidate {name!r} matches >1 active row: "
                + ", ".join(f"{r['full_name']} ({r['id']})" for r in rows)
            )
        # 0 rows → try next candidate

    return None, anomalies


def _fetch_calls_for_client(db, client_id: str) -> list[dict]:
    resp = (
        db.table("calls")
        .select(
            "id, external_id, source, title, started_at, "
            "call_category, call_type, primary_client_id, "
            "is_retrievable_by_client_agents"
        )
        .eq("primary_client_id", client_id)
        .order("started_at", desc=False)
        .execute()
    )
    return resp.data or []


def _count_documents_for_calls(db, call_ids: list[str]) -> int:
    """Count documents whose metadata.call_id matches any of the given
    call_ids. Used to surface knowledge-base footprint at the gate."""
    if not call_ids:
        return 0
    total = 0
    for cid in call_ids:
        resp = (
            db.table("documents")
            .select("id", count="exact", head=True)
            .filter("metadata->>call_id", "eq", cid)
            .execute()
        )
        total += int(resp.count or 0)
    return total


def resolve_all(db) -> list[ResolvedTarget]:
    out: list[ResolvedTarget] = []
    # Pre-resolve Isabel for Branden's reroute.
    isabel_resp = (
        db.table("clients")
        .select("id, full_name, email")
        .ilike("full_name", "Isabel Bledsoe")
        .is_("archived_at", "null")
        .execute()
    )
    isabel_rows = isabel_resp.data or []
    isabel = isabel_rows[0] if len(isabel_rows) == 1 else None

    for spec in TARGETS:
        client, anomalies = _resolve_target_client(db, spec)
        if client is None:
            out.append(
                ResolvedTarget(
                    spec=spec,
                    client={},
                    calls=[],
                    reroute_client=None,
                    document_count=0,
                    skip_reason="no name match found",
                    anomalies=anomalies,
                )
            )
            continue

        calls = _fetch_calls_for_client(db, client["id"])
        doc_count = _count_documents_for_calls(db, [c["id"] for c in calls])

        reroute = None
        if spec.reroute_to_full_name is not None:
            if isabel is None:
                anomalies.append(
                    f"reroute target Isabel Bledsoe could not be resolved "
                    f"({len(isabel_rows)} active matches)"
                )
            else:
                reroute = isabel

        out.append(
            ResolvedTarget(
                spec=spec,
                client=client,
                calls=calls,
                reroute_client=reroute,
                document_count=doc_count,
                anomalies=anomalies,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Apply — calls
# ---------------------------------------------------------------------------


def apply_calls(db, targets: list[ResolvedTarget]) -> dict[str, int]:
    counts: dict[str, int] = {
        "calls_reclassified_external": 0,
        "calls_reclassified_internal": 0,
        "calls_repointed_primary_client": 0,
        "calls_already_correct": 0,
        "call_apply_errors": 0,
        "documents_deactivated": 0,
        "documents_already_inactive": 0,
        "documents_kept_active": 0,
        "document_apply_errors": 0,
    }
    for tgt in targets:
        if tgt.skip_reason or not tgt.calls:
            continue

        # Belt-and-suspenders document suppression for category-change
        # targets (Andy + Aman). The call-level is_retrievable flag is the
        # primary gate; flipping is_active=false on the linked documents
        # is a defensive over-suppress so the docs are excluded by every
        # downstream filter (kb_query reads is_active before joining
        # against calls).
        #
        # Branden's case (new_call_category is None) keeps documents
        # active — the call IS legitimately Isabel's offboarding-call
        # summary post-repoint; retrievability for her account is the
        # right semantics.
        deactivate_docs = tgt.spec.new_call_category is not None

        for call in tgt.calls:
            # Build the changes payload for update_call_classification RPC.
            changes: dict[str, Any] = {}
            if tgt.spec.new_call_category is not None:
                # Andy / Aman: change category. RPC auto-clears
                # primary_client_id and sets is_retrievable=false.
                if call["call_category"] == tgt.spec.new_call_category:
                    counts["calls_already_correct"] += 1
                else:
                    changes["call_category"] = tgt.spec.new_call_category
            else:
                # Branden: repoint primary_client_id only.
                if (
                    tgt.reroute_client is not None
                    and call["primary_client_id"] == tgt.reroute_client["id"]
                ):
                    counts["calls_already_correct"] += 1
                elif tgt.reroute_client is None:
                    counts["call_apply_errors"] += 1
                    continue
                else:
                    changes["primary_client_id"] = tgt.reroute_client["id"]

            if changes:
                try:
                    db.rpc(
                        "update_call_classification",
                        {
                            "p_call_id": call["id"],
                            "p_changes": changes,
                            "p_changed_by": GREGORY_BOT_UUID,
                        },
                    ).execute()
                    if tgt.spec.new_call_category == "external":
                        counts["calls_reclassified_external"] += 1
                    elif tgt.spec.new_call_category == "internal":
                        counts["calls_reclassified_internal"] += 1
                    else:
                        counts["calls_repointed_primary_client"] += 1
                except Exception as exc:
                    print(f"  ERR call {call['id']}: {str(exc).splitlines()[0]}")
                    counts["call_apply_errors"] += 1
                    continue

            # Document suppression: per Drake's adjustment, flip is_active
            # on docs linked to category-changed calls (Andy + Aman). Skip
            # for Branden (his call's docs are legitimately Isabel's now).
            try:
                docs_resp = (
                    db.table("documents")
                    .select("id, is_active")
                    .filter("metadata->>call_id", "eq", call["id"])
                    .execute()
                )
                docs = docs_resp.data or []
                for doc in docs:
                    if not deactivate_docs:
                        counts["documents_kept_active"] += 1
                        continue
                    if not doc.get("is_active"):
                        counts["documents_already_inactive"] += 1
                        continue
                    db.table("documents").update({"is_active": False}).eq(
                        "id", doc["id"]
                    ).execute()
                    counts["documents_deactivated"] += 1
            except Exception as exc:
                print(
                    f"  ERR doc suppression for call {call['id']}: "
                    f"{str(exc).splitlines()[0]}"
                )
                counts["document_apply_errors"] += 1

    return counts


# ---------------------------------------------------------------------------
# Apply — client archives
# ---------------------------------------------------------------------------


def apply_archives(db, targets: list[ResolvedTarget]) -> dict[str, int]:
    counts: dict[str, int] = {
        "clients_archived": 0,
        "clients_already_archived": 0,
        "archive_errors": 0,
    }
    now_iso = datetime.now(timezone.utc).isoformat()

    for tgt in targets:
        if tgt.skip_reason or not tgt.client:
            continue

        client_id = tgt.client["id"]

        # Re-fetch fresh to check archived_at (idempotency on re-run).
        fresh = (
            db.table("clients")
            .select("id, archived_at, metadata")
            .eq("id", client_id)
            .single()
            .execute()
        )
        if fresh.data and fresh.data.get("archived_at"):
            counts["clients_already_archived"] += 1
            continue

        existing_metadata = dict(fresh.data.get("metadata") or {})
        archive_metadata = {
            "archived_via": ARCHIVED_VIA,
            "archived_at_iso": now_iso,
            "misclassification_type": tgt.spec.misclass_type,
        }
        if tgt.reroute_client is not None:
            archive_metadata["rerouted_to_client_id"] = tgt.reroute_client["id"]

        new_metadata = {**existing_metadata, **archive_metadata}

        try:
            db.table("clients").update(
                {"archived_at": now_iso, "metadata": new_metadata}
            ).eq("id", client_id).execute()
            counts["clients_archived"] += 1
        except Exception as exc:
            print(f"  ERR archive {tgt.spec.display_label}: {str(exc).splitlines()[0]}")
            counts["archive_errors"] += 1

    return counts


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_dry_run_report(targets: list[ResolvedTarget]) -> None:
    print("=" * 72)
    print("DRY-RUN REPORT — archive_misclassified_clients")
    print("=" * 72)
    for tgt in targets:
        print()
        print(f"— {tgt.spec.display_label}")
        if tgt.skip_reason:
            print(f"  SKIP: {tgt.skip_reason}")
            for a in tgt.anomalies:
                print(f"    anomaly: {a}")
            continue

        c = tgt.client
        print(f"  client_id:    {c['id']}")
        print(f"  full_name:    {c.get('full_name')!r}")
        print(f"  email:        {c.get('email')!r}")
        print(f"  status:       {c.get('status')!r}")
        if tgt.reroute_client is not None:
            r = tgt.reroute_client
            print(f"  reroute to:   {r['full_name']!r} ({r['id']})")
        elif tgt.spec.reroute_to_full_name is not None:
            print(f"  reroute to:   {tgt.spec.reroute_to_full_name!r} — UNRESOLVED")

        print(f"  calls found:  {len(tgt.calls)}")
        for call in tgt.calls:
            curr = (
                f"category={call['call_category']!r}, "
                f"primary={call['primary_client_id']}, "
                f"retrievable={call['is_retrievable_by_client_agents']}"
            )
            if tgt.spec.new_call_category is not None:
                proposed = (
                    f"category={tgt.spec.new_call_category!r}, "
                    f"primary=NULL (auto-clear), retrievable=False (auto-derive)"
                )
            elif tgt.reroute_client is not None:
                proposed = (
                    f"category={call['call_category']!r} (unchanged), "
                    f"primary={tgt.reroute_client['id']} ({tgt.reroute_client['full_name']!r}), "
                    "retrievable=True (auto-derive)"
                )
            else:
                proposed = "(unresolved reroute target)"
            print(
                f"    - {call['id']} ({call['started_at'][:10]} {call.get('title') or '(no title)'})"
            )
            print(f"        before: {curr}")
            print(f"        after:  {proposed}")

        print(f"  documents linked to these calls: {tgt.document_count}")
        print(
            f"  archive metadata: archived_via={ARCHIVED_VIA!r}, "
            f"misclassification_type={tgt.spec.misclass_type!r}"
            + (
                f", rerouted_to_client_id={tgt.reroute_client['id']!r}"
                if tgt.reroute_client is not None
                else ""
            )
        )
        for a in tgt.anomalies:
            print(f"  anomaly: {a}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply-calls",
        action="store_true",
        help="Apply call reclassifications. Idempotent.",
    )
    parser.add_argument(
        "--apply-archives",
        action="store_true",
        help="Apply client archives. Idempotent. Should run AFTER --apply-calls.",
    )
    args = parser.parse_args(argv)

    db = get_client()
    targets = resolve_all(db)

    print("=" * 72)
    flags = []
    if args.apply_calls:
        flags.append("apply-calls")
    if args.apply_archives:
        flags.append("apply-archives")
    print(f"Mode: {'+'.join(flags) if flags else 'DRY-RUN'}")
    print("=" * 72)

    render_dry_run_report(targets)

    if args.apply_calls:
        print()
        print("=" * 72)
        print("APPLYING call reclassifications...")
        print("=" * 72)
        counts = apply_calls(db, targets)
        print()
        print("Call apply summary:")
        for k, v in sorted(counts.items()):
            print(f"  {k:<40}  {v}")

    if args.apply_archives:
        print()
        print("=" * 72)
        print("APPLYING client archives...")
        print("=" * 72)
        counts = apply_archives(db, targets)
        print()
        print("Archive apply summary:")
        for k, v in sorted(counts.items()):
            print(f"  {k:<40}  {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
