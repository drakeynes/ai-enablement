"""Unit tests for ingestion.fathom.parser."""

from __future__ import annotations

from datetime import datetime, timezone
from textwrap import dedent

import pytest

from ingestion.fathom import parser as p


def _fixture_1on1() -> str:
    return dedent(
        """\
        Meeting: 30mins with Scott (The AI Partner) (Abel Asfaw)
        Date: 2026-02-16T21:03:59Z
        Scheduled: 2026-02-16T20:30:00Z - 2026-02-16T21:00:00Z
        Recording: 2026-02-16T20:50:40Z - 2026-02-16T21:03:51Z
        Language: en
        URL: https://fathom.video/calls/567855261
        Share Link: https://fathom.video/share/Cz8JHbryz5rhwih5yVp2p1_xJBsrqHZG
        Recording ID: 122784606

        Participants: Abel Asfaw (abel.f.asfaw@gmail.com), Scott Wilson (scott@theaipartner.io)
        Recorded by: Scott Wilson (scott@theaipartner.io)
        --- TRANSCRIPT ---

        [00:00:00] Abel Asfaw: I'm just doing all the stuff.
        [00:00:05] Abel Asfaw: Wow, thanks.
        [00:00:06] Scott Wilson: Which verification is that?
        """
    )


def _fixture_internal_with_quirks() -> str:
    return dedent(
        """\
        Meeting: CSM Sync
        Date: 2026-04-10T20:02:10Z
        Scheduled: 2026-04-10T19:30:00Z - 2026-04-10T20:00:00Z
        Recording: 2026-04-10T19:52:15Z - 2026-04-10T20:01:49Z
        Language: en
        URL: https://fathom.video/calls/631520289
        Share Link: https://fathom.video/share/aWJXgXzT4nUtW3FmULzFQTVW1TXycyV5
        Recording ID: 137158959

        Participants: Nabeel Junaid (nabeel@theaipartner.io), scott@theaipartner.io (scott@theaipartner.io), CALENDAR BLOCK OFF a (ellis@theaipartner.io), Lou Perez (lou@theaipartner.io)
        Recorded by: Lou Perez (lou@theaipartner.io)
        --- TRANSCRIPT ---

        [00:00:01] Scott Wilson: Yeah.
        [00:00:02] Scott Wilson: I know what it is.
        """
    )


# ---------------------------------------------------------------------------
# Happy path header + utterance parsing
# ---------------------------------------------------------------------------


def test_parse_text_extracts_header_fields():
    record = p.parse_text(_fixture_1on1())

    assert record.external_id == "122784606"
    assert record.title == "30mins with Scott (The AI Partner) (Abel Asfaw)"
    assert record.started_at == datetime(2026, 2, 16, 21, 3, 59, tzinfo=timezone.utc)
    assert record.scheduled_start == datetime(2026, 2, 16, 20, 30, tzinfo=timezone.utc)
    assert record.scheduled_end == datetime(2026, 2, 16, 21, 0, tzinfo=timezone.utc)
    assert record.recording_start is not None and record.recording_end is not None
    assert record.duration_seconds == 13 * 60 + 11   # 20:50:40 -> 21:03:51
    assert record.language == "en"
    assert record.recording_url == "https://fathom.video/calls/567855261"
    assert record.share_link.startswith("https://fathom.video/share/")


def test_parse_text_extracts_participants_email_first():
    record = p.parse_text(_fixture_1on1())

    emails = [pt.email for pt in record.participants]
    assert emails == ["abel.f.asfaw@gmail.com", "scott@theaipartner.io"]
    # display names survive as-is for normal entries
    assert record.participants[0].display_name == "Abel Asfaw"
    # recorded_by captured separately
    assert record.recorded_by is not None
    assert record.recorded_by.email == "scott@theaipartner.io"


def test_parse_text_handles_weird_participant_display_names():
    record = p.parse_text(_fixture_internal_with_quirks())
    by_email = {pt.email: pt.display_name for pt in record.participants}

    # CALENDAR BLOCK OFF a stays as-is — real artifact of how Scott
    # labels calendar entries; surface it rather than hide it.
    assert by_email["ellis@theaipartner.io"] == "CALENDAR BLOCK OFF a"
    # When display name is itself the email, it's preserved — cleaner
    # than doubling it; still not a useful display name, but accurate.
    assert by_email["scott@theaipartner.io"] == "scott@theaipartner.io"


def test_parse_text_extracts_utterances_in_order():
    record = p.parse_text(_fixture_1on1())

    assert len(record.utterances) == 3
    assert record.utterances[0].timestamp == "00:00:00"
    assert record.utterances[0].speaker == "Abel Asfaw"
    assert record.utterances[0].text.startswith("I'm just doing")
    assert record.utterances[2].speaker == "Scott Wilson"


