"""Command-line entrypoint for the Fathom backlog ingest pipeline.

Usage:
    python -m ingestion.fathom.cli --input <path> [--apply]
                                   [--limit N] [--since YYYY-MM-DD]
                                   [--only-category client,internal,...]

`--input` accepts a `.zip` archive or a directory of `.txt` files.
Without `--apply`, runs in dry-run mode: parses + classifies every
file and prints a category distribution report + per-category
samples. With `--apply`, writes to Supabase and drops a log under
`data/fathom_ingest/run_<ts>.log`.

`--limit` short-circuits after N files post-parse (handy for
iteration).

`--since YYYY-MM-DD` filters to calls started on or after that date
(UTC). Useful when a re-run should touch only recent calls.

`--only-category` is applied AFTER classification. In dry-run it
filters the sample output; in `--apply` it also filters which
records reach the DB-write step.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.fathom import parser as fathom_parser  # noqa: E402
from ingestion.fathom import pipeline  # noqa: E402
from ingestion.fathom.classifier import (  # noqa: E402
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
)
from shared.db import get_client  # noqa: E402

_LOG_DIR = _REPO_ROOT / "data" / "fathom_ingest"
_ALL_CATEGORIES = ("client", "internal", "external", "unclassified", "excluded")


# ---------------------------------------------------------------------------
# Result accumulators
# ---------------------------------------------------------------------------


@dataclass
class ParsedRecord:
    path: Path
    record: "fathom_parser.FathomCallRecord"
    file_size_bytes: int


@dataclass
class ParseFailure:
    path: Path
    error: str


@dataclass
class RunReport:
    total_files: int = 0
    parsed: list[ParsedRecord] = field(default_factory=list)
    parse_failures: list[ParseFailure] = field(default_factory=list)
    outcomes: list["pipeline.IngestOutcome"] = field(default_factory=list)
    filtered_out_by_since: int = 0
    filtered_out_by_limit: int = 0
    filtered_out_by_only_category: int = 0


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


def _iter_txt_files(input_path: Path) -> Iterable[Path]:
    """Yield .txt paths from a directory or an extracted zip.

    Zips are extracted into a temporary directory that the caller is
    responsible for cleaning up (we just yield the paths; the caller's
    context manager in main() handles teardown).
    """
    if input_path.is_dir():
        yield from sorted(p for p in input_path.rglob("*.txt"))
        return
    if input_path.suffix.lower() == ".zip":
        extract_dir = Path(tempfile.mkdtemp(prefix="fathom_ingest_"))
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(extract_dir)
        yield from sorted(p for p in extract_dir.rglob("*.txt"))
        # NOTE: caller uses _cleanup_extracted to remove extract_dir
        _ACTIVE_EXTRACT_DIRS.append(extract_dir)
        return
    raise SystemExit(f"ERROR: --input must be a .zip or a directory, got {input_path}")


_ACTIVE_EXTRACT_DIRS: list[Path] = []


def _cleanup_extracted() -> None:
    for d in _ACTIVE_EXTRACT_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    _ACTIVE_EXTRACT_DIRS.clear()


# ---------------------------------------------------------------------------
# Parsing + classification pass
# ---------------------------------------------------------------------------


def _parse_all(paths: Iterable[Path]) -> tuple[list[ParsedRecord], list[ParseFailure]]:
    parsed: list[ParsedRecord] = []
    failures: list[ParseFailure] = []
    for path in paths:
        try:
            record = fathom_parser.parse_file(path)
        except Exception as exc:
            failures.append(ParseFailure(path=path, error=str(exc)))
            continue
        parsed.append(
            ParsedRecord(path=path, record=record, file_size_bytes=path.stat().st_size)
        )
    return parsed, failures


def _apply_since_filter(
    records: list[ParsedRecord], since: date | None
) -> tuple[list[ParsedRecord], int]:
    if since is None:
        return records, 0
    cutoff = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    kept = [r for r in records if r.record.started_at >= cutoff]
    return kept, len(records) - len(kept)


def _apply_limit(
    records: list[ParsedRecord], limit: int | None
) -> tuple[list[ParsedRecord], int]:
    if limit is None or limit <= 0:
        return records, 0
    kept = records[:limit]
    return kept, max(0, len(records) - limit)


# ---------------------------------------------------------------------------
# Dry-run / apply reporting
# ---------------------------------------------------------------------------


def _confidence_tier(conf: float) -> str:
    if conf >= CONFIDENCE_HIGH:
        return "high"
    if conf >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"


def _render_category_matrix(outcomes: list[pipeline.IngestOutcome]) -> list[str]:
    matrix: dict[tuple[str, str], int] = defaultdict(int)
    for o in outcomes:
        matrix[(o.category, _confidence_tier(o.confidence))] += 1
    tiers = ("high", "medium", "low")
    header = "  " + "category".ljust(14) + "  " + "  ".join(t.rjust(6) for t in tiers) + "   total"
    lines = [header, "  " + "-" * (len(header) - 2)]
    for cat in _ALL_CATEGORIES:
        row = [str(matrix[(cat, t)]).rjust(6) for t in tiers]
        total = sum(matrix[(cat, t)] for t in tiers)
        lines.append(f"  {cat.ljust(14)}  " + "  ".join(row) + f"   {str(total).rjust(5)}")
    grand = len(outcomes)
    lines.append(f"  {'TOTAL'.ljust(14)}  " + " " * (len("  ".join([''.rjust(6)] * 3))) + f"   {str(grand).rjust(5)}")
    return lines


def _render_samples(
    parsed: list[ParsedRecord],
    outcomes: list[pipeline.IngestOutcome],
    client_id_to_name: dict[str, str],
    per_category: int = 5,
) -> list[str]:
    lines: list[str] = []
    by_cat: dict[str, list[tuple[ParsedRecord, pipeline.IngestOutcome]]] = defaultdict(list)
    for pr, outcome in zip(parsed, outcomes):
        by_cat[outcome.category].append((pr, outcome))

    rng = random.Random(42)
    for category in _ALL_CATEGORIES:
        bucket = by_cat.get(category) or []
        if not bucket:
            continue
        sample = rng.sample(bucket, k=min(per_category, len(bucket)))
        lines.append(f"  [{category}] — {len(bucket)} calls, showing {len(sample)}")
        for pr, outcome in sample:
            client_name = (
                client_id_to_name.get(outcome.primary_client_id, "?")
                if outcome.primary_client_id else "—"
            )
            first_chunk_preview = _first_chunk_preview(pr.record, outcome)
            lines.append(
                f"    {pr.path.name}\n"
                f"      title:       {pr.record.title[:80]}\n"
                f"      confidence:  {_confidence_tier(outcome.confidence)} ({outcome.confidence:.2f}) via {outcome.method}\n"
                f"      client:      {outcome.primary_client_id or '—'} ({client_name})\n"
                f"      participants:{len(pr.record.participants)}    duration: {pr.record.duration_seconds}s\n"
                f"      preview:     {first_chunk_preview}"
            )
        lines.append("")
    return lines


def _first_chunk_preview(
    record: "fathom_parser.FathomCallRecord", outcome: pipeline.IngestOutcome
) -> str:
    if outcome.category != "client":
        return "(non-client — no chunks produced)"
    # Use the first substantive utterance(s) to give a flavor preview
    if not record.utterances:
        return "(no utterances)"
    text = f"[{record.utterances[0].timestamp}] {record.utterances[0].speaker}: {record.utterances[0].text}"
    if len(text) > 140:
        text = text[:137] + "..."
    return text


def _render_auto_create_predictions(
    outcomes: list[pipeline.IngestOutcome],
) -> list[str]:
    pending: list[str] = []
    for o in outcomes:
        if o.auto_created_client_email and not o.auto_created_client_id:
            pending.append(o.auto_created_client_email)
    if not pending:
        return ["(none)"]
    counts: Counter[str] = Counter(pending)
    return [f"  {count:>3} × {email}" for email, count in counts.most_common()]


def _render_parse_failures(failures: list[ParseFailure]) -> list[str]:
    if not failures:
        return ["(none)"]
    return [f"  {pf.path.name}: {pf.error}" for pf in failures]


# ---------------------------------------------------------------------------
# Apply-log counters
# ---------------------------------------------------------------------------


@dataclass
class ApplyCounts:
    calls_inserted: int = 0
    calls_updated: int = 0
    participants_upserted: int = 0
    documents_created: int = 0
    documents_archived: int = 0
    chunks_inserted: int = 0
    chunks_reused: int = 0
    auto_created_clients: int = 0
    validation_failures: int = 0


def _aggregate_apply_counts(outcomes: list[pipeline.IngestOutcome]) -> ApplyCounts:
    c = ApplyCounts()
    for o in outcomes:
        if o.action == "inserted":
            c.calls_inserted += 1
        elif o.action == "updated":
            c.calls_updated += 1
        c.participants_upserted += o.participants_linked_to_clients + o.participants_linked_to_team
        if o.document_id and o.chunks_written > 0:
            c.documents_created += 1
        c.chunks_inserted += o.chunks_written
        c.chunks_reused += o.chunks_reused
        if o.auto_created_client_id:
            c.auto_created_clients += 1
        c.validation_failures += len(o.validation_failures)
    return c


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        sys.exit(f"ERROR: --input path does not exist: {input_path}")

    try:
        return _run(args, input_path)
    finally:
        _cleanup_extracted()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Zip file or directory of .txt transcripts.")
    p.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    p.add_argument("--limit", type=int, default=None, help="Process only the first N files post-parse.")
    p.add_argument("--since", type=lambda s: date.fromisoformat(s), default=None,
                   help="Only include calls with started_at >= this UTC date (YYYY-MM-DD).")
    p.add_argument(
        "--only-category",
        type=lambda s: frozenset(c.strip() for c in s.split(",") if c.strip()),
        default=None,
        help="Comma-separated. In dry-run: limits sample output. In --apply: skips DB writes for others.",
    )
    return p.parse_args(argv)


def _run(args: argparse.Namespace, input_path: Path) -> int:
    paths = list(_iter_txt_files(input_path))

    print("=" * 72)
    print("FATHOM BACKLOG INGESTION")
    print("=" * 72)
    print(f"Input:   {input_path}")
    print(f"Files:   {len(paths)}")
    if args.limit:
        print(f"Limit:   {args.limit}")
    if args.since:
        print(f"Since:   {args.since.isoformat()}")
    if args.only_category:
        print(f"Only:    {sorted(args.only_category)}")
    print()

    report = RunReport(total_files=len(paths))
    report.parsed, report.parse_failures = _parse_all(paths)
    report.parsed, report.filtered_out_by_since = _apply_since_filter(report.parsed, args.since)
    report.parsed, report.filtered_out_by_limit = _apply_limit(report.parsed, args.limit)

    db = get_client()
    client_resolver, team_resolver, client_id_to_name = pipeline.load_resolvers(db)

    # Classification pass (no writes yet) — always runs full set so the
    # dry-run matrix reflects everything. --only-category filters later.
    embed_fn = None
    if args.apply:
        from shared.kb_query import embed as embed_fn  # noqa: F401 — import cost only when needed

    for parsed_record in report.parsed:
        outcome = pipeline.ingest_call(
            parsed_record.record,
            db,
            client_resolver=client_resolver,
            team_resolver=team_resolver,
            file_size_bytes=parsed_record.file_size_bytes,
            dry_run=True,   # always dry-run during classification pass
        )
        report.outcomes.append(outcome)

    # Enrich outcomes with client names for display
    enriched = [
        _enrich_primary_client_name(o, client_id_to_name) for o in report.outcomes
    ]
    report.outcomes = enriched

    _print_dry_run_report(report, client_id_to_name, args.only_category)

    if not args.apply:
        print("Dry run only — no changes written. Re-run with --apply to commit.")
        return 0

    # Apply pass — re-invoke ingest_call with dry_run=False, only for
    # records passing --only-category if set.
    print("-" * 72)
    print("APPLYING...")
    print("-" * 72)
    applied_outcomes: list[pipeline.IngestOutcome] = []
    for parsed_record, dry_outcome in zip(report.parsed, report.outcomes):
        if args.only_category and dry_outcome.category not in args.only_category:
            report.filtered_out_by_only_category += 1
            continue
        applied = pipeline.ingest_call(
            parsed_record.record,
            db,
            client_resolver=client_resolver,
            team_resolver=team_resolver,
            embed_fn=embed_fn,
            file_size_bytes=parsed_record.file_size_bytes,
            dry_run=False,
        )
        applied_outcomes.append(_enrich_primary_client_name(applied, client_id_to_name))

    _print_apply_log(applied_outcomes)
    log_path = _write_apply_log(report, applied_outcomes, client_id_to_name)
    print(f"\nLog: {log_path}")
    return 0


def _enrich_primary_client_name(
    outcome: pipeline.IngestOutcome, id_to_name: dict[str, str]
) -> pipeline.IngestOutcome:
    from dataclasses import replace
    if outcome.primary_client_id is None:
        return outcome
    return replace(outcome, primary_client_name=id_to_name.get(outcome.primary_client_id))


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------


def _print_dry_run_report(
    report: RunReport,
    client_id_to_name: dict[str, str],
    only_category: frozenset[str] | None,
) -> None:
    print(f"Total files seen:        {report.total_files}")
    print(f"Parsed successfully:     {len(report.parsed) + report.filtered_out_by_since + report.filtered_out_by_limit}")
    print(f"Parse failures:          {len(report.parse_failures)}")
    if report.filtered_out_by_since:
        print(f"Filtered by --since:     {report.filtered_out_by_since}")
    if report.filtered_out_by_limit:
        print(f"Filtered by --limit:     {report.filtered_out_by_limit}")
    print(f"Classified (in sample):  {len(report.outcomes)}")
    print()

    print("-" * 72)
    print("CLASSIFICATION DISTRIBUTION — category × confidence")
    print("-" * 72)
    for line in _render_category_matrix(report.outcomes):
        print(line)
    print()

    print("-" * 72)
    print("AUTO-CREATE PREDICTIONS — clients the pipeline would insert on --apply")
    print("-" * 72)
    for line in _render_auto_create_predictions(report.outcomes):
        print(line)
    print()

    print("-" * 72)
    print("PARSE FAILURES")
    print("-" * 72)
    for line in _render_parse_failures(report.parse_failures):
        print(line)
    print()

    sample_outcomes = report.outcomes
    sample_parsed = report.parsed
    if only_category:
        pairs = [
            (pr, o) for pr, o in zip(sample_parsed, sample_outcomes)
            if o.category in only_category
        ]
        sample_parsed = [p for p, _ in pairs]
        sample_outcomes = [o for _, o in pairs]

    print("-" * 72)
    print("SAMPLES — up to 5 random calls per category" + (
        f" (filtered to {sorted(only_category)})" if only_category else ""
    ))
    print("-" * 72)
    for line in _render_samples(sample_parsed, sample_outcomes, client_id_to_name):
        print(line)


def _print_apply_log(applied: list[pipeline.IngestOutcome]) -> None:
    counts = _aggregate_apply_counts(applied)
    cost = pipeline.estimate_embedding_cost_usd(counts.chunks_inserted)
    print()
    print("APPLY SUMMARY")
    print(f"  calls inserted:                 {counts.calls_inserted}")
    print(f"  calls updated:                  {counts.calls_updated}")
    print(f"  call_participants upserted:     {counts.participants_upserted}")
    print(f"  call_action_items inserted:     0  (deferred — conventions §5)")
    print(f"  documents created:              {counts.documents_created}")
    print(f"  documents soft-archived:        {counts.documents_archived}")
    print(f"  document_chunks inserted:       {counts.chunks_inserted}")
    print(f"  document_chunks reused:         {counts.chunks_reused}")
    print(f"  clients auto-created:           {counts.auto_created_clients}")
    print(f"  validation failures:            {counts.validation_failures}   (should be 0)")
    print(f"  embedding API calls:            {counts.chunks_inserted}")
    print(f"  estimated embedding cost:       ${cost:.4f}")


def _write_apply_log(
    report: RunReport,
    applied: list[pipeline.IngestOutcome],
    client_id_to_name: dict[str, str],
) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"run_{ts}.log"
    counts = _aggregate_apply_counts(applied)
    cost = pipeline.estimate_embedding_cost_usd(counts.chunks_inserted)

    body = {
        "timestamp_utc": ts,
        "total_files": report.total_files,
        "parsed": len(report.parsed) + report.filtered_out_by_since + report.filtered_out_by_limit,
        "parse_failures": [
            {"path": str(pf.path), "error": pf.error} for pf in report.parse_failures
        ],
        "classified": len(report.outcomes),
        "applied": len(applied),
        "filtered_by_since": report.filtered_out_by_since,
        "filtered_by_limit": report.filtered_out_by_limit,
        "filtered_by_only_category": report.filtered_out_by_only_category,
        "counts": counts.__dict__,
        "estimated_embedding_cost_usd": round(cost, 4),
        "per_category_totals": dict(Counter(o.category for o in report.outcomes)),
    }
    path.write_text(json.dumps(body, indent=2, default=str))
    return path


if __name__ == "__main__":
    sys.exit(main())
