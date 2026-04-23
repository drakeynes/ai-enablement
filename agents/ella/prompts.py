"""System prompt construction for Ella.

**STUB.** The real system prompt text is being drafted collaboratively
(see `docs/agents/ella-v1-scope.md` for the V1 behavior the prompt
needs to encode — in-scope / escalate / decline categories, hedging on
transcript quotes, anti-injection).

This module exists now so the agent skeleton can import from it and
the tests can verify the wiring. When the prompt lands, only this
file changes — `agents/ella/agent.py` keeps calling
`build_system_prompt(client, context)` and the plumbing stays the same.
"""

from __future__ import annotations

from typing import Any


def build_system_prompt(
    client: dict[str, Any],
    primary_csm: dict[str, Any] | None = None,
) -> str:
    """Return the system prompt for Ella given current client context.

    Stub implementation returns a placeholder string that's clearly
    marked as non-production — if this ever reaches Claude in a live
    run, the output will be nonsense and someone will notice fast.
    """
    client_name = client.get("full_name") or "(unknown client)"
    csm_name = (primary_csm or {}).get("full_name") or "(unassigned)"
    return (
        "[ELLA PROMPT STUB — replace via agents/ella/prompts.py]\n"
        f"Client: {client_name}\n"
        f"Primary CSM: {csm_name}\n"
    )
