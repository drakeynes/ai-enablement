"""Local test loop for api/airtable_nps_webhook.py.

Stands up the real `handler` class in a background thread via
http.server.HTTPServer (same class Vercel instantiates in prod). Runs
8 paths (2 happy + 6 negative), checks HTTP response + cloud DB state
for each, cleans up the test client's nps_standing + csm_standing in
try/finally. Mirrors scripts/test_fathom_webhook_locally.py.

Test client: Branden Bledsoe (brandenbledsoe@transcendcu.com) — active,
csm_standing NULL, no client_standing_history rows pre-test. After
this run the client will have N standing_history rows attributable to
Gregory Bot (intentional — clearing csm_standing back to NULL doesn't
delete history per the 0018 RPC contract). Branden was selected per
M5.4 receiver chunk: low-profile, not on Drake/Scott's watchlist.

Uses a TEST webhook secret (NOT production). Sets the secret itself
if AIRTABLE_NPS_WEBHOOK_SECRET is unset, so you can just run:

    .venv/bin/python scripts/test_airtable_nps_webhook_locally.py

Reads SUPABASE_DB_PASSWORD from .env.local for direct psycopg2 DB
verification (bypasses PostgREST quirks per the Fathom harness pattern).
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
# present at first os.environ.get() call.
_TEST_SECRET = "test_secret_" + secrets.token_urlsafe(32)
os.environ.setdefault("AIRTABLE_NPS_WEBHOOK_SECRET", _TEST_SECRET)
_RESOLVED_SECRET = os.environ["AIRTABLE_NPS_WEBHOOK_SECRET"]

from api.airtable_nps_webhook import handler  # noqa: E402 — env-first
from shared.db import get_client  # noqa: E402


# Test client — see module docstring for selection criteria.
TEST_CLIENT_EMAIL = "brandenbledsoe@transcendcu.com"


def _pg_conn():
    """Direct psycopg2 connection — same pattern as the Fathom harness.
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
_PORT = 0  # filled when the server binds


def _start_server() -> str:
    """Start the receiver in a background thread. Returns the base URL."""
    global _server, _server_thread, _PORT
    _server = HTTPServer(("127.0.0.1", 0), handler)
    _PORT = _server.server_port
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    time.sleep(0.1)  # give it a tick to bind
    return f"http://127.0.0.1:{_PORT}/api/airtable_nps_webhook"


