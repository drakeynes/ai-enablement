"""Local test loop for api/accountability_roster.py.

Stands up the real `handler` class in a background thread via
http.server.HTTPServer (same class Vercel instantiates in prod). Runs
6 paths, checks HTTP response shape + cross-references one known-good
client via direct psycopg2. Mirrors scripts/test_airtable_nps_webhook_locally.py.

This endpoint is read-only — there is no DB cleanup needed and no
test client is mutated. The harness reads the live cloud roster and
prints the actionable count for Drake to eyeball against expectations.

Uses a TEST webhook secret (NOT production). Sets the secret itself
if MAKE_OUTBOUND_ROSTER_SECRET is unset, so you can just run:

    .venv/bin/python scripts/test_accountability_roster_locally.py

Reads SUPABASE_DB_PASSWORD from .env.local for direct psycopg2 DB
verification (bypasses PostgREST quirks per the Path 1 harness pattern).
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Set the test secret BEFORE importing the handler so the env var is
# present at first os.environ.get() call. We deliberately do NOT use
# the production secret even if .env.local has it — local harness
# should not depend on prod credentials being readable.
_TEST_SECRET = "test_secret_" + secrets.token_urlsafe(32)
os.environ["MAKE_OUTBOUND_ROSTER_SECRET"] = _TEST_SECRET
_RESOLVED_SECRET = os.environ["MAKE_OUTBOUND_ROSTER_SECRET"]

from api.accountability_roster import handler  # noqa: E402 — env-first


def _pg_conn():
    """Direct psycopg2 connection — same pattern as the Path 1 harness.
    Bypasses PostgREST's occasional empty-body 400 on count queries."""
    import psycopg2
    from urllib.parse import quote
    from dotenv import load_dotenv

    load_dotenv(".env.local")
    with open(_REPO / "supabase/.temp/pooler-url") as f:
        pooler = f.read().strip()
    pw = os.environ["SUPABASE_DB_PASSWORD"]
    at = pooler.index("@")
    dsn = f"{pooler[:at]}:{quote(pw, safe='')}{pooler[at:]}"
    return psycopg2.connect(dsn, connect_timeout=15)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


_server: HTTPServer | None = None
_server_thread: threading.Thread | None = None
_PORT = 0


def _start_server() -> str:
    """Start the receiver in a background thread. Returns the base URL."""
    global _server, _server_thread, _PORT
    _server = HTTPServer(("127.0.0.1", 0), handler)
    _PORT = _server.server_port
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    time.sleep(0.1)  # give it a tick to bind
    return f"http://127.0.0.1:{_PORT}/api/accountability_roster"


def _stop_server() -> None:
    if _server is not None:
        _server.shutdown()
        _server.server_close()


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def _request(
    url: str,
    method: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict | None, str | None]:
    """Issue an HTTP request, return (status, parsed_json_or_None, raw_text).
    raw_text is set when the body is non-JSON or empty."""
    req_headers = dict(headers or {})
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else None, raw
            except json.JSONDecodeError:
                return resp.status, None, raw
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            raw = ""
        try:
            return exc.code, json.loads(raw) if raw else None, raw
        except json.JSONDecodeError:
            return exc.code, None, raw


def _get_with_secret(
    url: str, secret: str = _RESOLVED_SECRET
) -> tuple[int, dict | None, str | None]:
    return _request(url, "GET", {"X-Webhook-Secret": secret})


# ---------------------------------------------------------------------------
# DB-state helpers
# ---------------------------------------------------------------------------


def _spot_check_client() -> dict | None:
    """Pick one known-good client (active, has slack_user_id, has at
    least one non-archived slack_channels row) and return their email +
    expected slack_channel_id. The harness will assert that this client
    appears in the response with the matching channel id.

    We pick deterministically: the alphabetically-first qualifying
    client by full_name. Stable across reruns."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.email, c.full_name,
                   (
                     SELECT sc.slack_channel_id
                     FROM slack_channels sc
                     WHERE sc.client_id = c.id
                       AND sc.is_archived = false
                     ORDER BY sc.created_at DESC
                     LIMIT 1
                   ) AS expected_channel_id
            FROM clients c
            WHERE c.archived_at IS NULL
              AND c.slack_user_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM slack_channels sc2
                WHERE sc2.client_id = c.id AND sc2.is_archived = false
              )
            ORDER BY c.full_name
            LIMIT 1;
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "email": row[0],
            "full_name": row[1],
            "expected_channel_id": row[2],
        }
    finally:
        conn.close()


def _expected_actionable_count() -> int:
    """Compute the expected actionable count via direct SQL — same
    eligibility rules the handler enforces. Used to assert the response
    count matches what the handler should be returning."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*)
            FROM clients c
            WHERE c.archived_at IS NULL
              AND c.slack_user_id IS NOT NULL
              AND c.email IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM slack_channels sc
                WHERE sc.client_id = c.id AND sc.is_archived = false
              );
            """
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _total_non_archived_count() -> int:
    """Total non-archived clients — surfaces the filter-out delta."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM clients WHERE archived_at IS NULL;")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, condition: bool, detail: str) -> None:
    _RESULTS.append((name, condition, detail))
    marker = "✅" if condition else "❌"
    print(f"  {marker} {name}: {detail}")


