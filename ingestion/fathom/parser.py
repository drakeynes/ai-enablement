"""Parse Fathom .txt transcript exports into a structured `FathomCallRecord`.

Expected file shape (header + transcript separated by `--- TRANSCRIPT ---`):

    Meeting: 30mins with Scott (The AI Partner) (Abel Asfaw)
    Date: 2026-02-16T21:03:59Z
    Scheduled: 2026-02-16T20:30:00Z - 2026-02-16T21:00:00Z
    Recording: 2026-02-16T20:50:40Z - 2026-02-16T21:03:51Z
    Language: en
    URL: https://fathom.video/calls/567855261
    Share Link: https://fathom.video/share/...
    Recording ID: 122784606

    Participants: Abel Asfaw (abel.f.asfaw@gmail.com), Scott Wilson (scott@theaipartner.io)
    Recorded by: Scott Wilson (scott@theaipartner.io)
    --- TRANSCRIPT ---

    [00:00:00] Abel Asfaw: I'm just doing all the stuff...
    [00:00:05] Abel Asfaw: Wow, thanks.
    ...

Robust to common drift: leading/trailing whitespace, optional blank
lines between header fields, participant display-name quirks (e.g.
`scott@theaipartner.io (scott@theaipartner.io)` or
`CALENDAR BLOCK OFF a (ellis@theaipartner.io)`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_TRANSCRIPT_SEPARATOR_RE = re.compile(r"^---\s*TRANSCRIPT\s*---\s*$", re.MULTILINE)
_UTTERANCE_RE = re.compile(
    r"^\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s+(?P<speaker>.+?):\s*(?P<text>.*)$"
)
_PARTICIPANT_RE = re.compile(r"\s*(?P<name>.+?)\s*\((?P<email>[^)]+)\)\s*$")


@dataclass(frozen=True)
class Participant:
    display_name: str
    email: str


@dataclass(frozen=True)
class Utterance:
    timestamp: str      # "HH:MM:SS" wall-clock offset from recording start
    speaker: str
    text: str


@dataclass(frozen=True)
class ActionItem:
    """One action item extracted from a call.

    Shape mirrors Fathom's webhook `ActionItem` with light normalization
    (email lowercased, playback url preserved verbatim). The backlog TXT
    path never populates these — backlog records leave
    `FathomCallRecord.action_items = None`. Only the webhook adapter
    produces ActionItem instances.
    """
    description: str
    user_generated: bool
    completed: bool
    recording_timestamp: str | None = None     # "HH:MM:SS" or None
    recording_playback_url: str | None = None
    assignee_email: str | None = None
    assignee_display_name: str | None = None


@dataclass(frozen=True)
class FathomCallRecord:
    """Structured view of a Fathom call — from either the .txt backlog
    export or the `new-meeting-content-ready` webhook payload."""

    # external_id comes from the Recording ID line, NOT from the URL's
    # call id. Recording ID is Fathom's durable artifact identifier and
    # matches what the webhook / REST API payloads surface as the key
    # for a recorded call — using it keeps the backlog ingestion
    # aligned with the future real-time webhook pipeline.
    external_id: str
    title: str
    started_at: datetime
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    recording_start: datetime | None
    recording_end: datetime | None
    duration_seconds: int | None
    language: str | None
    recording_url: str | None
    share_link: str | None
    participants: list[Participant]
    recorded_by: Participant | None
    utterances: list[Utterance]
    transcript: str
    raw_text: str
    source_path: Path | None = None
    parse_warnings: list[str] = field(default_factory=list)

    # Webhook-sourced fields — None on TXT backlog records, populated by
    # ingestion.fathom.webhook_adapter when ingesting from live deliveries.
    # Three-state semantics on action_items matter for the pipeline:
    #   None -> "no info, don't touch DB"
    #   []   -> "call has zero action items; delete any existing, write none"
    #   [..] -> "write these, replacing any existing for the call"
    summary_text: str | None = None
    action_items: list[ActionItem] | None = None

    # "txt" (backlog) or "fathom_webhook" (live). Persisted into
    # calls.raw_payload.source_format so the origin of a row is recoverable
    # from the DB alone — matters when debugging a mis-ingested call or
    # when the webhook payload shape evolves and we need to re-parse a
    # single source's rows.
    source_format: str = "txt"


def parse_file(path: Path | str) -> FathomCallRecord:
    """Read a Fathom `.txt` file and return a parsed record."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    record = parse_text(text)
    return _with_source_path(record, path)


