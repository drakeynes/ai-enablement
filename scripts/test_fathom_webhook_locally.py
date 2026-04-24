"""F2.4 local test loop for api/fathom_events.py.

Stands up the real `handler` class in a background thread via
http.server.HTTPServer — same class Vercel instantiates in prod. Runs 5
paths (1 happy + 4 negative), checks HTTP response + cloud DB state for
each, cleans up all F24_TEST rows in try/finally.

Uses a TEST webhook secret (not the production one — F2.5 generates that).

Run:
    FATHOM_WEBHOOK_SECRET=whsec_<base64> .venv/bin/python scripts/test_fathom_webhook_locally.py

The script sets a test secret itself if none is set, so you can just run:
    .venv/bin/python scripts/test_fathom_webhook_locally.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
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

# Set the test secret BEFORE importing the handler so module-level env reads
# see it. The handler reads FATHOM_WEBHOOK_SECRET from os.environ on each
# invocation (no module-level cache) so order-of-imports doesn't strictly
# matter, but setting early avoids any future coupling surprise.
_TEST_SECRET_BYTES = secrets.token_bytes(32)
_TEST_SECRET = "whsec_" + base64.b64encode(_TEST_SECRET_BYTES).decode()
os.environ.setdefault("FATHOM_WEBHOOK_SECRET", _TEST_SECRET)
_RESOLVED_SECRET = os.environ["FATHOM_WEBHOOK_SECRET"]
# Keep the bytes the handler will use for verification
_SECRET_BYTES = base64.b64decode(_RESOLVED_SECRET[len("whsec_") :])

from api.fathom_events import handler  # noqa: E402  — must follow env setup
from shared.db import get_client  # noqa: E402


def _pg_conn():
    """Direct psycopg2 connection — bypasses PostgREST's occasional empty-body
    400 on `count='exact', head=True` queries during test verification.
    """
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


def _count(table: str, where_sql: str, params: tuple) -> int:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"select count(*) from {table} where {where_sql}", params)
        return cur.fetchone()[0]
    finally:
        conn.close()


FAKE_EXTERNAL_ID = "F24_TEST_CALL_001"
JAVI_UUID = "d1f69a08-9764-4ab8-ac04-94d9986721a0"


# ---------------------------------------------------------------------------
# Fixture + signing
# ---------------------------------------------------------------------------


def fixture_payload(external_id: str = FAKE_EXTERNAL_ID) -> dict:
    return {
        "title": "30mins with Scott (The AI Partner) (Javi Pena) [F24 TEST]",
        "meeting_title": None,
        "recording_id": external_id,
        "url": f"https://fathom.video/calls/{external_id}",
        "share_url": f"https://fathom.video/share/{external_id}",
        "created_at": "2026-04-24T19:30:00Z",
        "scheduled_start_time": "2026-04-24T19:00:00Z",
        "scheduled_end_time": "2026-04-24T19:30:00Z",
        "recording_start_time": "2026-04-24T19:02:00Z",
        "recording_end_time": "2026-04-24T19:28:00Z",
        "calendar_invitees_domains_type": "one_or_more_external",
        "transcript_language": "en",
        "transcript": [
            {"speaker": {"display_name": "Scott Wilson"}, "text": "F24 handler test.", "timestamp": "00:00:05"},
            {"speaker": {"display_name": "Javi Pena"}, "text": "Yes, end-to-end check.", "timestamp": "00:00:12"},
        ],
        "default_summary": {"markdown": "Drake ran the F2.4 handler end-to-end test against cloud."},
        "action_items": [
            {
                "description": "Ship the F2.4 handler",
                "user_generated": False,
                "completed": True,
                "recording_timestamp": "00:00:05",
                "recording_playback_url": None,
                "assignee": {"name": "Scott Wilson", "email": "scott@theaipartner.io"},
            },
        ],
        "calendar_invitees": [
            {"name": "Javi Pena", "email": "javpen93@gmail.com", "email_domain": "gmail.com", "is_external": True},
            {"name": "Scott Wilson", "email": "scott@theaipartner.io", "email_domain": "theaipartner.io", "is_external": False},
        ],
        "recorded_by": {"name": "Scott Wilson", "email": "scott@theaipartner.io"},
    }


def standard_webhooks_headers(body: bytes, *, webhook_id: str, timestamp: int | None = None) -> dict[str, str]:
    """Build valid webhook-id/timestamp/signature headers for `body`.

    Replicates the Standard Webhooks signing algorithm — same one the
    handler verifies against. `timestamp=None` means "now."
    """
    ts = int(time.time()) if timestamp is None else timestamp
    signed_payload = f"{webhook_id}.{ts}.".encode("utf-8") + body
    sig = base64.b64encode(
        hmac.new(_SECRET_BYTES, signed_payload, hashlib.sha256).digest()
    ).decode()
    return {
        "content-type": "application/json",
        "webhook-id": webhook_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": f"v1,{sig}",
    }


# ---------------------------------------------------------------------------
# Local HTTP server lifecycle
# ---------------------------------------------------------------------------


class _Server:
    """Context manager that runs the handler on 127.0.0.1:<random port>."""

    def __enter__(self) -> "_Server":
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/api/fathom_events"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def post(server: _Server, body_bytes: bytes, headers: dict[str, str]) -> tuple[int, dict]:
    req = urllib.request.Request(server.url, data=body_bytes, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"_raw": body}
        return exc.code, parsed


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def cleanup(db, webhook_ids: list[str], external_ids: list[str]) -> None:
    for ext in external_ids:
        call_rows = db.table("calls").select("id").eq("external_id", ext).execute().data or []
        call_uuids = [c["id"] for c in call_rows]
        doc_rows = db.table("documents").select("id").eq("external_id", ext).execute().data or []
        doc_ids = [d["id"] for d in doc_rows]
        if doc_ids:
            db.table("document_chunks").delete().in_("document_id", doc_ids).execute()
            db.table("documents").delete().in_("id", doc_ids).execute()
        if call_uuids:
            db.table("calls").delete().in_("id", call_uuids).execute()
    for wh_id in webhook_ids:
        db.table("webhook_deliveries").delete().eq("webhook_id", wh_id).execute()


# ---------------------------------------------------------------------------
# Test paths
# ---------------------------------------------------------------------------


def run_all():
    db = get_client()
    webhook_ids: list[str] = []
    external_ids: list[str] = [FAKE_EXTERNAL_ID, FAKE_EXTERNAL_ID + "_DUP"]

    results: list[tuple[str, bool, str]] = []

    try:
        # Pre-emptive cleanup in case an aborted prior run left state
        cleanup(db, [
            "F24_TEST_HAPPY", "F24_TEST_DUP_1", "F24_TEST_BAD_SIG",
            "F24_TEST_MALFORMED", "F24_TEST_INGEST_FAIL",
        ], external_ids)

        with _Server() as server:
            # ==========================================================
            # PATH 1: HAPPY — 200, processed, all tables populated
            # ==========================================================
            print("\n=== PATH 1: happy path ===")
            wh_id = "F24_TEST_HAPPY"
            webhook_ids.append(wh_id)
            payload = fixture_payload()
            body = json.dumps(payload).encode()
            headers = standard_webhooks_headers(body, webhook_id=wh_id)
            status, resp = post(server, body, headers)
            print(f"  HTTP {status}  body={resp}")
            assert status == 200, f"expected 200, got {status}"
            assert resp.get("delivered") == wh_id
            assert resp.get("action") == "inserted"
            # Verify cloud state
            wd = db.table("webhook_deliveries").select("*").eq("webhook_id", wh_id).execute().data
            assert len(wd) == 1 and wd[0]["processing_status"] == "processed", wd
            assert wd[0]["call_external_id"] == FAKE_EXTERNAL_ID
            assert "webhook-signature" not in (wd[0].get("headers") or {}), "signature leaked into DB!"
            # Verify all downstream tables
            calls = db.table("calls").select("*").eq("external_id", FAKE_EXTERNAL_ID).execute().data
            assert len(calls) == 1 and calls[0]["primary_client_id"] == JAVI_UUID
            docs = db.table("documents").select("document_type").eq("external_id", FAKE_EXTERNAL_ID).execute().data
            assert sorted(d["document_type"] for d in docs) == ["call_summary", "call_transcript_chunk"]
            ai_rows = db.table("call_action_items").select("*").eq("call_id", calls[0]["id"]).execute().data
            assert len(ai_rows) == 1 and ai_rows[0]["owner_type"] == "team_member"
            results.append(("happy path", True, "200 + all 5 tables populated + no sig leak"))

            # ==========================================================
            # PATH 2: DUPLICATE — same webhook_id, 200 dedup, no re-ingest
            # ==========================================================
            print("\n=== PATH 2: duplicate (replay) ===")
            # Need a fresh timestamp so the signature is within replay window
            body2 = json.dumps(payload).encode()
            headers2 = standard_webhooks_headers(body2, webhook_id=wh_id)
            status, resp = post(server, body2, headers2)
            print(f"  HTTP {status}  body={resp}")
            assert status == 200, f"expected 200, got {status}"
            assert resp.get("deduplicated") is True
            # webhook_deliveries row unchanged (still 'processed' from path 1)
            wd = db.table("webhook_deliveries").select("*").eq("webhook_id", wh_id).execute().data
            assert wd[0]["processing_status"] == "processed"
            # call row count for this external_id still = 1 (no duplicate ingest)
            calls_after = _count("calls", "external_id = %s", (FAKE_EXTERNAL_ID,))
            assert calls_after == 1, f"duplicate re-ingested! count={calls_after}"
            results.append(("duplicate", True, "200 dedup, cloud unchanged"))

            # ==========================================================
            # PATH 3: INVALID SIGNATURE — 401, no DB write
            # ==========================================================
            print("\n=== PATH 3: invalid signature ===")
            wh_id3 = "F24_TEST_BAD_SIG"
            webhook_ids.append(wh_id3)
            body3 = json.dumps(payload).encode()
            bad_headers = {
                "content-type": "application/json",
                "webhook-id": wh_id3,
                "webhook-timestamp": str(int(time.time())),
                "webhook-signature": "v1,AAAAinvalidbase64signaturethatwillfail==",
            }
            status, resp = post(server, body3, bad_headers)
            print(f"  HTTP {status}  body={resp}")
            assert status == 401, f"expected 401, got {status}"
            # Crucially: NO row in webhook_deliveries for this webhook_id
            wd_count = _count("webhook_deliveries", "webhook_id = %s", (wh_id3,))
            assert wd_count == 0, f"bad-sig delivery created a webhook_deliveries row ({wd_count})!"
            results.append(("bad signature", True, "401 + no DB write"))

            # ==========================================================
            # PATH 4: MALFORMED PAYLOAD — 400, row marked malformed
            # ==========================================================
            print("\n=== PATH 4: malformed payload (missing required) ===")
            wh_id4 = "F24_TEST_MALFORMED"
            webhook_ids.append(wh_id4)
            bad_payload = fixture_payload(external_id="F24_TEST_MALFORMED_CALL")
            bad_payload.pop("recording_id")   # adapter's AdapterError path
            body4 = json.dumps(bad_payload).encode()
            headers4 = standard_webhooks_headers(body4, webhook_id=wh_id4)
            status, resp = post(server, body4, headers4)
            print(f"  HTTP {status}  body={resp}")
            assert status == 400, f"expected 400, got {status}"
            assert resp.get("error") == "malformed_payload"
            wd = db.table("webhook_deliveries").select("*").eq("webhook_id", wh_id4).execute().data
            assert len(wd) == 1
            assert wd[0]["processing_status"] == "malformed", wd[0]
            assert wd[0]["processing_error"] is not None
            # No downstream rows — adapter failed before ingest
            calls_count = _count("calls", "external_id = %s", ("F24_TEST_MALFORMED_CALL",))
            assert calls_count == 0, f"malformed delivery wrote calls rows! count={calls_count}"
            results.append(("malformed", True, "400 + status=malformed + no downstream rows"))

            # ==========================================================
            # PATH 5: INGEST FAILURE — 500, row marked failed
            # ==========================================================
            print("\n=== PATH 5: ingest failure (simulated via monkeypatch) ===")
            wh_id5 = "F24_TEST_INGEST_FAIL"
            webhook_ids.append(wh_id5)
            # Monkeypatch ingest_call in the handler module to raise
            import api.fathom_events as fh
            original_ingest = fh.ingest_call
            def boom(*args, **kwargs):
                raise RuntimeError("simulated ingest failure for F24 test")
            fh.ingest_call = boom
            try:
                payload5 = fixture_payload(external_id="F24_TEST_FAIL_CALL")
                body5 = json.dumps(payload5).encode()
                headers5 = standard_webhooks_headers(body5, webhook_id=wh_id5)
                status, resp = post(server, body5, headers5)
                print(f"  HTTP {status}  body={resp}")
                assert status == 500, f"expected 500, got {status}"
                assert resp.get("error") == "ingest_failed"
                wd = db.table("webhook_deliveries").select("*").eq("webhook_id", wh_id5).execute().data
                assert len(wd) == 1
                assert wd[0]["processing_status"] == "failed", wd[0]
                # Traceback present and doesn't contain the secret
                err = wd[0]["processing_error"] or ""
                assert "simulated ingest failure" in err
                assert "whsec_" not in err, "traceback leaked the webhook secret!"
                assert "sk-" not in err
                results.append(("ingest failure", True, "500 + status=failed + traceback sanitized"))
            finally:
                fh.ingest_call = original_ingest

    except AssertionError as exc:
        print(f"\n!! TEST FAILED: {exc}")
        traceback.print_exc()
        results.append(("assertion", False, str(exc)))
    except Exception:
        print("\n!! UNEXPECTED ERROR:")
        traceback.print_exc()
        results.append(("unexpected", False, "see traceback"))
    finally:
        print("\n=== CLEANUP ===")
        try:
            cleanup(db, webhook_ids, external_ids + ["F24_TEST_MALFORMED_CALL", "F24_TEST_FAIL_CALL"])
            # Final verification via psycopg2 because PostgREST occasionally flakes
            import psycopg2
            from urllib.parse import quote
            from dotenv import load_dotenv
            load_dotenv(".env.local")
            with open("supabase/.temp/pooler-url") as f:
                pooler = f.read().strip()
            pw = os.environ["SUPABASE_DB_PASSWORD"]
            at = pooler.index("@")
            dsn = f"{pooler[:at]}:{quote(pw, safe='')}{pooler[at:]}"
            conn = psycopg2.connect(dsn, connect_timeout=15)
            cur = conn.cursor()
            for label, q in [
                ("F24 calls left", "select count(*) from calls where external_id like 'F24_TEST_%'"),
                ("F24 docs left",  "select count(*) from documents where external_id like 'F24_TEST_%'"),
                ("F24 webhook_deliveries left", "select count(*) from webhook_deliveries where webhook_id like 'F24_TEST_%'"),
                ("total calls (expect 516)", "select count(*) from calls"),
                ("total documents (expect 685)", "select count(*) from documents"),
                ("total webhook_deliveries (expect 0)", "select count(*) from webhook_deliveries"),
                ("total call_action_items (expect 0)", "select count(*) from call_action_items"),
            ]:
                cur.execute(q)
                print(f"  {label}: {cur.fetchone()[0]}")
            conn.close()
        except Exception:
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for path, passed, detail in results:
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {path:<18} {detail}")
    all_pass = all(r[1] for r in results)
    print(f"\nOVERALL: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(run_all())
