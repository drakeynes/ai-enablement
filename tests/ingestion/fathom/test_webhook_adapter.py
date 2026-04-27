"""Unit tests for ingestion.fathom.webhook_adapter.

Covers the happy path + the four edge cases called out in the F2.3 spec:
empty/missing summary, empty action_items, participant with no email,
empty transcript. Payload shape mirrors the OpenAPI `Meeting` component
verbatim — when Fathom's first real delivery lands in F2.5, add a
fixture from that delivery here and assert round-trip equality.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ingestion.fathom import webhook_adapter as a
from ingestion.fathom.parser import ActionItem


def _fixture_happy_path() -> dict:
    """Spec-exact payload matching the `Meeting` schema in the OpenAPI.

    Participant emails pinned to Javi Pena's canonical primary email so
    that when the integration test in test_webhook_pipeline_integration
    (if we add one later) runs against cloud, this participant resolves
    cleanly without auto-creating a row.
    """
    return {
        "title": "Fathom Test Call (F2.3)",
        "meeting_title": None,
        "recording_id": 998001002,
        "url": "https://fathom.video/calls/998001002",
        "share_url": "https://fathom.video/share/TEST_F23_HAPPY",
        "created_at": "2026-04-24T18:00:00Z",
        "scheduled_start_time": "2026-04-24T17:30:00Z",
        "scheduled_end_time": "2026-04-24T18:00:00Z",
        "recording_start_time": "2026-04-24T17:32:15Z",
        "recording_end_time": "2026-04-24T17:58:45Z",
        "calendar_invitees_domains_type": "one_or_more_external",
        "transcript_language": "en",
        "transcript": [
            {
                "speaker": {
                    "display_name": "Javi Pena",
                    "matched_calendar_invitee_email": "javpen93@gmail.com",
                },
                "text": "Let me walk through what we've been testing.",
                "timestamp": "00:00:15",
            },
            {
                "speaker": {"display_name": "Scott Wilson"},
                "text": "Great, go ahead.",
                "timestamp": "00:00:22",
            },
        ],
        "default_summary": {
            "markdown": "Javi walked Scott through the testing plan. Next steps on setter hiring.",
        },
        "action_items": [
            {
                "description": "Javi to send the setter JD by Friday",
                "user_generated": False,
                "completed": False,
                "recording_timestamp": "00:24:15",
                "recording_playback_url": "https://fathom.video/share/TEST_F23_HAPPY?t=1455",
                "assignee": {"name": "Javi Pena", "email": "javpen93@gmail.com"},
            },
            {
                "description": "Scott to review the draft",
                "user_generated": True,
                "completed": True,
                "recording_timestamp": "00:25:50",
                "recording_playback_url": None,
                "assignee": {"name": "Scott Wilson", "email": "scott@theaipartner.io"},
            },
        ],
        "calendar_invitees": [
            {
                "name": "Javi Pena",
                "matched_speaker_display_name": "Javi Pena",
                "email": "javpen93@gmail.com",
                "email_domain": "gmail.com",
                "is_external": True,
            },
            {
                "name": "Scott Wilson",
                "matched_speaker_display_name": "Scott Wilson",
                "email": "scott@theaipartner.io",
                "email_domain": "theaipartner.io",
                "is_external": False,
            },
        ],
        "recorded_by": {
            "name": "Scott Wilson",
            "email": "scott@theaipartner.io",
        },
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_roundtrips_every_documented_field():
    payload = _fixture_happy_path()
    record = a.record_from_webhook(payload)

    # Identity
    assert record.external_id == "998001002"               # str cast from int
    assert record.title == "Fathom Test Call (F2.3)"
    assert record.source_format == "fathom_webhook"

    # Timestamps timezone-aware UTC
    assert record.started_at == datetime(2026, 4, 24, 17, 32, 15, tzinfo=timezone.utc)
    assert record.recording_end == datetime(2026, 4, 24, 17, 58, 45, tzinfo=timezone.utc)
    assert record.scheduled_start == datetime(2026, 4, 24, 17, 30, tzinfo=timezone.utc)
    assert record.duration_seconds == 26 * 60 + 30         # 26:30 elapsed

    # URLs + language
    assert record.recording_url == "https://fathom.video/calls/998001002"
    assert record.share_link == "https://fathom.video/share/TEST_F23_HAPPY"
    assert record.language == "en"

    # Participants mapped + emails lowercased
    emails = sorted(p.email for p in record.participants)
    assert emails == ["javpen93@gmail.com", "scott@theaipartner.io"]
    names = sorted(p.display_name for p in record.participants)
    assert names == ["Javi Pena", "Scott Wilson"]
    assert record.recorded_by is not None
    assert record.recorded_by.email == "scott@theaipartner.io"

    # Transcript utterances preserved; transcript string rendered in
    # backlog-equivalent shape so downstream columns are source-agnostic
    assert len(record.utterances) == 2
    assert record.utterances[0].speaker == "Javi Pena"
    assert record.utterances[0].timestamp == "00:00:15"
    assert "[00:00:15] Javi Pena: Let me walk through" in record.transcript
    assert "[00:00:22] Scott Wilson: Great, go ahead." in record.transcript

    # Summary extraction prefers markdown
    assert record.summary_text is not None
    assert "Javi walked Scott through" in record.summary_text

    # Action items
    assert record.action_items is not None
    assert len(record.action_items) == 2
    assert record.action_items[0].description == "Javi to send the setter JD by Friday"
    assert record.action_items[0].assignee_email == "javpen93@gmail.com"
    assert record.action_items[0].completed is False
    assert record.action_items[1].completed is True
    assert record.action_items[1].assignee_email == "scott@theaipartner.io"

    # Raw payload preserved as JSON string for replay/re-parse
    assert json.loads(record.raw_text)["recording_id"] == 998001002


# ---------------------------------------------------------------------------
# Edge: summary missing / empty
# ---------------------------------------------------------------------------


def test_summary_missing_produces_none():
    payload = _fixture_happy_path()
    payload.pop("default_summary")
    record = a.record_from_webhook(payload)
    assert record.summary_text is None


def test_summary_empty_dict_produces_none():
    payload = _fixture_happy_path()
    payload["default_summary"] = {}
    record = a.record_from_webhook(payload)
    assert record.summary_text is None


def test_summary_plain_string_accepted():
    payload = _fixture_happy_path()
    payload["default_summary"] = "Plain string summary"
    record = a.record_from_webhook(payload)
    assert record.summary_text == "Plain string summary"


def test_summary_with_text_field_accepted():
    """Common fallback shape when `markdown` isn't provided."""
    payload = _fixture_happy_path()
    payload["default_summary"] = {"text": "Plain-text summary"}
    record = a.record_from_webhook(payload)
    assert record.summary_text == "Plain-text summary"