def test_parse_text_preserves_transcript_and_raw_text():
    raw = _fixture_1on1()
    record = p.parse_text(raw)

    assert record.raw_text == raw   # verbatim preserved for calls.raw_payload
    assert "Abel Asfaw" in record.transcript
    assert "---" not in record.transcript  # separator is not kept


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_parse_text_without_action_items_succeeds():
    """The backlog export has no ACTION ITEM lines. Parser must not
    require them (and the pipeline deliberately doesn't populate
    call_action_items from these transcripts — see
    docs/ingestion/metadata-conventions.md §5 deferral)."""
    record = p.parse_text(_fixture_1on1())
    # Nothing in the parser surfaces action items; the pipeline skips
    # them for this source. The test guards against drift if someone
    # adds an action-item extractor without reading the deferral note.
    assert not hasattr(record, "action_items")


def test_parse_text_tolerates_extra_blank_lines_and_whitespace():
    raw = dedent(
        """\

        Meeting:   Owen
        Date: 2026-03-15T18:00:00Z

        Scheduled: 2026-03-15T17:30:00Z - 2026-03-15T18:00:00Z
        Recording: 2026-03-15T17:30:00Z - 2026-03-15T18:00:00Z
        Language: en
        URL: https://fathom.video/calls/123
        Share Link: https://fathom.video/share/abc
        Recording ID:   999

        Participants: Owen Nordberg (nordbergowen@gmail.com), Scott Wilson (scott@theaipartner.io)
        Recorded by: Scott Wilson (scott@theaipartner.io)

        --- TRANSCRIPT ---

        [00:00:00] Owen Nordberg: Hey.
        """
    )
    record = p.parse_text(raw)
    assert record.external_id == "999"
    assert record.title == "Owen"
    assert len(record.utterances) == 1


def test_parse_text_raises_when_recording_id_missing():
    raw = dedent(
        """\
        Meeting: Bad file
        Date: 2026-03-15T18:00:00Z
        URL: https://fathom.video/calls/123

        Participants: Owen (owen@example.com)
        Recorded by: Owen (owen@example.com)
        --- TRANSCRIPT ---

        [00:00:00] Owen: Hello.
        """
    )
    with pytest.raises(ValueError, match=r"Recording ID"):
        p.parse_text(raw)


def test_parse_text_raises_when_date_unparseable():
    raw = dedent(
        """\
        Meeting: Bad date
        Date: not-a-date
        Recording ID: 42

        Participants: Owen (owen@example.com)
        Recorded by: Owen (owen@example.com)
        --- TRANSCRIPT ---

        [00:00:00] Owen: Hello.
        """
    )
    with pytest.raises(ValueError, match=r"Date"):
        p.parse_text(raw)


def test_parse_text_preserves_unicode_in_speakers_and_text():
    raw = dedent(
        """\
        Meeting: Unicode sample
        Date: 2026-03-15T18:00:00Z
        Recording: 2026-03-15T18:00:00Z - 2026-03-15T18:05:00Z
        Recording ID: 101

        Participants: Renée Étienne (renee@example.com), João Silva (joao@example.com)
        Recorded by: Renée Étienne (renee@example.com)
        --- TRANSCRIPT ---

        [00:00:00] Renée Étienne: Olá — começamos?
        [00:00:02] João Silva: Sim, vamos lá!
        """
    )
    record = p.parse_text(raw)

    emails = [pt.email for pt in record.participants]
    assert "renee@example.com" in emails
    assert "joao@example.com" in emails
    assert record.utterances[0].speaker == "Renée Étienne"
    assert "começamos" in record.utterances[0].text


def test_parse_text_folds_continuation_lines_into_previous_utterance():
    """Some Fathom exports wrap very long utterances onto a second
    line without the `[HH:MM:SS] Speaker:` prefix. Rather than drop
    or warn, the parser folds the continuation into the previous
    utterance's text."""
    raw = dedent(
        """\
        Meeting: Continuation test
        Date: 2026-03-15T18:00:00Z
        Recording: 2026-03-15T18:00:00Z - 2026-03-15T18:05:00Z
        Recording ID: 202

        Participants: A (a@x.com), B (b@x.com)
        Recorded by: A (a@x.com)
        --- TRANSCRIPT ---

        [00:00:00] A: First part of a long thought
        that continues on the next line.
        [00:00:05] B: Got it.
        """
    )
    record = p.parse_text(raw)
    assert len(record.utterances) == 2
    assert record.utterances[0].text == (
        "First part of a long thought that continues on the next line."
    )


def test_parse_file_reads_from_disk(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(_fixture_1on1(), encoding="utf-8")

    record = p.parse_file(path)
    assert record.external_id == "122784606"
    assert record.source_path == path
