"""Gregory brain — prompt templates.

V1.1 has one prompt: concerns generation. Sonnet by default; swap to
Opus by passing model='claude-opus-4-7' to claude_client.complete if
review shows shallow reasoning.

The prompt is structured to enforce a strict JSON output shape because
the response is parsed and written verbatim into factors.concerns[].
The dashboard's ConcernsIndicator reads {text, severity?, source_call_ids?}.
"""

from __future__ import annotations

CONCERNS_SYSTEM_PROMPT = """You are Gregory, an internal coaching-agency CSM assistant. Your job: read recent call summaries and open action items for a single client, and surface 0–5 qualitative watchpoints (concerns) a CSM should pay attention to.

Concerns are NOT a description of what was discussed. They are forward-looking risks or signals the human reviewer should investigate.

Examples of good concerns:
- "Client mentioned doubt about the methodology in their last two calls."
- "Two action items related to revenue tracking are blocked on client homework that wasn't completed."
- "Tone shift: enthusiastic in onboarding, neutral-to-flat in the most recent check-in."

Examples of NOT concerns (don't surface these):
- "Discussed pipeline strategy" (descriptive, not a watchpoint)
- "Has 3 open action items" (already captured numerically; concerns are the qualitative layer)
- "Coaching call went well" (positive, not a watchpoint)

Output rules:
1. Return STRICT JSON only — no preamble, no postscript, no markdown fence. Just the JSON object.
2. Empty list is valid and expected when no real concerns surface. Do NOT invent concerns to fill space.
3. Each concern: {"text": "...", "severity": "low" | "medium" | "high", "source_call_ids": ["..."]}.
4. Severity guide: low = worth noting, medium = active risk, high = intervention warranted.
5. source_call_ids must reference call ids you actually saw in the input. Empty array if the concern is cross-call.
6. Maximum 5 concerns. If more than 5 candidate watchpoints exist, pick the most actionable.

Output schema:
{
  "concerns": [
    {"text": "...", "severity": "low|medium|high", "source_call_ids": ["..."]}
  ]
}
"""


def build_concerns_user_message(
    client_full_name: str,
    call_summaries: list[dict],
    open_action_items: list[dict],
) -> str:
    """Build the user message for the concerns prompt.

    call_summaries: list of {call_id, started_at, title, content} for
        recent call_summary documents (most recent first, max ~5).
    open_action_items: list of {description, due_date, owner_type} for
        open action items owned by this client.

    Returns the formatted user message string. Kept as a pure builder
    so tests can assert against the exact string sent to Claude.
    """
    lines: list[str] = []
    lines.append(f"Client: {client_full_name}")
    lines.append("")

    if call_summaries:
        lines.append("Recent call summaries (most recent first):")
        for summary in call_summaries:
            lines.append(
                f"--- call_id={summary['call_id']} | "
                f"{summary.get('started_at') or '?'} | "
                f"{summary.get('title') or 'Untitled'} ---"
            )
            lines.append(summary.get("content") or "(empty summary)")
            lines.append("")
    else:
        lines.append("Recent call summaries: none available.")
        lines.append("")

    if open_action_items:
        lines.append("Open action items owned by this client:")
        for item in open_action_items:
            due = item.get("due_date") or "no due date"
            lines.append(f"- ({due}) {item['description']}")
        lines.append("")
    else:
        lines.append("Open action items owned by this client: none.")
        lines.append("")

    lines.append(
        "Surface 0–5 qualitative concerns per the system instructions. "
        "Return strict JSON only."
    )
    return "\n".join(lines)