def test_summary_with_markdown_formatted_field_accepted():
    """Real Fathom shape verified 2026-04-27 against M1.2.5 cron sweep.

    Fathom delivers `default_summary` as `{"markdown_formatted": "...",
    "template_name": "..."}`. F2.1 doc read missed this — neither
    `markdown_formatted` nor `template_name` were in the spec. M1.2.5
    ingested 15 client calls with 0 summary docs because the adapter
    didn't recognize the key. This test pins the real shape so a
    future regression can't drop it again."""
    payload = _fixture_happy_path()
    payload["default_summary"] = {
        "markdown_formatted": "## Customer:\n\n[Fernando — bilingual SDR...]",
        "template_name": "Customer Success",
    }
    record = a.record_from_webhook(payload)
    assert record.summary_text is not None
    assert record.summary_text.startswith("## Customer:")
    assert "Fernando" in record.summary_text


def test_summary_priority_markdown_formatted_over_others():
    """When a payload has both `markdown_formatted` AND a fallback key,
    the canonical Fathom shape (markdown_formatted) wins."""
    payload = _fixture_happy_path()
    payload["default_summary"] = {
        "markdown_formatted": "the canonical one",
        "markdown": "the fallback",
        "text": "another fallback",
    }
    record = a.record_from_webhook(payload)
    assert record.summary_text == "the canonical one"


