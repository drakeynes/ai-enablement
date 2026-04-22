"""Unit tests for ingestion.content.chunker."""

from __future__ import annotations

import pytest

from ingestion.content import chunker


def _text_of_n_words(n: int) -> str:
    """Build a text with exactly `n` whitespace-separated words arranged
    across paragraphs of ~50 words each."""
    words = [f"word{i}" for i in range(n)]
    paragraphs = []
    for start in range(0, n, 50):
        paragraphs.append(" ".join(words[start:start + 50]))
    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Chunk count by input size
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list():
    assert chunker.chunk_text("") == []
    assert chunker.chunk_text("   \n\n   ") == []


def test_short_lesson_returns_single_chunk():
    """Lessons under target_words come back as exactly one chunk
    containing the full text (so the lesson is still retrievable)."""
    text = _text_of_n_words(200)  # well under 500
    chunks = chunker.chunk_text(text, target_words=500)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    # Full text preserved
    assert chunks[0].content.count("word") == 200


def test_medium_lesson_produces_2_or_3_chunks():
    text = _text_of_n_words(1200)
    chunks = chunker.chunk_text(text, target_words=500, overlap_words=50)
    assert 2 <= len(chunks) <= 3
    # chunk_index values are 0..n-1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_long_lesson_produces_5_plus_chunks():
    text = _text_of_n_words(3000)
    chunks = chunker.chunk_text(text, target_words=500, overlap_words=50)
    assert len(chunks) >= 5


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


def test_overlap_between_adjacent_chunks():
    """Each non-first chunk starts with the tail of the previous chunk —
    a word from near the boundary appears in both."""
    text = _text_of_n_words(1500)
    chunks = chunker.chunk_text(text, target_words=500, overlap_words=50)
    assert len(chunks) >= 2
    for i in range(1, len(chunks)):
        prev_words = set(chunks[i - 1].content.split())
        curr_lead = set(chunks[i].content.split()[:60])
        # Some overlap words should appear in both
        assert prev_words & curr_lead, (
            f"expected overlap between chunk {i-1} and {i}"
        )


def test_no_overlap_when_overlap_words_zero():
    text = _text_of_n_words(1500)
    chunks = chunker.chunk_text(text, target_words=500, overlap_words=0)
    assert len(chunks) >= 2
    # With zero overlap, the first word of chunk i+1 should NOT appear
    # as the last word of chunk i (a weak but serviceable check).
    for i in range(1, len(chunks)):
        first = chunks[i].content.split()[0]
        last_of_prev = chunks[i - 1].content.split()[-1]
        assert first != last_of_prev


# ---------------------------------------------------------------------------
# Chunk shape
# ---------------------------------------------------------------------------


def test_chunk_metadata_carries_word_count():
    chunks = chunker.chunk_text(_text_of_n_words(300))
    assert chunks[0].metadata.get("chunk_word_count") == 300


def test_chunks_sized_around_target():
    chunks = chunker.chunk_text(_text_of_n_words(3000), target_words=500)
    word_counts = [c.metadata["chunk_word_count"] for c in chunks]
    # Every non-terminal chunk should be between ~target and target+overlap
    for wc in word_counts[:-1]:
        assert 400 <= wc <= 700, f"chunk size out of band: {wc}"


def test_paragraphs_preserved_within_chunks():
    text = "Para one sentence.\n\nPara two sentence.\n\nPara three sentence."
    chunks = chunker.chunk_text(text, target_words=500)
    assert len(chunks) == 1
    assert "Para one" in chunks[0].content
    assert "Para two" in chunks[0].content
    assert "Para three" in chunks[0].content
    # Blank lines between paragraphs preserved
    assert "\n\n" in chunks[0].content
