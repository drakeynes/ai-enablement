"""Convert standard Markdown to Slack mrkdwn for `chat.postMessage`.

Slack's `text` field expects a Slack-flavored markup that's similar to
Markdown but differs in load-bearing ways:

  Standard Markdown    Slack mrkdwn
  -----------------    ------------
  **bold**             *bold*
  __bold__             *bold*
  *italic*             _italic_
  [text](url)          <url|text>
  # / ## / ### Header  *Header*       (Slack has no header concept)

The pieces that don't differ:

  `inline code`        `inline code`
  ```fenced```         ```fenced```
  - bullet              - bullet      (rendered as a bullet either way)
  1. ordered            1. ordered    (Slack: rendered as plain text)
  > quote              > quote
  bare URLs            (Slack auto-links them)

Why this lives in shared/ and not agents/ella/: future agents (CSM
Co-Pilot, Internal Scout) all post to Slack and need the same conversion.
Single source of truth.

Why this exists at all (vs prompting Claude to use mrkdwn directly):
the prompt does ask for mrkdwn, but model output isn't perfectly
deterministic — a single `**bold**` slipping through renders as literal
asterisks to the user. The converter is the safety net. Belt-and-
suspenders is the right shape for a user-visible rendering bug.

Design rules:
  - **Pass through unknown patterns.** Horizontal rules, numbered lists,
    blockquotes, tables — Slack renders most as plain text near-correctly.
    Over-transforming is worse than under-transforming.
  - **Protect code spans first.** Asterisks inside `inline code` and
    ```fenced blocks``` stay literal — Slack renders them in monospace
    and would otherwise collide with our bold/italic transforms.
  - **Bold before italic, with placeholders.** Naive regex chaining of
    `**bold**` → `*bold*` followed by `*italic*` → `_italic_` would
    re-process the bold result and mangle. The bold step writes its
    output to placeholder tokens; the italic step can't see them; the
    placeholders are restored at the end.
"""

from __future__ import annotations

import re

# Sentinel chars unlikely to appear in any real Claude output. Used to
# stash protected substrings (code spans, completed bold transforms)
# during the multi-step regex pass and restore at the end.
_CODE_SENTINEL_PREFIX = "\x00CODE"
_BOLD_SENTINEL_PREFIX = "\x00BOLD"
_SENTINEL_SUFFIX = "\x00"

# Fenced code blocks `````...``````, multiline, non-greedy.
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
# Inline code `...`, non-greedy, single-line. Disallow newlines so a
# single stray backtick doesn't swallow the rest of the message.
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# **bold** — at least one non-`*` char inside, non-greedy. Multi-line
# bold (across `\n`) intentionally NOT matched: Slack doesn't render
# multi-line bold either, so leaving the pattern alone makes Claude's
# output look identically broken in both formats (which is correct
# behavior — better than silently dropping the markers).
_DOUBLE_STAR_BOLD_RE = re.compile(r"\*\*([^*\n][^*\n]*?)\*\*")

# __bold__ — alt Markdown bold syntax. Some prompts produce this.
_DOUBLE_UNDERSCORE_BOLD_RE = re.compile(r"__([^_\n][^_\n]*?)__")

# *italic* — single asterisks, NOT part of a leftover `**` pair. The
# bold step has already consumed all valid `**...**` pairs into
# placeholders, so any remaining `*...*` is meant to be italic.
# Negative lookbehind/lookahead on `*` excludes accidental triples.
_SINGLE_STAR_ITALIC_RE = re.compile(r"(?<![*\\])\*([^*\n]+)\*(?!\*)")

# [text](url) — Markdown link. URL captured as non-whitespace so an
# optional title in quotes (`[t](url "title")`) is dropped — Slack's
# `<url|text>` syntax doesn't carry titles, and Claude's title would
# render as part of the URL otherwise.
_LINK_RE = re.compile(r"\[([^\]]+)\]\((\S+?)(?:\s+\"[^\"]*\")?\)")

# Line-anchored Markdown headers. `# `, `## `, `### ` etc. Slack has
# no header concept; bold approximates emphasis.
_HEADER_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def markdown_to_mrkdwn(text: str) -> str:
    """Convert standard Markdown to Slack mrkdwn.

    Empty / falsy input returns as-is. Idempotent on already-mrkdwn input
    in the common case (a `*bold*` Slack mrkdwn isn't matched by the
    `**bold**` regex; `_italic_` already-Slack stays untouched).

    Returns the converted text. Does not raise.
    """
    if not text:
        return text

    code_stash: list[str] = []
    bold_stash: list[str] = []

    # Step 1: protect code spans. Fenced first (greedier match), then
    # inline. Order matters because a fenced block could legitimately
    # contain triple-backtick-adjacent backticks that the inline regex
    # would otherwise mis-anchor on.
    text = _FENCED_CODE_RE.sub(lambda m: _stash(code_stash, m.group(0), _CODE_SENTINEL_PREFIX), text)
    text = _INLINE_CODE_RE.sub(lambda m: _stash(code_stash, m.group(0), _CODE_SENTINEL_PREFIX), text)

    # Step 2a: bold (both Markdown forms). Stash the converted result so
    # the italic step can't re-process the inner content.
    text = _DOUBLE_STAR_BOLD_RE.sub(
        lambda m: _stash(bold_stash, f"*{m.group(1)}*", _BOLD_SENTINEL_PREFIX), text
    )
    text = _DOUBLE_UNDERSCORE_BOLD_RE.sub(
        lambda m: _stash(bold_stash, f"*{m.group(1)}*", _BOLD_SENTINEL_PREFIX), text
    )

    # Step 2b: italic. With bold safely behind sentinels, any remaining
    # `*...*` is unambiguous italic.
    text = _SINGLE_STAR_ITALIC_RE.sub(r"_\1_", text)

    # Step 2c: links — [text](url) -> <url|text>.
    text = _LINK_RE.sub(r"<\2|\1>", text)

    # Step 2d: headers. Slack has no header concept — render as bold so
    # the visual emphasis survives the transition.
    text = _HEADER_RE.sub(r"*\1*", text)

    # Step 3: restore bold placeholders, then code placeholders. Bold
    # restored first because a code span content might itself contain
    # the bold sentinel pattern (vanishingly unlikely with NUL prefix
    # but cheap to defend against by ordering).
    for idx, value in enumerate(bold_stash):
        text = text.replace(f"{_BOLD_SENTINEL_PREFIX}{idx}{_SENTINEL_SUFFIX}", value)
    for idx, value in enumerate(code_stash):
        text = text.replace(f"{_CODE_SENTINEL_PREFIX}{idx}{_SENTINEL_SUFFIX}", value)

    return text


def _stash(bucket: list[str], value: str, prefix: str) -> str:
    """Append `value` to `bucket` and return its placeholder token."""
    idx = len(bucket)
    bucket.append(value)
    return f"{prefix}{idx}{_SENTINEL_SUFFIX}"
