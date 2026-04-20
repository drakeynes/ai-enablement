"""Supabase client setup.

Single source of truth for reaching our database. Every other module in
`shared/` — logging, kb_query, hitl — goes through `get_client()` so
there is exactly one place to swap credentials, add connection pooling,
or wire in a different client library.

Example:

    from shared.db import get_client

    client = get_client()
    client.table("clients").select("*").limit(5).execute()
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOCAL = _REPO_ROOT / ".env.local"
if _ENV_LOCAL.exists():
    load_dotenv(_ENV_LOCAL)


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return a Supabase client configured from env vars.

    Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. The service role
    key bypasses RLS, which is what agent code needs; never surface this
    client to the browser.

    The result is cached for the process lifetime. Call
    `get_client.cache_clear()` to force a rebuild (tests do this).

    Raises:
        RuntimeError: if either env var is unset or empty.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", url),
                ("SUPABASE_SERVICE_ROLE_KEY", key),
            )
            if not value
        ]
        raise RuntimeError(
            f"Supabase env vars missing: {', '.join(missing)}. "
            "Copy .env.example to .env.local and fill them in."
        )
    return create_client(url, key)
