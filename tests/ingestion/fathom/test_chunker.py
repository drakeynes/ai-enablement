"""Unit tests for ingestion.fathom.chunker."""

from __future__ import annotations

import pytest

from ingestion.fathom import chunker
from ingestion.fathom.parser import Utterance


def _utt(ts: str, speaker: str, text: str) -> Utterance:
    return Utterance(timestamp=ts, speaker=speaker, text=text)


def _alternating_utterances(total_words: int, words_per_utt: int = 20) -> list[Utterance]:
    """Build utterances alternating between two speakers at known word counts."""
    utterances = []
    speakers = ["Drake", "Scott"]
    word = "alpha"
    ts_seconds = 0
    total = 0
    i = 0
    while total < total_words:
        remaining = total_words - total
        take = min(words_per_utt, remaining)
        text = " ".join([word] * take)
        m, s = divmod(ts_seconds, 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}"
        utterances.append(_utt(ts, speakers[i % 2], text))
        total += take
        ts_seconds += 5
        i += 1
    return utterances


# ---------------------------------------------------------------------------
# Filler filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("yeah", True),
        ("Yeah.", True),
        ("yeah!", True),
        ("100%", True),
        ("for sure", True),
        ("mm-hmm", True),
        ("okay", True),
        ("sure", True),
        # Short utterance with a digit = keep
        ("Okay, $900 then", False),
        # Short utterance with a proper noun (capital letter after pos 0) = keep
        ("Yeah, Scott said", False),
        # Short utterance with a domain verb = keep
        ("send it", False),
        # Longer utterance, not checked against filler set regardless
        ("yeah that is what I was trying to understand", False),
    ],
)
def test_pure_filler_detection(text, expected):
    assert chunker._is_pure_filler(text) is expected


def test_filter_fillers_drops_pure_filler_keeps_substantive():
    utts = [
        _utt("00:00:00", "A", "yeah"),
        _utt("00:00:01", "A", "I need you to email Scott by Friday"),
        _utt("00:00:05", "A", "100%"),
        _utt("00:00:06", "B", "Okay, $900 then"),   # digits, kept
    ]
    filtered = chunker.filter_fillers(utts)
    assert len(filtered) == 2
    assert filtered[0].text == "I need you to email Scott by Friday"
    assert filtered[1].text == "Okay, $900 then"


# ---------------------------------------------------------------------------
# Chunk count by input size
# ---------------------------------------------------------------------------


def test_400_word_input_produces_one_chunk():
    utts = _alternating_utterances(total_words=400)
    chunks = chunker.chunk_transcript(utts)
    assert len(chunks) == 1
    # Single chunk has no overlap section
    assert not chunks[0].content.startswith("[00:00:00]\n\n[")


def test_1200_word_input_produces_multiple_chunks_with_overlap():
    utts = _alternating_utterances(total_words=1200, words_per_utt=20)
    chunks = chunker.chunk_transcript(utts, target_words=500, overlap_words=50)
    # 1200 words / ~500 target = ~2-3 chunks
    assert 2 <= len(chunks) <= 3
    # Every non-first chunk starts with an overlap preamble drawn from
    # the tail of the previous chunk. The first line of each non-first
    # chunk should be an utterance-formatted line.
    for c in chunks[1:]:
        first_line = c.content.splitlines()[0]
        assert first_line.startswith("[")


def test_empty_input_returns_empty_list():
    assert chunker.chunk_transcript([]) == []


def test_all_fillers_returns_empty_list():
    utts = [_utt("00:00:00", "A", "yeah"), _utt("00:00:01", "B", "ok")]
    assert chunker.chunk_transcript(utts) == []


# ---------------------------------------------------------------------------
# Speaker-turn boundary preservation
# ---------------------------------------------------------------------------


def test_chunks_end_at_speaker_turn_boundaries():
    """No chunk ends mid-utterance — closing line is always a complete
    `[ts] Speaker: text` line (which implies we didn't split inside a
    speaker turn)."""
    utts = _alternating_utterances(total_words=1500, words_per_utt=30)
    chunks = chunker.chunk_transcript(utts, target_words=400)
    for c in chunks:
        last_line = c.content.rstrip().splitlines()[-1]
        assert last_line.startswith("[")
        assert "]" in last_line
        # A complete line ends with real text content, not a hanging word
        assert ":" in last_line


def test_speaker_labels_preserved_in_chunk_text():
    utts = [
        _utt("00:00:00", "Drake", "here is the context for the call today"),
        _utt("00:00:05", "Scott", "great let us dig into the numbers"),
    ]
    chunks = chunker.chunk_transcript(utts)
    assert len(chunks) == 1
    assert "[00:00:00] Drake:" in chunks[0].content
    assert "[00:00:05] Scott:" in chunks[0].content


# ---------------------------------------------------------------------------
# Per-chunk metadata
# ---------------------------------------------------------------------------


def test_chunk_metadata_has_required_keys():
    utts = _alternating_utterances(total_words=400)
    chunks = chunker.chunk_transcript(utts)
    md = chunks[0].metadata
    assert set(md.keys()) >= {"chunk_start_ts", "chunk_end_ts", "speaker_list", "speaker_turn_count"}
    assert md["chunk_start_ts"] == "00:00:00"
    assert md["speaker_list"] == ["Drake", "Scott"]
    assert md["speaker_turn_count"] >= 2


def test_short_utterance_with_proper_noun_kept_in_chunk():
    """Regression guard: 'Yeah, Scott said' must survive the filter."""
    utts = [_utt("00:00:00", "A", "Yeah, Scott said")]
    chunks = chunker.chunk_transcript(utts)
    assert len(chunks) == 1
    assert "Yeah, Scott said" in chunks[0].content