def test_1_happy_path(url: str) -> dict | None:
    print("\n[1] GET with valid secret → 200, sane payload shape")
    status, body, raw = _get_with_secret(url)
    _check("1.status", status == 200, f"got HTTP {status}")
    if body is None:
        _check("1.body", False, f"non-JSON body: {raw[:200] if raw else 'empty'}")
        return None

    # Top-level shape
    _check(
        "1.has_keys",
        set(body.keys()) == {"generated_at", "count", "clients"},
        f"keys={sorted(body.keys())}",
    )
    _check(
        "1.generated_at_iso",
        isinstance(body.get("generated_at"), str)
        and body["generated_at"].endswith("+00:00"),
        f"generated_at={body.get('generated_at')!r}",
    )
    clients = body.get("clients") or []
    _check(
        "1.count_matches",
        body.get("count") == len(clients),
        f"count={body.get('count')} clients_len={len(clients)}",
    )
    _check("1.count_positive", len(clients) > 0, f"got {len(clients)} actionable rows")

    # Per-row shape — verify on the first row only.
    if clients:
        first = clients[0]
        expected_keys = {
            "client_email",
            "full_name",
            "country",
            "advisor_first_name",
            "slack_user_id",
            "slack_channel_id",
            "accountability_enabled",
            "nps_enabled",
        }
        _check(
            "1.row_keys",
            set(first.keys()) == expected_keys,
            f"row[0] keys={sorted(first.keys())}",
        )
        _check(
            "1.row_email_str",
            isinstance(first.get("client_email"), str) and first["client_email"],
            f"client_email={first.get('client_email')!r}",
        )
        _check(
            "1.row_full_name_str",
            isinstance(first.get("full_name"), str) and first["full_name"],
            f"full_name={first.get('full_name')!r}",
        )
        country_v = first.get("country")
        _check(
            "1.row_country_str_or_null",
            country_v is None or (isinstance(country_v, str) and len(country_v) > 0),
            f"country={country_v!r}",
        )
        advisor_v = first.get("advisor_first_name")
        _check(
            "1.row_advisor_str_or_null",
            advisor_v is None or (isinstance(advisor_v, str) and len(advisor_v) > 0),
            f"advisor_first_name={advisor_v!r}",
        )
        if isinstance(advisor_v, str):
            # Single whitespace-separated token, leading capital. Internal
            # caps and hyphens preserved per the receiver's spec (only the
            # leading char is forced uppercase via .capitalize() — but
            # .capitalize() also lowercases the rest of a single token,
            # which is fine for current CSMs and acknowledged in the
            # receiver docstring).
            _check(
                "1.row_advisor_single_token",
                len(advisor_v.split()) == 1,
                f"advisor_first_name={advisor_v!r}",
            )
            _check(
                "1.row_advisor_leading_cap",
                advisor_v[0].isupper(),
                f"advisor_first_name={advisor_v!r}",
            )
        _check(
            "1.row_slack_user_id_str",
            isinstance(first.get("slack_user_id"), str)
            and first["slack_user_id"].startswith("U"),
            f"slack_user_id={first.get('slack_user_id')!r}",
        )
        _check(
            "1.row_slack_channel_id_str",
            isinstance(first.get("slack_channel_id"), str)
            and first["slack_channel_id"].startswith("C"),
            f"slack_channel_id={first.get('slack_channel_id')!r}",
        )
        _check(
            "1.row_accountability_bool",
            isinstance(first.get("accountability_enabled"), bool),
            f"accountability_enabled={first.get('accountability_enabled')!r}",
        )
        _check(
            "1.row_nps_bool",
            isinstance(first.get("nps_enabled"), bool),
            f"nps_enabled={first.get('nps_enabled')!r}",
        )

    return body


