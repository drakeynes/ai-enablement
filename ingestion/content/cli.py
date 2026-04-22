"""Command-line entrypoint for the filesystem content ingestion.

Usage:

    python -m ingestion.content.cli [--input <path>] [--limit N] [--apply]

Default `--input` is `data/course_content/`. Discovers every `.html`
under it (recursively), derives tags from the relative path,
parses + hashes + chunks each, and either prints a dry-run report
(default) or upserts to `documents` / `document_chunks` on `--apply`.

Re-runs are cheap: unchanged files (same sha256) are silent no-ops.
Content-changed files get their document updated and chunks
replaced.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.content import pipeline  # noqa: E402
from ingestion.content.pipeline import ContentIngestOutcome  # noqa: E402
from shared.db import get_client  # noqa: E402

_DEFAULT_INPUT = _REPO_ROOT / "data" / "course_content"
_LOG_DIR = _REPO_ROOT / "data" / "content_ingest"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    content_root = Path(args.input).resolve()
    if not content_root.exists() or not content_root.is_dir():
        sys.exit(f"ERROR: --input not a directory: {content_root}")

    files = sorted(p for p in content_root.rglob("*.html"))
    if args.limit:
        files = files[: args.limit]

    _print_header(content_root, len(files), args)

    db = get_client()
    embed_fn = None
    if args.apply:
        from shared.kb_query import embed as embed_fn  # noqa: F401

    outcomes: list[ContentIngestOutcome] = []
    parse_failures: list[tuple[Path, str]] = []

    for path in files:
        try:
            outcome = pipeline.ingest_file(
                path,
                content_root=content_root,
                db=db,
                embed_fn=embed_fn,
                dry_run=not args.apply,
            )
        except Exception as exc:
            parse_failures.append((path, str(exc)))
            continue
        outcomes.append(outcome)

    _print_summary(content_root, outcomes, parse_failures, apply=args.apply)

    if not args.apply:
        print("Dry run only — no changes written. Re-run with --apply to commit.")
        return 0

    log_path = _write_log(outcomes, parse_failures)
    print(f"\nLog: {log_path}")
    return 0 if not parse_failures else 1


def _parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default=str(_DEFAULT_INPUT), help="Content root directory.")
    p.add_argument("--limit", type=int, default=None, help="Process only the first N files.")
    p.add_argument("--apply", action="store_true", help="Write to Supabase. Dry-run otherwise.")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_header(content_root: Path, file_count: int, args) -> None:
    print("=" * 72)
    print("CONTENT INGESTION")
    print("=" * 72)
    print(f"Root:   {content_root}")
    print(f"Files:  {file_count}")
    if args.limit:
        print(f"Limit:  {args.limit}")
    if args.apply:
        print(f"Mode:   APPLY")
    else:
        print(f"Mode:   dry-run")
    print()


def _print_summary(
    content_root: Path,
    outcomes: list[ContentIngestOutcome],
    parse_failures: list[tuple[Path, str]],
    *,
    apply: bool,
) -> None:
    print("-" * 72)
    print("MODULE × SECTION × FILE COUNTS")
    print("-" * 72)
    # Build nested module → section → [outcomes] tree.
    tree: dict[str, dict[str, list[ContentIngestOutcome]]] = defaultdict(lambda: defaultdict(list))
    module_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"lessons": 0, "chunks": 0}
    )

    for outcome in outcomes:
        module_tag = next((t for t in outcome.tags if t.startswith("module_")), "module_?")
        section_tag = next(
            (t for t in outcome.tags if t.startswith("section_")), "—"
        )
        tree[module_tag][section_tag].append(outcome)
        module_totals[module_tag]["lessons"] += 1
        module_totals[module_tag]["chunks"] += outcome.chunk_count

    for module_tag in sorted(tree.keys()):
        totals = module_totals[module_tag]
        print(
            f"  {module_tag:<40} lessons={totals['lessons']:>3}  "
            f"chunks={totals['chunks']:>4}"
        )
        for section_tag in sorted(tree[module_tag].keys()):
            section_outcomes = tree[module_tag][section_tag]
            section_chunks = sum(o.chunk_count for o in section_outcomes)
            label = section_tag if section_tag != "—" else "(top level)"
            print(
                f"    └ {label:<38} lessons={len(section_outcomes):>3}  "
                f"chunks={section_chunks:>4}"
            )
    print()

    total_chunks = sum(o.chunk_count for o in outcomes)
    estimated_cost = pipeline.estimate_embedding_cost_usd(total_chunks)
    print("-" * 72)
    print("TOTALS")
    print("-" * 72)
    print(f"  files processed:           {len(outcomes)}")
    print(f"  total chunks (if fresh):   {total_chunks}")
    print(f"  estimated embedding cost:  ${estimated_cost:.4f}")
    if parse_failures:
        print(f"  parse failures:            {len(parse_failures)}")
    print()

    print("-" * 72)
    print("PARSE FAILURES")
    print("-" * 72)
    if not parse_failures:
        print("(none)")
    for path, error in parse_failures[:20]:
        rel = path.relative_to(content_root)
        print(f"  {rel}: {error}")
    if len(parse_failures) > 20:
        print(f"  ... and {len(parse_failures) - 20} more")
    print()

    print("-" * 72)
    print("SAMPLES — 3 random files")
    print("-" * 72)
    import random
    rng = random.Random(42)
    sample = rng.sample(outcomes, k=min(3, len(outcomes)))
    for o in sample:
        print(f"  {o.external_id}")
        print(f"    title:       {o.title}")
        print(f"    tags:        {o.tags}")
        print(f"    word_count:  {o.word_count}")
        print(f"    chunks:      {o.chunk_count}")
        print()

    if apply:
        inserted = sum(1 for o in outcomes if o.action == "inserted")
        updated = sum(1 for o in outcomes if o.action == "updated_content_changed")
        skipped = sum(1 for o in outcomes if o.action == "skipped_unchanged")
        chunks_written = sum(o.chunks_written for o in outcomes)
        chunks_reused = sum(o.chunks_reused for o in outcomes)
        actual_cost = pipeline.estimate_embedding_cost_usd(chunks_written)
        validation_failures = sum(len(o.validation_failures) for o in outcomes)

        print("-" * 72)
        print("APPLY SUMMARY")
        print("-" * 72)
        print(f"  documents inserted:              {inserted}")
        print(f"  documents updated (content changed): {updated}")
        print(f"  documents skipped (unchanged):   {skipped}")
        print(f"  chunks written (embedded):       {chunks_written}")
        print(f"  chunks reused (no re-embed):     {chunks_reused}")
        print(f"  embedding API calls:             {chunks_written}")
        print(f"  estimated embedding cost:        ${actual_cost:.4f}")
        print(f"  validation failures:             {validation_failures}   (should be 0)")


def _write_log(
    outcomes: list[ContentIngestOutcome],
    parse_failures: list[tuple[Path, str]],
) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"run_{ts}.log"
    body = {
        "timestamp_utc": ts,
        "total_files": len(outcomes),
        "parse_failures": [{"path": str(p), "error": e} for p, e in parse_failures],
        "outcomes": [_outcome_to_dict(o) for o in outcomes],
    }
    path.write_text(json.dumps(body, indent=2, default=str))
    return path


def _outcome_to_dict(o: ContentIngestOutcome) -> dict:
    # asdict works but Paths aren't JSON-safe — coerce manually.
    return {
        "source_path": str(o.source_path),
        "external_id": o.external_id,
        "title": o.title,
        "tags": o.tags,
        "word_count": o.word_count,
        "chunk_count": o.chunk_count,
        "content_hash": o.content_hash,
        "document_id": o.document_id,
        "chunks_written": o.chunks_written,
        "chunks_reused": o.chunks_reused,
        "action": o.action,
        "validation_failures": o.validation_failures,
        "errors": o.errors,
    }


if __name__ == "__main__":
    sys.exit(main())