def parse_text(raw_text: str) -> FathomCallRecord:
    """Parse the raw contents of a Fathom `.txt` export."""
    header, transcript_text = _split_header_and_transcript(raw_text)
    fields = _parse_header_fields(header)
    warnings: list[str] = []

    external_id = fields.get("recording id")
    if not external_id:
        raise ValueError(
            "Transcript is missing the `Recording ID:` line — cannot produce "
            "a stable external_id for the calls row. See parser docstring."
        )

    title = fields.get("meeting") or "(untitled)"
    started_at = _parse_iso(fields.get("date"))
    if started_at is None:
        raise ValueError("Transcript is missing a parseable `Date:` line.")

    scheduled_start, scheduled_end = _parse_range(fields.get("scheduled"))
    recording_start, recording_end = _parse_range(fields.get("recording"))

    duration_seconds: int | None = None
    if recording_start and recording_end and recording_end >= recording_start:
        duration_seconds = int((recording_end - recording_start).total_seconds())

    participants = _parse_participants(fields.get("participants") or "")
    recorded_by = _parse_recorded_by(fields.get("recorded by"))

    utterances, utterance_warnings = _parse_utterances(transcript_text)
    warnings.extend(utterance_warnings)

    transcript_text_clean = transcript_text.strip("\n")

    return FathomCallRecord(
        external_id=external_id.strip(),
        title=title.strip(),
        started_at=started_at,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        recording_start=recording_start,
        recording_end=recording_end,
        duration_seconds=duration_seconds,
        language=(fields.get("language") or None),
        recording_url=(fields.get("url") or None),
        share_link=(fields.get("share link") or None),
        participants=participants,
        recorded_by=recorded_by,
        utterances=utterances,
        transcript=transcript_text_clean,
        raw_text=raw_text,
        parse_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _with_source_path(record: FathomCallRecord, path: Path) -> FathomCallRecord:
    # frozen dataclass — swap via dataclasses.replace
    from dataclasses import replace
    return replace(record, source_path=path)


def _split_header_and_transcript(raw_text: str) -> tuple[str, str]:
    """Split the file on the `--- TRANSCRIPT ---` separator.

    Falls back to treating everything as header if the separator is
    absent (malformed file) — downstream callers will see an empty
    transcript and can decide how to handle it.
    """
    match = _TRANSCRIPT_SEPARATOR_RE.search(raw_text)
    if match is None:
        return raw_text, ""
    return raw_text[: match.start()], raw_text[match.end() :]


def _parse_header_fields(header: str) -> dict[str, str]:
    """Turn the header block into a {lowercased_label: value} dict.

    Tolerates blank lines and preserves whatever values are on the
    right of the first `: ` for each labeled line. Lines without a
    `:` are ignored. Labels are lowercased and stripped so downstream
    lookup is case-insensitive.
    """
    out: dict[str, str] = {}
    for line in header.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        label, _, value = stripped.partition(":")
        out[label.strip().lower()] = value.strip()
    return out


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp. Returns None on unparseable input."""
    if not value:
        return None
    text = value.strip()
    # Python's fromisoformat doesn't accept trailing 'Z' until 3.11+; we
    # support 3.11+ but be defensive.
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_range(value: str | None) -> tuple[datetime | None, datetime | None]:
    """Parse `<ISO> - <ISO>` into (start, end). Missing half → None."""
    if not value:
        return None, None
    parts = [p.strip() for p in value.split(" - ")]
    if len(parts) != 2:
        return _parse_iso(parts[0]) if parts else None, None
    return _parse_iso(parts[0]), _parse_iso(parts[1])


def _strip_duplicated_email_suffix(display_name: str, email: str) -> str:
    """If display_name is exactly the same as email, keep it.

    If display_name carries a parenthetical that is the email itself,
    strip the suffix. Weird artifacts (`CALENDAR BLOCK OFF a`) are
    preserved as-is — they're real data about how calendar entries
    are labeled.
    """
    cleaned = display_name.strip()
    # Example: "scott@theaipartner.io (scott@theaipartner.io)" reaches
    # this function with display_name already equal to email because
    # the regex captured it that way. Nothing extra to strip.
    return cleaned


def _parse_participants(value: str) -> list[Participant]:
    """Split `Name (email), Name (email), ...` into a participant list."""
    if not value:
        return []
    out: list[Participant] = []
    # Split on commas that separate distinct `Name (email)` entries.
    # Simple splitter works because emails can't contain commas.
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _PARTICIPANT_RE.match(chunk)
        if match is None:
            continue
        name = match.group("name").strip()
        email = match.group("email").strip().lower()
        display = _strip_duplicated_email_suffix(name, email)
        out.append(Participant(display_name=display, email=email))
    return out


def _parse_recorded_by(value: str | None) -> Participant | None:
    if not value:
        return None
    match = _PARTICIPANT_RE.match(value.strip())
    if match is None:
        return None
    name = match.group("name").strip()
    email = match.group("email").strip().lower()
    return Participant(display_name=name, email=email)


def _parse_utterances(transcript_text: str) -> tuple[list[Utterance], list[str]]:
    """Convert each `[HH:MM:SS] Speaker: text` line into an Utterance.

    Lines that don't match the pattern are collected into a warnings
    list rather than silently dropped. Empty lines are skipped.
    """
    utterances: list[Utterance] = []
    warnings: list[str] = []
    for idx, line in enumerate(transcript_text.splitlines(), start=1):
        if not line.strip():
            continue
        match = _UTTERANCE_RE.match(line)
        if match is None:
            # Malformed line in the transcript body — fold it into the
            # previous utterance's text when possible, otherwise record
            # a warning. Continuation lines would otherwise become
            # empty ghost utterances.
            if utterances:
                last = utterances[-1]
                utterances[-1] = Utterance(
                    timestamp=last.timestamp,
                    speaker=last.speaker,
                    text=(last.text + " " + line.strip()).strip(),
                )
            else:
                warnings.append(f"unmatched transcript line {idx}: {line!r}")
            continue
        utterances.append(
            Utterance(
                timestamp=match.group("ts"),
                speaker=match.group("speaker").strip(),
                text=match.group("text").strip(),
            )
        )
    return utterances, warnings