def test_summary_whitespace_only_produces_none():
    payload = _fixture_happy_path()
    payload["default_summary"] = {"markdown": "   \n\n  "}
    record = a.record_from_webhook(payload)
    assert record.summary_text is None


# ---------------------------------------------------------------------------
# Edge: action_items empty vs missing (three-state contract matters)
# ---------------------------------------------------------------------------


def test_action_items_missing_is_none_not_empty_list():
    """Pipeline contract: None means 'no info, leave DB alone'; [] means
    'call has zero items, delete any existing'. Missing key = None."""
    payload = _fixture_happy_path()
    payload.pop("action_items")
    record = a.record_from_webhook(payload)
    assert record.action_items is None


def test_action_items_explicit_empty_list_preserved():
    payload = _fixture_happy_path()
    payload["action_items"] = []
    record = a.record_from_webhook(payload)
    assert record.action_items == []


def test_action_items_assignee_missing_tolerated():
    payload = _fixture_happy_path()
    payload["action_items"] = [
        {"description": "Follow up next week", "user_generated": False, "completed": False}
    ]
    record = a.record_from_webhook(payload)
    assert record.action_items is not None
    assert len(record.action_items) == 1
    assert record.action_items[0].assignee_email is None
    assert record.action_items[0].assignee_display_name is None
    assert record.action_items[0].description == "Follow up next week"


# ---------------------------------------------------------------------------
# Edge: participant with no email
# ---------------------------------------------------------------------------


def test_participant_without_email_is_skipped():
    """Fathom sometimes has invitees without a captured email (rare but
    observed in the backlog). They can't participate in downstream keying
    (call_participants unique on (call_id, email); resolver looks up by
    email). Skipping at the adapter keeps the pipeline idempotent and
    avoids a NULL-email row that nothing can reason about."""
    payload = _fixture_happy_path()
    payload["calendar_invitees"].append({
        "name": "Ghost Participant",
        "email": None,
        "email_domain": None,
        "is_external": True,
    })
    record = a.record_from_webhook(payload)
    # Still just the original 2 invitees with emails
    assert len(record.participants) == 2
    assert "Ghost Participant" not in {p.display_name for p in record.participants}


# ---------------------------------------------------------------------------
# Edge: transcript empty / missing
# ---------------------------------------------------------------------------


def test_transcript_missing_gives_empty_utterances():
    payload = _fixture_happy_path()
    payload.pop("transcript")
    record = a.record_from_webhook(payload)
    assert record.utterances == []
    assert record.transcript == ""


def test_transcript_explicit_empty_list_handled():
    payload = _fixture_happy_path()
    payload["transcript"] = []
    record = a.record_from_webhook(payload)
    assert record.utterances == []


# ---------------------------------------------------------------------------
# Required-field enforcement
# ---------------------------------------------------------------------------


def test_missing_recording_id_raises_adapter_error():
    payload = _fixture_happy_path()
    payload.pop("recording_id")
    with pytest.raises(a.AdapterError) as exc:
        a.record_from_webhook(payload)
    assert "recording_id" in str(exc.value)


def test_missing_recording_start_time_raises():
    payload = _fixture_happy_path()
    payload.pop("recording_start_time")
    with pytest.raises(a.AdapterError):
        a.record_from_webhook(payload)


def test_malformed_timestamp_raises_adapter_error_not_valueerror():
    payload = _fixture_happy_path()
    payload["recording_start_time"] = "not a real timestamp"
    with pytest.raises(a.AdapterError) as exc:
        a.record_from_webhook(payload)
    assert "unparseable" in str(exc.value).lower() or "timestamp" in str(exc.value).lower()


def test_naive_timestamp_coerced_to_utc():
    """Spec says ISO 8601 with offset — but be resilient. A naive timestamp
    should be coerced to UTC rather than reject the whole delivery."""
    payload = _fixture_happy_path()
    payload["recording_start_time"] = "2026-04-24T17:32:15"
    record = a.record_from_webhook(payload)
    assert record.started_at.tzinfo is timezone.utc
