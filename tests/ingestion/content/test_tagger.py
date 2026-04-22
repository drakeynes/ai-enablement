"""Unit tests for ingestion.content.tagger."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.content import tagger


@pytest.mark.parametrize(
    "relative_path,expected",
    [
        # Flat folder — the two examples from the spec
        ("FOUNDATION MODULE/lesson_1.html",
         ["module_foundation", "v1_content"]),
        ("TRAFFIC ACQUISITION MODULE/COLD CALLING/lesson_3.html",
         ["module_traffic_acquisition", "section_cold_calling", "v1_content"]),

        # "MODULE" stripping
        ("BUSINESS LAUNCH MODULE/01.html",
         ["module_business_launch", "v1_content"]),

        # Special characters dropped (e.g. `&`)
        ("CLIENT SUCCESS & RETENTION MODULE/lesson.html",
         ["module_client_success_retention", "v1_content"]),

        # Deeper nesting — every subdirectory beyond module becomes a section
        ("SALES PROCESS MODULE/Section One/Subsection/leaf.html",
         ["module_sales_process", "section_section_one", "section_subsection", "v1_content"]),

        # Lowercased and spaces → underscores
        ("Market Selection Module/Format Examples/x.html",
         ["module_market_selection", "section_format_examples", "v1_content"]),

        # File directly at the root of content_dir — only version tag
        ("top_level_file.html",
         ["v1_content"]),
    ],
)
def test_tags_for_path(relative_path, expected):
    assert tagger.tags_for_path(relative_path) == expected


def test_normalize_collapses_multiple_spaces():
    assert tagger._normalize("Client    Success  &  Retention MODULE") == "client_success_retention"


def test_normalize_strips_module_only_as_standalone_word():
    """The word 'module' inside another word shouldn't get stripped."""
    assert tagger._normalize("modular_thinking") == "modular_thinking"


def test_tags_for_path_accepts_path_objects():
    path = Path("FOUNDATION MODULE/lesson.html")
    assert tagger.tags_for_path(path) == ["module_foundation", "v1_content"]
