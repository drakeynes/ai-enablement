"""Chunk lesson prose into retrievable pieces with ~50-word overlap.

Prose-tuned cousin of `ingestion/fathom/chunker.py`. Differences:

  - No speaker rules — prose has no speaker turns; boundaries come
    from paragraph breaks (blank line) and, failing that, sentence
    ends.
  - No filler filter — filler is a spoken-content concept.
  - Short lessons (< target_words) return a single chunk of the full
    text. We explicitly want every lesson retrievable even when tiny.

Target chunk size 400-600 words (aim ~500), ~50-word overlap on
adjacent chunks. Matches the retrieval-time budget Ella plans around.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DEFAULT_TARGET_WORDS = 500
DEFAULT_OVERLAP_WORDS = 50


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    content: str
    metadata: dict[str, Any]


# Split on blank-line paragraph boundaries first; if a paragraph on its
# own exceeds target, fall back to sentence-ish splits inside it.
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(
    text: str,
    *,
    target_words: int = DEFAULT_TARGET_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[Chunk]:
    """Split `text` into chunks sized around `target_words`.

    Empty input returns an empty list. Short text (< target_words)
    returns exactly one chunk with the full text.
    """
    if not text.strip():
        return []

    total_words = len(text.split())
    if total_words <= target_words:
        return [Chunk(chunk_index=0, content=text.strip(), metadata={
            "chunk_word_count": total_words,
        })]

    # Split into paragraphs; then into sentences within oversized paragraphs.
    atoms = _split_atoms(text, target_words=target_words)

    chunks: list[Chunk] = []
    current: list[str] = []
    current_words = 0
    for atom in atoms:
        atom_words = len(atom.split())
        if current and current_words + atom_words > target_words:
            chunks.append(_make_chunk(len(chunks), current))
            # Prime the next chunk with an overlap tail.
            overlap_lines = _tail_words(current, overlap_words)
            current = list(overlap_lines)
            current_words = sum(len(x.split()) for x in current)
        current.append(atom)
        current_words += atom_words
    if current:
        chunks.append(_make_chunk(len(chunks), current))
    return chunks


def _split_atoms(text: str, *, target_words: int) -> list[str]:
    """First by blank-line paragraphs; any oversized paragraph by
    sentences. Each atom is a string that goes into a chunk intact
    when it fits."""
    atoms: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        para = paragraph.strip()
        if not para:
            continue
        if len(para.split()) <= target_words:
            atoms.append(para)
            continue
        # Fallback — split oversized paragraph by sentence-ish.
        for sentence in _SENTENCE_RE.split(para):
            s = sentence.strip()
            if s:
                atoms.append(s)
    return atoms


def _tail_words(atoms: list[str], overlap_words: int) -> list[str]:
    """Return the smallest suffix of `atoms` whose combined word count
    meets `overlap_words`. Used to seed the next chunk."""
    if overlap_words <= 0:
        return []
    tail: list[str] = []
    words = 0
    for atom in reversed(atoms):
        tail.append(atom)
        words += len(atom.split())
        if words >= overlap_words:
            break
    tail.reverse()
    return tail


def _make_chunk(idx: int, atoms: list[str]) -> Chunk:
    content = "\n\n".join(atoms).strip()
    return Chunk(
        chunk_index=idx,
        content=content,
        metadata={"chunk_word_count": len(content.split())},
    )
