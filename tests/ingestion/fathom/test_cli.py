"""Unit tests for ingestion.fathom.cli.

Smoke-level: verify argparse wiring, zip-vs-directory input resolution,
and that --apply routes through the pipeline. Full pipeline logic is
tested in test_pipeline.py.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from textwrap import dedent
from zipfile import ZipFile

import pytest

from ingestion.fathom import cli
from ingestion.fathom import pipeline


def _sample_transcript() -> str:
    return dedent(
        """\
        Meeting: 30mins with Scott (The AI Partner) (Sample Client)
        Date: 2026-02-10T18:00:00Z
        Scheduled: 2026-02-10T17:30:00Z - 2026-02-10T18:00:00Z
        Recording: 2026-02-10T17:30:00Z - 2026-02-10T17:40:00Z
        Language: en
        URL: https://fathom.video/calls/1
        Share Link: https://fathom.video/share/x
        Recording ID: 1001

        Participants: Scott Wilson (scott@theaipartner.io), Sample Client (sample@example.com)
        Recorded by: Scott Wilson (scott@theaipartner.io)
        --- TRANSCRIPT ---

        [00:00:00] Scott Wilson: Here is the meaningful content we had today about building.
        [00:00:05] Sample Client: I will email you the spec by Friday.
        """
    )


def _fake_empty_response():
    from types import SimpleNamespace
    return SimpleNamespace(data=[])


def _make_db(mocker):
    """Mock DB that returns empty for every select and records inserts."""
    fake_db = mocker.MagicMock()

    def table(_name):
        chain = mocker.MagicMock()
        chain.select.return_value.is_.return_value.execute.return_value = _fake_empty_response()
        chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = _fake_empty_response()
        chain.select.return_value.eq.return_value.execute.return_value = _fake_empty_response()
        chain.select.return_value.execute.return_value = _fake_empty_response()
        chain.insert.return_value.execute.return_value = _fake_empty_response()
        chain.update.return_value.eq.return_value.execute.return_value = _fake_empty_response()
        chain.upsert.return_value.execute.return_value = _fake_empty_response()
        return chain

    fake_db.table.side_effect = table
    return fake_db


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


def test_iter_txt_files_from_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "ignore.md").write_text("x")

    found = sorted(p.name for p in cli._iter_txt_files(tmp_path))
    assert found == ["a.txt", "b.txt"]


def test_iter_txt_files_from_zip(tmp_path):
    zip_path = tmp_path / "archive.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr("first.txt", "x")
        zf.writestr("second.txt", "x")
        zf.writestr("ignore.md", "x")

    found = sorted(p.name for p in cli._iter_txt_files(zip_path))
    assert found == ["first.txt", "second.txt"]

    # Cleanup extraction directory the iterator created
    cli._cleanup_extracted()


def test_iter_txt_files_rejects_other_extensions(tmp_path):
    weird = tmp_path / "file.gz"
    weird.write_text("x")
    with pytest.raises(SystemExit):
        list(cli._iter_txt_files(weird))


# ---------------------------------------------------------------------------
# --since and --limit filters
# ---------------------------------------------------------------------------


def test_since_filter_drops_older_records():
    from ingestion.fathom.parser import parse_text

    old = parse_text(_sample_transcript())
    newer = parse_text(_sample_transcript().replace("2026-02-10", "2026-04-01"))
    records = [
        cli.ParsedRecord(path=Path("/tmp/a.txt"), record=old, file_size_bytes=1000),
        cli.ParsedRecord(path=Path("/tmp/b.txt"), record=newer, file_size_bytes=1000),
    ]
    kept, filtered = cli._apply_since_filter(records, date(2026, 3, 1))
    assert len(kept) == 1
    assert filtered == 1
    assert kept[0].path.name == "b.txt"


def test_limit_caps_records():
    records = [
        cli.ParsedRecord(path=Path(f"/tmp/{i}.txt"), record=None, file_size_bytes=1)
        for i in range(5)
    ]
    kept, filtered = cli._apply_limit(records, limit=3)
    assert len(kept) == 3
    assert filtered == 2


# ---------------------------------------------------------------------------
# Dry-run + apply flow integration (single file)
# ---------------------------------------------------------------------------


def test_cli_dry_run_runs_classification_but_does_not_apply(mocker, tmp_path, capsys):
    # One sample transcript
    transcript = tmp_path / "sample.txt"
    transcript.write_text(_sample_transcript())

    fake_db = _make_db(mocker)
    mocker.patch("ingestion.fathom.cli.get_client", return_value=fake_db)
    mocker.patch(
        "ingestion.fathom.cli.pipeline.load_resolvers",
        return_value=(
            __import__("ingestion.fathom.classifier", fromlist=["ClientResolver"])
            .ClientResolver({"sample@example.com": "c-1"}),
            pipeline.TeamMemberResolver({"scott@theaipartner.io": "tm-1"}),
            {"c-1": "Sample Client"},
        ),
    )
    ingest_spy = mocker.spy(pipeline, "ingest_call")

    rc = cli.main(["--input", str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "FATHOM BACKLOG INGESTION" in out
    assert "Dry run only" in out
    # ingest_call was called (dry-run) once
    assert ingest_spy.call_count == 1
    # All calls in dry-run mode
    assert all(kwargs.get("dry_run") is True for _, kwargs in ingest_spy.call_args_list)


def test_cli_apply_flow_invokes_ingest_in_live_mode(mocker, tmp_path):
    transcript = tmp_path / "sample.txt"
    transcript.write_text(_sample_transcript())

    fake_db = _make_db(mocker)
    mocker.patch("ingestion.fathom.cli.get_client", return_value=fake_db)
    mocker.patch(
        "ingestion.fathom.cli.pipeline.load_resolvers",
        return_value=(
            __import__("ingestion.fathom.classifier", fromlist=["ClientResolver"])
            .ClientResolver({"sample@example.com": "c-1"}),
            pipeline.TeamMemberResolver({"scott@theaipartner.io": "tm-1"}),
            {"c-1": "Sample Client"},
        ),
    )
    # Mock embed to avoid OpenAI
    mocker.patch("shared.kb_query.embed", return_value=[0.0] * 1536)
    # Make ingest_call return a simple outcome to avoid deep DB shape munging
    fake_outcome = pipeline.IngestOutcome(
        external_id="1001", call_id="call-1", category="client", call_type="coaching",
        confidence=0.9, method="title_pattern", primary_client_id="c-1",
        primary_client_name="Sample Client",
        auto_created_client_id=None, auto_created_client_email=None,
        participants_linked_to_clients=1, participants_linked_to_team=1,
        document_id="doc-1", chunks_written=2, chunks_reused=0,
        retrievable=True, retrievable_before=None, action="inserted",
    )
    ingest = mocker.patch(
        "ingestion.fathom.cli.pipeline.ingest_call", return_value=fake_outcome
    )

    rc = cli.main(["--input", str(tmp_path), "--apply"])

    assert rc == 0
    # Two calls: one dry-run pass for classification, one apply pass
    assert ingest.call_count == 2
    last_call = ingest.call_args_list[-1]
    assert last_call.kwargs.get("dry_run") is False
