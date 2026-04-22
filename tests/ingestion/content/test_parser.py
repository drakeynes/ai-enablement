"""Unit tests for ingestion.content.parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from ingestion.content import parser


def _p(raw: str) -> parser.ContentRecord:
    return parser.parse_text(raw, source_path=Path("/fake/lesson.html"))


# ---------------------------------------------------------------------------
# Happy-path structured HTML
# ---------------------------------------------------------------------------


def test_parse_headers_and_lists():
    raw = dedent("""\
        <!DOCTYPE html>
        <html>
        <head>
            <title>Some Page Title</title>
            <style>body { color: red; }</style>
        </head>
        <body>
            <h1>The Decision-Making Framework</h1>
            <p>Most decisions are two-way doors.</p>
            <h2>Type 1 decisions</h2>
            <ul>
                <li>Signing a long-term lease</li>
                <li>Taking on a 50/50 partner</li>
            </ul>
        </body>
        </html>
    """)
    record = _p(raw)
    assert record.title == "The Decision-Making Framework"
    assert "Most decisions are two-way doors." in record.text
    assert "Signing a long-term lease" in record.text
    assert "Taking on a 50/50 partner" in record.text
    # style block was dropped
    assert "color: red" not in record.text
    # paragraph break is preserved (blank line between h1 and p)
    assert "\n\n" in record.text


def test_parse_title_falls_back_to_title_tag_when_no_h1():
    raw = "<html><head><title>Fallback Title</title></head><body><p>Body only.</p></body></html>"
    record = _p(raw)
    assert record.title == "Fallback Title"
    assert "Body only." in record.text


def test_parse_title_falls_back_to_filename_when_no_h1_or_title():
    raw = "<html><body><p>Bare body</p></body></html>"
    record = parser.parse_text(raw, source_path=Path("/fake/my-lesson.html"))
    assert record.title == "my-lesson"


def test_parse_body_only_html_extracts_text():
    raw = "<p>Paragraph one.</p><p>Paragraph two.</p>"
    record = _p(raw)
    assert "Paragraph one." in record.text
    assert "Paragraph two." in record.text


def test_parse_html_entities_decoded():
    raw = "<html><body><p>A &amp; B &lt; C</p></body></html>"
    record = _p(raw)
    assert "A & B < C" in record.text


def test_parse_script_and_style_stripped():
    raw = dedent("""\
        <html><head>
          <style>.foo { display: none; }</style>
          <script>var secret = 'hidden';</script>
        </head><body>
          <p>Visible text.</p>
        </body></html>
    """)
    record = _p(raw)
    assert "Visible text." in record.text
    assert "display" not in record.text
    assert "secret" not in record.text


def test_parse_malformed_html_doesnt_crash():
    """HTMLParser's forgiving — unclosed tags don't raise. Ensure we
    get SOMETHING useful out of broken input."""
    raw = "<p>Start<h1>Header</p><div>End"
    record = _p(raw)
    # Text survives even without closing tags
    assert "Start" in record.text
    assert "Header" in record.text
    assert "End" in record.text


def test_parse_empty_html_returns_empty_text():
    record = _p("")
    assert record.text == ""


def test_parse_whitespace_only_html_returns_empty_text():
    record = _p("   \n\n  \t  ")
    assert record.text == ""


def test_parse_preserves_h1_via_buffer_when_nested_content():
    """If <h1> has inline tags, their text content is part of the title."""
    raw = "<html><body><h1>The <em>Decision</em> Framework</h1></body></html>"
    record = _p(raw)
    assert record.title == "The Decision Framework"


def test_parse_file_reads_from_disk(tmp_path):
    path = tmp_path / "lesson.html"
    path.write_text("<html><body><h1>Hello</h1><p>World.</p></body></html>", encoding="utf-8")
    record = parser.parse_file(path)
    assert record.title == "Hello"
    assert "World." in record.text
    assert record.source_path == path
