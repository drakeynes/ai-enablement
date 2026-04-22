"""HTML lesson file → clean text, using stdlib `html.parser`.

Filesystem-sourced content ingestion (pre-Drive). Per-file parser
produces a `ContentRecord` with:

  - `title`: `<h1>` text if present, else `<title>` tag, else filename
    stem.
  - `text`: tags stripped, paragraph/list/heading structure preserved
    as blank-line / newline boundaries. `<style>` and `<script>`
    blocks are dropped — their text content is CSS/JS, not lesson
    content.
  - `source_path`: the file that was parsed.

Kept to stdlib so we don't pull BeautifulSoup for 297 files of
well-formed HTML.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

# Block-level tags that should produce a hard break between their text
# content and the surrounding text. Paragraphs, headings, list items,
# divs, and anything else that in rendered HTML would introduce a line
# break. `br` is self-closing but gets the same treatment at the
# `handle_startendtag` / `handle_starttag` level.
_BLOCK_TAGS: frozenset[str] = frozenset({
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "div", "section", "article", "header", "footer", "main",
    "ul", "ol", "li",
    "tr", "td", "th", "table", "thead", "tbody",
    "br", "hr",
    "blockquote", "pre",
})
# Tags whose content is CSS / JavaScript, not prose. Skip entirely.
_SKIPPED_TAGS: frozenset[str] = frozenset({"style", "script", "noscript"})

# Collapse runs of whitespace into one space within a line. We keep
# newlines; the collapse is horizontal only.
_HORIZONTAL_WS_RE = re.compile(r"[ \t\f\v\r]+")
# Collapse 3+ newlines down to 2 (one blank line between paragraphs).
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class ContentRecord:
    """Structured view of one parsed HTML file."""

    title: str
    text: str
    source_path: Path
    raw_bytes_len: int


def parse_file(path: Path | str) -> ContentRecord:
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    record = parse_text(raw, source_path=path)
    return record


def parse_text(raw_html: str, *, source_path: Path) -> ContentRecord:
    extractor = _TextExtractor()
    extractor.feed(raw_html)
    extractor.close()

    text = _clean(extractor.text_buffer)
    title = extractor.h1 or extractor.title_tag or source_path.stem
    return ContentRecord(
        title=title.strip(),
        text=text,
        source_path=source_path,
        raw_bytes_len=len(raw_html.encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# HTMLParser subclass
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """Accumulates visible text with paragraph boundaries preserved."""

    def __init__(self):
        # `convert_charrefs=True` makes HTMLParser pre-decode &amp;
        # and friends. Saves us from threading html.unescape through.
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._in_h1 = False
        self._h1_buf: list[str] = []
        self._title_buf: list[str] = []
        self.h1: str | None = None
        self.title_tag: str | None = None
        self.text_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
        if tag in _BLOCK_TAGS and self._skip_depth == 0:
            self.text_buffer.append("\n")

    def handle_startendtag(self, tag: str, attrs):
        # Self-closing (<br/>, <hr/>) — same newline treatment as block open.
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            return
        if tag in _BLOCK_TAGS and self._skip_depth == 0:
            self.text_buffer.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in _SKIPPED_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title_tag = "".join(self._title_buf).strip()
        if tag == "h1" and self._in_h1:
            self._in_h1 = False
            if self.h1 is None:
                self.h1 = "".join(self._h1_buf).strip()
        if tag in _BLOCK_TAGS and self._skip_depth == 0:
            self.text_buffer.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth > 0:
            return
        if self._in_title:
            self._title_buf.append(data)
        if self._in_h1:
            self._h1_buf.append(data)
        self.text_buffer.append(data)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


def _clean(buf: list[str]) -> str:
    """Collapse whitespace while preserving paragraph breaks."""
    joined = "".join(buf)
    # Unescape any entities the parser didn't auto-convert (belt and
    # suspenders — convert_charrefs=True handles most).
    joined = html.unescape(joined)
    # Collapse horizontal whitespace, then collapse 3+ newlines → 2.
    lines = [_HORIZONTAL_WS_RE.sub(" ", line).strip() for line in joined.splitlines()]
    collapsed = "\n".join(lines)
    collapsed = _MULTI_NEWLINE_RE.sub("\n\n", collapsed)
    return collapsed.strip()