def test_2_count_matches_db(body: dict | None) -> None:
    print("\n[2] Response count matches direct-SQL expected actionable count")
    if body is None:
        _check("2.skipped", False, "no body from test 1")
        return
    expected = _expected_actionable_count()
    total = _total_non_archived_count()
    actual = body.get("count", 0)
    _check(
        "2.count_eq_db",
        actual == expected,
        f"response count={actual}, db expected={expected}, total non-archived={total}",
    )
    print(
        f"     INFO: filtered out {total - expected} of {total} non-archived clients (NULL slack_user_id or no resolvable channel or no email)"
    )


def test_3_spot_check_known_client(body: dict | None) -> None:
    print("\n[3] One known-good client appears with matching slack_channel_id")
    if body is None:
        _check("3.skipped", False, "no body from test 1")
        return
    spot = _spot_check_client()
    if spot is None:
        _check(
            "3.skipped",
            False,
            "no spot-check client found (db has no qualifying client?)",
        )
        return
    print(f"     spot client: {spot['full_name']} <{spot['email']}>")
    print(f"     expected slack_channel_id: {spot['expected_channel_id']}")
    matched = next(
        (
            c
            for c in body.get("clients") or []
            if c.get("client_email") == spot["email"]
        ),
        None,
    )
    _check(
        "3.in_response", matched is not None, f"found in response={matched is not None}"
    )
    if matched is not None:
        _check(
            "3.channel_matches",
            matched.get("slack_channel_id") == spot["expected_channel_id"],
            f"response channel={matched.get('slack_channel_id')}, expected={spot['expected_channel_id']}",
        )


def test_4_missing_secret(url: str) -> None:
    print("\n[4] GET with no X-Webhook-Secret header → 401, no body")
    status, body, raw = _request(url, "GET")
    _check("4.status", status == 401, f"got HTTP {status}")
    _check("4.empty_body", not raw, f"raw body={raw!r}")


def test_5_wrong_secret(url: str) -> None:
    print("\n[5] GET with wrong X-Webhook-Secret → 401, no body")
    status, body, raw = _get_with_secret(url, secret="not_the_real_secret_definitely")
    _check("5.status", status == 401, f"got HTTP {status}")
    _check("5.empty_body", not raw, f"raw body={raw!r}")


def test_6_post_method(url: str) -> None:
    print("\n[6] POST with valid secret → 405 method_not_allowed")
    status, body, raw = _request(
        url,
        "POST",
        {"X-Webhook-Secret": _RESOLVED_SECRET, "Content-Type": "application/json"},
        body=b"{}",
    )
    _check("6.status", status == 405, f"got HTTP {status}")
    _check(
        "6.error",
        body and body.get("error") == "method_not_allowed",
        f"body={body!r}",
    )


def test_7_missing_env_var(url: str) -> None:
    """Restart-style test: clear MAKE_OUTBOUND_ROSTER_SECRET, fire a
    request, expect 500 (server_misconfigured). Restore afterward.

    The handler reads os.environ.get on every request (no cached
    secret), so we don't need to actually restart the HTTPServer — just
    delete the env var, fire one request, restore."""
    print("\n[7] Missing MAKE_OUTBOUND_ROSTER_SECRET env var → 500")
    saved = os.environ.pop("MAKE_OUTBOUND_ROSTER_SECRET", None)
    try:
        status, body, raw = _request(url, "GET")
        _check("7.status", status == 500, f"got HTTP {status}")
        _check(
            "7.error",
            body and body.get("error") == "server_misconfigured",
            f"body={body!r}",
        )
    finally:
        if saved is not None:
            os.environ["MAKE_OUTBOUND_ROSTER_SECRET"] = saved


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 72)
    print("Accountability roster endpoint — local test harness")
    print(f"Test secret: {_RESOLVED_SECRET[:24]}... (truncated)")
    print("=" * 72)

    url = _start_server()
    print(f"Endpoint listening at {url}")

    try:
        body = test_1_happy_path(url)
        test_2_count_matches_db(body)
        test_3_spot_check_known_client(body)
        test_4_missing_secret(url)
        test_5_wrong_secret(url)
        test_6_post_method(url)
        test_7_missing_env_var(url)
    except Exception:
        traceback.print_exc()
        return 2
    finally:
        _stop_server()

    print("\n" + "=" * 72)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print(f"Results: {passed}/{total} checks passed")
    failures = [name for name, ok, _ in _RESULTS if not ok]
    if failures:
        print(f"Failed: {failures}")
        return 1
    print("All checks green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