def _stop_server() -> None:
    if _server is not None:
        _server.shutdown()
        _server.server_close()


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def _post(
    url: str,
    body: bytes | str,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict | None]:
    """POST to url, return (status_code, parsed_json_or_None)."""
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(
        url, data=body_bytes, headers=req_headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _post_with_secret(
    url: str, payload: dict, secret: str = _RESOLVED_SECRET
) -> tuple[int, dict | None]:
    return _post(
        url,
        json.dumps(payload),
        {"X-Webhook-Secret": secret},
    )


# ---------------------------------------------------------------------------
# DB-state helpers
# ---------------------------------------------------------------------------


def _client_state(email: str) -> dict:
    """Return current nps_standing + csm_standing for the test client."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nps_standing, csm_standing FROM clients
            WHERE lower(trim(email)) = lower(trim(%s))
              AND archived_at IS NULL
            LIMIT 1;
            """,
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return {"id": None, "nps_standing": None, "csm_standing": None}
        return {
            "id": row[0],
            "nps_standing": row[1],
            "csm_standing": row[2],
        }
    finally:
        conn.close()


def _latest_history_changed_by(client_id: str) -> str | None:
    """Return changed_by UUID on the most recent standing_history row,
    or None if no history rows."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT changed_by FROM client_standing_history
            WHERE client_id = %s
            ORDER BY changed_at DESC LIMIT 1;
            """,
            (client_id,),
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()


def _delivery_status(delivery_id: str) -> dict | None:
    """Return webhook_deliveries row for a given delivery_id, or None."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT webhook_id, source, processing_status, processing_error,
                   call_external_id
            FROM webhook_deliveries WHERE webhook_id = %s;
            """,
            (delivery_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "webhook_id": row[0],
            "source": row[1],
            "processing_status": row[2],
            "processing_error": row[3],
            "call_external_id": row[4],
        }
    finally:
        conn.close()


def _count_deliveries_with_source(source: str, since_ts: float) -> int:
    """Count rows in webhook_deliveries matching source, received after
    a wall-clock timestamp (in epoch seconds)."""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        from datetime import datetime, timezone
        since_iso = datetime.fromtimestamp(since_ts, timezone.utc).isoformat()
        cur.execute(
            """
            SELECT count(*) FROM webhook_deliveries
            WHERE source = %s AND received_at >= %s;
            """,
            (source, since_iso),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def _reset_test_client() -> None:
    """Clear nps_standing + csm_standing on the test client. History rows
    are intentionally NOT deleted (matches the 0018 RPC contract on
    null-clear: history table preserves the record of past values)."""
    state = _client_state(TEST_CLIENT_EMAIL)
    if state["id"] is None:
        return
    db = get_client()
    db.table("clients").update({"nps_standing": None}).eq(
        "id", state["id"]
    ).execute()
    if state["csm_standing"] is not None:
        db.rpc(
            "update_client_csm_standing_with_history",
            {
                "p_client_id": state["id"],
                "p_new_csm_standing": None,
                "p_changed_by": None,
                "p_note": "test_airtable_nps_webhook_locally cleanup",
            },
        ).execute()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, condition: bool, detail: str) -> None:
    _RESULTS.append((name, condition, detail))
    marker = "✅" if condition else "❌"
    print(f"  {marker} {name}: {detail}")


def test_1_promoter_happy_path(url: str) -> None:
    print("\n[1] Valid payload, segment='Strong / Promoter' → 200, auto-derive=true")
    _reset_test_client()  # ensure clean starting state
    pre = _client_state(TEST_CLIENT_EMAIL)
    _check("1.pre", pre["csm_standing"] is None, f"pre csm_standing={pre['csm_standing']}")

    status, body = _post_with_secret(
        url,
        {
            "client_email": TEST_CLIENT_EMAIL,
            "segment": "Strong / Promoter",
            "airtable_record_id": "rec_test_1_promoter",
        },
    )
    _check("1.status", status == 200, f"got HTTP {status}, body={body}")
    if not body:
        return
    _check("1.nps_standing", body.get("nps_standing") == "promoter", f"got {body.get('nps_standing')!r}")
    _check("1.csm_standing", body.get("csm_standing") == "happy", f"got {body.get('csm_standing')!r}")
    _check("1.auto_derive", body.get("auto_derive_applied") is True, f"got {body.get('auto_derive_applied')!r}")

    post = _client_state(TEST_CLIENT_EMAIL)
    _check("1.db.nps", post["nps_standing"] == "promoter", f"db nps_standing={post['nps_standing']}")
    _check("1.db.csm", post["csm_standing"] == "happy", f"db csm_standing={post['csm_standing']}")

    GREGORY_BOT = "cfcea32a-062d-4269-ae0f-959adac8f597"
    history = _latest_history_changed_by(post["id"])
    _check(
        "1.history.gregory_bot",
        history == GREGORY_BOT,
        f"latest history changed_by={history}",
    )

    delivery = _delivery_status(body.get("delivery_id", ""))
    _check(
        "1.delivery.row",
        delivery is not None and delivery["processing_status"] == "processed",
        f"delivery row={delivery}",
    )
    _check(
        "1.delivery.source",
        delivery is not None and delivery["source"] == "airtable_nps_webhook",
        f"source={delivery['source'] if delivery else None}",
    )
    _check(
        "1.delivery.airtable_record_id",
        delivery is not None and delivery["call_external_id"] == "rec_test_1_promoter",
        f"call_external_id={delivery['call_external_id'] if delivery else None}",
    )


def test_2_at_risk_happy_path(url: str) -> None:
    print("\n[2] Valid payload, segment='At Risk' → 200, auto-derive=true")
    # Don't reset — test 1's Gregory-Bot history row makes this test
    # exercise the "auto-derive ALLOWED via Gregory Bot history" branch.
    status, body = _post_with_secret(
        url,
        {
            "client_email": TEST_CLIENT_EMAIL,
            "segment": "At Risk",
        },
    )
    _check("2.status", status == 200, f"got HTTP {status}, body={body}")
    if not body:
        return
    _check("2.nps_standing", body.get("nps_standing") == "at_risk", f"got {body.get('nps_standing')!r}")
    _check("2.csm_standing", body.get("csm_standing") == "at_risk", f"got {body.get('csm_standing')!r}")
    _check("2.auto_derive", body.get("auto_derive_applied") is True, f"got {body.get('auto_derive_applied')!r}")


def test_3_missing_secret(url: str) -> None:
    print("\n[3] Missing X-Webhook-Secret header → 401")
    status, body = _post(
        url,
        json.dumps({"client_email": TEST_CLIENT_EMAIL, "segment": "Neutral"}),
        # no X-Webhook-Secret header
    )
    _check("3.status", status == 401, f"got HTTP {status}, body={body}")
    _check("3.body", body == {"error": "unauthorized"}, f"got {body!r}")


def test_4_wrong_secret(url: str) -> None:
    print("\n[4] Wrong X-Webhook-Secret value → 401")
    status, body = _post_with_secret(
        url,
        {"client_email": TEST_CLIENT_EMAIL, "segment": "Neutral"},
        secret="wrong_value_definitely_not_the_real_secret",
    )
    _check("4.status", status == 401, f"got HTTP {status}, body={body}")
    _check("4.body", body == {"error": "unauthorized"}, f"got {body!r}")


def test_5_invalid_json(url: str) -> None:
    print("\n[5] Invalid JSON body → 400")
    status, body = _post(
        url,
        b"not valid json {{",
        {"X-Webhook-Secret": _RESOLVED_SECRET},
    )
    _check("5.status", status == 400, f"got HTTP {status}, body={body}")
    _check("5.error", body and body.get("error") == "invalid_json", f"got {body!r}")


def test_6_missing_email(url: str) -> None:
    print("\n[6] Missing client_email → 400")
    status, body = _post_with_secret(
        url,
        {"segment": "Neutral"},  # no client_email
    )
    _check("6.status", status == 400, f"got HTTP {status}, body={body}")
    _check("6.error", body and body.get("error") == "missing_field", f"got {body!r}")
    _check("6.detail", body and "client_email" in body.get("detail", ""), f"detail={body.get('detail') if body else None}")


def test_7_invalid_segment(url: str) -> None:
    print("\n[7] Unrecognized segment string → 400 with accepted-values list")
    status, body = _post_with_secret(
        url,
        {"client_email": TEST_CLIENT_EMAIL, "segment": "Detractor"},
    )
    _check("7.status", status == 400, f"got HTTP {status}, body={body}")
    _check("7.error", body and body.get("error") == "invalid_segment", f"got {body.get('error') if body else None}")
    expected_accepted = ["Strong / Promoter", "Neutral", "At Risk"]
    _check(
        "7.accepted",
        body and body.get("accepted") == expected_accepted,
        f"accepted={body.get('accepted') if body else None}",
    )


def test_8_no_client_match(url: str) -> None:
    print("\n[8] Email matching no client → 404")
    status, body = _post_with_secret(
        url,
        {
            "client_email": "nobody-test-airtable-nps@nowhere.invalid",
            "segment": "Strong / Promoter",
        },
    )
    _check("8.status", status == 404, f"got HTTP {status}, body={body}")
    _check("8.error", body and body.get("error") == "client_not_found", f"got {body.get('error') if body else None}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 72)
    print("Airtable NPS webhook — local test harness")
    print(f"Test client: {TEST_CLIENT_EMAIL}")
    print(f"Test secret: {_RESOLVED_SECRET[:24]}... (truncated)")
    print("=" * 72)

    url = _start_server()
    print(f"Receiver listening at {url}")

    # Snapshot: count of webhook_deliveries rows for our source before tests.
    start_ts = time.time()
    pre_delivery_count = _count_deliveries_with_source(
        "airtable_nps_webhook", start_ts - 60
    )
    print(f"Pre-test webhook_deliveries (source=airtable_nps_webhook, last 60s): {pre_delivery_count}")

    try:
        test_1_promoter_happy_path(url)
        test_2_at_risk_happy_path(url)
        test_3_missing_secret(url)
        test_4_wrong_secret(url)
        test_5_invalid_json(url)
        test_6_missing_email(url)
        test_7_invalid_segment(url)
        test_8_no_client_match(url)
    finally:
        print("\n" + "=" * 72)
        print("Cleanup: resetting test client nps_standing + csm_standing to NULL")
        try:
            _reset_test_client()
            post_state = _client_state(TEST_CLIENT_EMAIL)
            print(f"Post-cleanup state: {post_state}")
        except Exception:
            traceback.print_exc()
        _stop_server()

    # Summary.
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
