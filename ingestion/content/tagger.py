"""Derive tags from a lesson file's path relative to `data/course_content/`.

Path conventions:

  - `FOUNDATION MODULE/lesson_1.html`
      → ['module_foundation', 'v1_content']
  - `TRAFFIC ACQUISITION MODULE/COLD CALLING/lesson_3.html`
      → ['module_traffic_acquisition', 'section_cold_calling', 'v1_content']
  - `CLIENT SUCCESS & RETENTION MODULE/lesson.html`
      → ['module_client_success_retention', 'v1_content']

Normalization rules:
  - Lowercase everything.
  - Replace non-alphanumeric with spaces (so `&`, `-`, `&amp;` etc.
    collapse into word boundaries).
  - Strip the standalone word `module` — it's noise in the tag form.
  - Collapse runs of whitespace, replace with `_`.

`v1_content` is always included. When content gets a v2 pass (Drive
sync, or a curator's refresh), the v1 rows get soft-archived with
their `v1_content` tag intact — `inspect_ingestion.md` query #7
surfaces that delta for cleanup.
"""

from __future__ import annotations

import re
from pathlib import Path

_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)
_MULTI_WS_RE = re.compile(r"\s+")
_VERSION_TAG = "v1_content"


def tags_for_path(relative_path: Path | str) -> list[str]:
    """Return the tag list for a file path relative to the content root.

    Input `relative_path` should NOT include `data/course_content/` —
    it starts at the module-name directory level.
    """
    p = Path(relative_path)
    parts = p.parts
    # Last part is the filename — not part of the module/section chain.
    directory_parts = parts[:-1]
    if not directory_parts:
        # File directly under data/course_content/ — only the version tag.
        return [_VERSION_TAG]

    tags: list[str] = []
    module_part = directory_parts[0]
    module_slug = _normalize(module_part)
    if module_slug:
        tags.append(f"module_{module_slug}")

    # Any directory level between the module and the filename becomes a
    # section tag. The user's examples only nest one level deep; this
    # tolerates deeper nesting by flattening each level into its own tag.
    for section_part in directory_parts[1:]:
        section_slug = _normalize(section_part)
        if section_slug:
            tags.append(f"section_{section_slug}")

    tags.append(_VERSION_TAG)
    return tags


def _normalize(value: str) -> str:
    """Lowercase, drop non-word chars, strip 'module' noise, underscores."""
    lowered = value.lower()
    # Replace non-word chars with spaces so `client success & retention`
    # becomes `client success   retention`, then collapse.
    spaced = _NON_WORD_RE.sub(" ", lowered)
    collapsed = _MULTI_WS_RE.sub(" ", spaced).strip()
    # Strip the standalone word `module` — leaves meaningful content.
    words = [w for w in collapsed.split(" ") if w != "module"]
    return "_".join(words)
