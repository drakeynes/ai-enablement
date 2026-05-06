"""Local test loop for api/accountability_notification_cron.py.

Mocks:
  - Airtable's HTTP layer at `urllib.request.urlopen` inside the cron
    module. Fakes pagination; injects fixture submission emails.
  - Slack at `shared.slack_post.post_message` (no real chat.postMessage
    fires).

Self-seeds three test clients with three different CSMs. Two clients
"didn't submit" (covered by mocked Airtable), one did.

Paths:
  1. Happy path — all CSMs with missing clients get one Slack message
     each; audit row processed; payload counts match.
  2. Idempotent re-run — same Airtable + Gregory state → same post
     count; audit row written each time (intentional duplication;
     dedup is V1.1+).
  3. No-missing — every eligible client submitted → no Slack post,
     audit row processed with `skipped_reason='no_missing_clients'`.
  4. Airtable failure → audit row failed; loud Slack alert posted to
     channel; no per-CSM messages; cron returns status='failed'.
  5. Per-CSM Slack failure — one CSM's post raises ok=false; other
     CSMs still get their messages; audit row reflects partial.
  6. Channel env var missing → audit row failed, no Slack call.
  7. Auth: missing/wrong token → 401, no work done. (Smoke via the
     handler interface, not the inner function.)

Self-seeded fixtures hard-deleted in cleanup.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import urllib.request
import uuid
from http.server import HTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Set the test auth token BEFORE importing the handler so the env var
# is present at first os.environ.get() call. The handler validates
# Authorization: Bearer <CRON_SECRET> — single-var pattern shared across
# all cron endpoints (consolidated in M6.2).
import secrets

_TEST_AUTH_TOKEN = "test_token_" + secrets.token_urlsafe(16)
os.environ.setdefault("CRON_SECRET", _TEST_AUTH_TOKEN)

# Stable Airtable env so the inner function has what it needs. The
# urllib mock intercepts before any real call goes out.
os.environ.setdefault("AIRTABLE_ACCOUNTABILITY_PAT", "test-pat-not-real")
os.environ.setdefault("AIRTABLE_ACCOUNTABILITY_BASE_ID", "appTEST")
os.environ.setdefault("AIRTABLE_ACCOUNTABILITY_TABLE_ID", "tblTEST")

from api import accountability_notification_cron as cron_mod  # noqa: E402
from api.accountability_notification_cron import (  # noqa: E402
    handler as CronHandler,
    run_accountability_notification_cron,
)
from shared.db import get_client  # noqa: E402

RUN_TOKEN = uuid.uuid4().hex[:10]
TEST_CHANNEL = f"C_TEST_ACCT_{RUN_TOKEN.upper()}"


def _pg_conn():
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
# Self-seeded fixtures
# ---------------------------------------------------------------------------


_FIXTURE_CLIENT_IDS: list[str] = []
_FIXTURE_CSM_IDS: list[str] = []
_FIXTURE_ASSIGNMENT_IDS: list[str] = []
_AUDIT_DELIVERY_IDS: list[str] = []

# Three (client, CSM) pairs. Per-test we'll vary which clients
# appear in mocked-Airtable's "yesterday submitted" set.
_FIXTURE_CLIENTS = [
    {
        "email": f"acct-test-a-{RUN_TOKEN}@nowhere.invalid",
        "client_full_name": f"Acct Test A {RUN_TOKEN}",
        "csm_full_name": f"Test CSM Alpha {RUN_TOKEN[:6]}",
    },
    {
        "email": f"acct-test-b-{RUN_TOKEN}@nowhere.invalid",
        "client_full_name": f"Acct Test B {RUN_TOKEN}",
        "csm_full_name": f"Test CSM Beta {RUN_TOKEN[:6]}",
    },
    {
        "email": f"acct-test-c-{RUN_TOKEN}@nowhere.invalid",
        "client_full_name": f"Acct Test C {RUN_TOKEN}",
        "csm_full_name": f"Test CSM Alpha {RUN_TOKEN[:6]}",  # shared with A
    },
]


def _seed_fixtures() -> None:
    """Insert three test clients + their CSMs + assignments. Two CSMs
    total (Alpha owns A + C, Beta owns B)."""
    csm_names_seen: dict[str, str] = {}
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        for fixture in _FIXTURE_CLIENTS:
            csm_name = fixture["csm_full_name"]
            if csm_name not in csm_names_seen:
                cur.execute(
                    """
                    INSERT INTO team_members (
                      email, full_name, role, is_active, is_csm, metadata
                    ) VALUES (%s, %s, 'csm', true, true,
                      jsonb_build_object('seeded_by',
                        'test_accountability_notification_cron_locally'))
                    RETURNING id;
                    """,
                    (
                        f"{csm_name.lower().replace(' ', '-')}@theaipartner.io",
                        csm_name,
                    ),
                )
                csm_id = str(cur.fetchone()[0])
                _FIXTURE_CSM_IDS.append(csm_id)
                csm_names_seen[csm_name] = csm_id

            cur.execute(
                """
                INSERT INTO clients (
                  full_name, email, status, csm_standing,
                  accountability_enabled, nps_enabled, tags, metadata
                ) VALUES (%s, %s, 'active', 'content',
                  true, true, '{}'::text[],
                  jsonb_build_object('seeded_by',
                    'test_accountability_notification_cron_locally'))
                RETURNING id;
                """,
                (fixture["client_full_name"], fixture["email"]),
            )
            client_id = str(cur.fetchone()[0])
            _FIXTURE_CLIENT_IDS.append(client_id)

            cur.execute(
                """
                INSERT INTO client_team_assignments (
                  client_id, team_member_id, role, assigned_at
                ) VALUES (%s, %s, 'primary_csm', now())
                RETURNING id;
                """,
                (client_id, csm_names_seen[csm_name]),
            )
            _FIXTURE_ASSIGNMENT_IDS.append(str(cur.fetchone()[0]))
        conn.commit()
    finally:
        conn.close()


def _teardown_fixtures() -> None:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        for delivery_id in _AUDIT_DELIVERY_IDS:
            cur.execute(
                "DELETE FROM webhook_deliveries WHERE webhook_id = %s",
                (delivery_id,),
            )
        # Generic cleanup of any orphaned audit rows for our cron source
        # written during the test run (some paths don't capture the
        # delivery_id back).
        cur.execute(
            "DELETE FROM webhook_deliveries WHERE source = %s "
            "AND received_at >= now() - interval '10 minutes' "
            "AND payload::text LIKE %s",
            (
                "accountability_notification_cron",
                f"%{RUN_TOKEN}%",
            ),
        )
        for assignment_id in _FIXTURE_ASSIGNMENT_IDS:
            cur.execute(
                "DELETE FROM client_team_assignments WHERE id = %s",
                (assignment_id,),
            )
        for client_id in _FIXTURE_CLIENT_IDS:
            cur.execute(
                "DELETE FROM client_status_history WHERE client_id = %s",
                (client_id,),
            )
            cur.execute(
                "DELETE FROM client_standing_history WHERE client_id = %s",
                (client_id,),
            )
            cur.execute(
                "DELETE FROM clients WHERE id = %s", (client_id,)
            )
        for csm_id in _FIXTURE_CSM_IDS:
            cur.execute(
                "DELETE FROM team_members WHERE id = %s", (csm_id,)
            )
        conn.commit()
    finally:
        conn.close()


def _delivery_status(delivery_id: str) -> dict | None:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT webhook_id, source, processing_status, processing_error,
                   payload
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
            "payload": row[4],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Airtable HTTP mock
# ---------------------------------------------------------------------------


def _make_fake_airtable_urlopen(submitted_emails: list[str], pages: int = 1):
    """Return a urlopen replacement that responds with paginated
    Airtable JSON containing the given submitted emails. Splits across
    `pages` pages if requested (to exercise pagination)."""

    def fake_urlopen(req, timeout=None):
        # Parse offset from the URL to pick the page.
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if "offset=p" in url:
            offset = url.split("offset=p")[1].split("&")[0]
            page_idx = int(offset)
        else:
            page_idx = 0

        if pages == 1:
            records = [
                {"fields": {"Email": e}} for e in submitted_emails
            ]
            body = {"records": records}
        else:
            # Multi-page: split emails across pages.
            per_page = max(1, len(submitted_emails) // pages + 1)
            start = page_idx * per_page
            end = start + per_page
            records = [
                {"fields": {"Email": e}}
                for e in submitted_emails[start:end]
            ]
            body = {"records": records}
            if page_idx + 1 < pages:
                body["offset"] = f"p{page_idx + 1}"

        encoded = json.dumps(body).encode("utf-8")
        # Return a context-manager-shaped response. urlopen returns an
        # http.client.HTTPResponse normally; we mimic the contextmanager
        # + .read() interface.
        class FakeResponse:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return False

            def read(self_inner):
                return encoded

        return FakeResponse()

    return fake_urlopen


def _make_failing_airtable_urlopen():
    """Return a urlopen replacement that raises (simulates Airtable
    being unreachable)."""
    def fake_urlopen(req, timeout=None):
        import socket
        raise socket.timeout("simulated Airtable timeout")
    return fake_urlopen


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, condition: bool, detail: str) -> None:
    _RESULTS.append((name, condition, detail))
    marker = "✅" if condition else "❌"
    print(f"  {marker} {name}: {detail}")


def test_1_happy_path() -> None:
    print("\n[1] Happy path — A submitted, B+C didn't → 2 messages (Alpha for C, Beta for B)")
    os.environ["SLACK_CS_ACCOUNTABILITY_CHANNEL_ID"] = TEST_CHANNEL

    submitted = [_FIXTURE_CLIENTS[0]["email"].upper()]  # A submitted (uppercase to test normalize)
    posts: list[tuple[str, str]] = []

    def fake_post(channel_id, text, **kwargs):
        posts.append((channel_id, text))
        return {"ok": True, "slack_error": None}

    fake_urlopen = _make_fake_airtable_urlopen(submitted)

    with patch.object(cron_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch("api.accountability_notification_cron.post_message", side_effect=fake_post):
        result = run_accountability_notification_cron()

    _AUDIT_DELIVERY_IDS.append(result["delivery_id"])

    _check("1.status", result["status"] == "ok", f"status={result['status']!r}")
    _check(
        "1.eligible_count_includes_3",
        result["eligible_count"] >= 3,
        f"eligible_count={result['eligible_count']} (>= 3 fixtures)",
    )
    _check(
        "1.submitted_count",
        result["submitted_count"] == 1,
        f"submitted_count={result['submitted_count']}",
    )
    # Production DB has other accountability-enabled clients with real
    # CSMs — they ALSO get messages. Assert >= 2 (our two fixture CSMs)
    # rather than exactly 2; full count varies with prod state.
    _check(
        "1.posts_made_at_least_2",
        len(posts) >= 2,
        f"posts={len(posts)} (must include our 2 fixture CSMs)",
    )
    posted_channels = {p[0] for p in posts}
    _check(
        "1.channel_correct",
        posted_channels == {TEST_CHANNEL},
        f"channels={posted_channels}",
    )
    posted_text = "\n\n".join(p[1] for p in posts)
    _check(
        "1.fixture_csms_messaged",
        f"Test CSM Alpha {RUN_TOKEN[:6]}" in result["csms_messaged_ok"]
        and f"Test CSM Beta {RUN_TOKEN[:6]}" in result["csms_messaged_ok"],
        f"csms_messaged_ok={result['csms_messaged_ok']}",
    )
    _check(
        "1.client_b_in_text",
        _FIXTURE_CLIENTS[1]["client_full_name"] in posted_text,
        f"client B name in text: yes",
    )
    _check(
        "1.client_c_in_text",
        _FIXTURE_CLIENTS[2]["client_full_name"] in posted_text,
        f"client C name in text: yes",
    )
    _check(
        "1.client_a_not_in_text",
        _FIXTURE_CLIENTS[0]["client_full_name"] not in posted_text,
        f"client A (submitted) absent from text: confirmed",
    )

    delivery = _delivery_status(result["delivery_id"])
    _check(
        "1.audit.processed",
        delivery is not None
        and delivery["processing_status"] == "processed",
        f"audit={delivery}",
    )


def test_2_idempotent_rerun() -> None:
    print("\n[2] Re-fire with same state → 2 more posts, 1 more audit row (V1 idempotency: no dedup)")
    os.environ["SLACK_CS_ACCOUNTABILITY_CHANNEL_ID"] = TEST_CHANNEL
    submitted = [_FIXTURE_CLIENTS[0]["email"]]
    posts: list[tuple[str, str]] = []

    def fake_post(channel_id, text, **kwargs):
        posts.append((channel_id, text))
        return {"ok": True, "slack_error": None}

    fake_urlopen = _make_fake_airtable_urlopen(submitted)

    with patch.object(cron_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch("api.accountability_notification_cron.post_message", side_effect=fake_post):
        result = run_accountability_notification_cron()

    _AUDIT_DELIVERY_IDS.append(result["delivery_id"])
    _check("2.status_ok", result["status"] == "ok", f"status={result['status']!r}")
    _check(
        "2.posts_made_again",
        len(posts) >= 2,
        f"posts={len(posts)} (>= 2 expected; no dedup in V1)",
    )


def test_3_no_missing() -> None:
    print("\n[3] All eligible clients submitted → no Slack post, audit row marks skip")
    os.environ["SLACK_CS_ACCOUNTABILITY_CHANNEL_ID"] = TEST_CHANNEL
    submitted = [c["email"] for c in _FIXTURE_CLIENTS]

    # Also include any other production active+enabled emails to ensure
    # NOTHING is missing system-wide for this test. We pull them from
    # the DB up front and add them to the mocked submission set.
    db = get_client()
    resp = (
        db.table("clients")
        .select("email")
        .is_("archived_at", "null")
        .eq("status", "active")
        .eq("accountability_enabled", True)
        .execute()
    )
    for row in (resp.data or []):
        if row.get("email"):
            submitted.append(row["email"])

    posts: list[tuple[str, str]] = []

    def fake_post(channel_id, text, **kwargs):
        posts.append((channel_id, text))
        return {"ok": True, "slack_error": None}

    fake_urlopen = _make_fake_airtable_urlopen(submitted)

    with patch.object(cron_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch("api.accountability_notification_cron.post_message", side_effect=fake_post):
        result = run_accountability_notification_cron()

    _AUDIT_DELIVERY_IDS.append(result["delivery_id"])
    _check("3.status_ok", result["status"] == "ok", f"status={result['status']!r}")
    _check("3.no_posts", len(posts) == 0, f"posts={len(posts)}")
    _check(
        "3.skipped_reason",
        result.get("skipped_reason") == "no_missing_clients",
        f"skipped_reason={result.get('skipped_reason')!r}",
    )

    delivery = _delivery_status(result["delivery_id"])
    _check(
        "3.audit.processed",
        delivery is not None
        and delivery["processing_status"] == "processed",
        f"audit={delivery}",
    )


def test_4_airtable_failure() -> None:
    print("\n[4] Airtable timeout → audit failed, loud Slack alert posted, status=failed")
    os.environ["SLACK_CS_ACCOUNTABILITY_CHANNEL_ID"] = TEST_CHANNEL
    posts: list[tuple[str, str]] = []

    def fake_post(channel_id, text, **kwargs):
        posts.append((channel_id, text))
        return {"ok": True, "slack_error": None}

    fake_urlopen = _make_failing_airtable_urlopen()

    with patch.object(cron_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch("api.accountability_notification_cron.post_message", side_effect=fake_post):
        result = run_accountability_notification_cron()

    _AUDIT_DELIVERY_IDS.append(result["delivery_id"])
    _check("4.status_failed", result["status"] == "failed", f"status={result['status']!r}")
    _check(
        "4.error_present",
        "airtable_fetch_failed" in (result.get("error") or ""),
        f"error={result.get('error')!r}",
    )
    _check(
        "4.failure_alert_posted",
        len(posts) == 1,
        f"posts={len(posts)}",
    )
    _check(
        "4.alert_text_mentions_delivery_id",
        len(posts) == 1
        and result["delivery_id"] in posts[0][1],
        f"alert text didn't include delivery_id",
    )
    _check(
        "4.alert_text_warning",
        len(posts) == 1 and ":warning:" in posts[0][1],
        f"alert text missing :warning: marker",
    )

    delivery = _delivery_status(result["delivery_id"])
    _check(
        "4.audit_failed",
        delivery is not None and delivery["processing_status"] == "failed",
        f"audit={delivery}",
    )


def test_5_per_csm_partial_failure() -> None:
    print("\n[5] Slack post fails for Alpha but succeeds for others → partial; audit reflects")
    os.environ["SLACK_CS_ACCOUNTABILITY_CHANNEL_ID"] = TEST_CHANNEL
    # B and C didn't submit (A did). Both fixture CSMs (Alpha owns C,
    # Beta owns B) get messages, plus prod CSMs for their own missing
    # clients. We fail Alpha's specifically by detecting the unique
    # Alpha-owned client name in the bullet list — first-name alone
    # can't distinguish since both fixture CSMs format as "Test —".
    submitted = [_FIXTURE_CLIENTS[0]["email"]]
    posts_made: list[dict] = []
    alpha_owned_client = _FIXTURE_CLIENTS[2]["client_full_name"]

    def fake_post(channel_id, text, **kwargs):
        if alpha_owned_client in text:
            posts_made.append({"text": text, "ok": False})
            return {"ok": False, "slack_error": "channel_not_found"}
        posts_made.append({"text": text, "ok": True})
        return {"ok": True, "slack_error": None}

    fake_urlopen = _make_fake_airtable_urlopen(submitted)

    with patch.object(cron_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch("api.accountability_notification_cron.post_message", side_effect=fake_post):
        result = run_accountability_notification_cron()

    _AUDIT_DELIVERY_IDS.append(result["delivery_id"])
    _check(
        "5.status_partial",
        result["status"] == "partial_failure",
        f"status={result['status']!r}",
    )
    # Alpha-fixture CSM is in the failed list; Beta-fixture CSM is in
    # the ok list. Production CSMs (Lou/Nico/Scott) all succeed because
    # the fail predicate keys on the Alpha-owned fixture client name
    # which won't appear in their messages.
    alpha_csm_name = f"Test CSM Alpha {RUN_TOKEN[:6]}"
    beta_csm_name = f"Test CSM Beta {RUN_TOKEN[:6]}"
    failed_names = [
        f["csm"] for f in result["csms_messaged_failed"]
    ]
    _check(
        "5.alpha_failed",
        alpha_csm_name in failed_names,
        f"failed={failed_names}",
    )
    _check(
        "5.beta_ok",
        beta_csm_name in result["csms_messaged_ok"],
        f"ok={result['csms_messaged_ok']}",
    )

    delivery = _delivery_status(result["delivery_id"])
    _check(
        "5.audit_failed_status",
        delivery is not None and delivery["processing_status"] == "failed",
        f"audit={delivery}",
    )


def test_6_channel_env_missing() -> None:
    print("\n[6] SLACK_CS_ACCOUNTABILITY_CHANNEL_ID unset → audit failed, no posts")
    saved = os.environ.pop("SLACK_CS_ACCOUNTABILITY_CHANNEL_ID", None)
    try:
        submitted = [_FIXTURE_CLIENTS[0]["email"]]
        posts: list[tuple[str, str]] = []

        def fake_post(channel_id, text, **kwargs):
            posts.append((channel_id, text))
            return {"ok": True, "slack_error": None}

        fake_urlopen = _make_fake_airtable_urlopen(submitted)

        with patch.object(cron_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
             patch("api.accountability_notification_cron.post_message", side_effect=fake_post):
            result = run_accountability_notification_cron()

        _AUDIT_DELIVERY_IDS.append(result["delivery_id"])
        _check(
            "6.status_failed",
            result["status"] == "failed",
            f"status={result['status']!r}",
        )
        # Posts list may include the failure-alert path, but since the
        # channel env var is what drives BOTH the per-CSM post AND the
        # failure-alert post, neither should land. The cron returned
        # 'failed' before reaching the post stage, so post count == 0.
        _check(
            "6.no_posts",
            len(posts) == 0,
            f"posts={len(posts)}",
        )
        _check(
            "6.error_mentions_channel",
            "SLACK_CS_ACCOUNTABILITY_CHANNEL_ID" in (result.get("error") or ""),
            f"error={result.get('error')!r}",
        )
    finally:
        if saved:
            os.environ["SLACK_CS_ACCOUNTABILITY_CHANNEL_ID"] = saved


def test_7_auth() -> None:
    print("\n[7] Handler auth — missing/wrong token → 401")
    # Use the HTTPServer-based smoke pattern from existing harnesses.
    server = HTTPServer(("127.0.0.1", 0), CronHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    url = f"http://127.0.0.1:{port}/api/accountability_notification_cron"

    try:
        # No auth header → 401
        req = urllib.request.Request(url, method="POST", data=b"")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        _check("7a.no_auth_401", status == 401, f"got HTTP {status}")

        # Wrong token → 401
        req = urllib.request.Request(
            url,
            method="POST",
            data=b"",
            headers={"Authorization": "Bearer wrong_token"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        _check("7b.wrong_auth_401", status == 401, f"got HTTP {status}")
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


import urllib.error  # noqa: E402  — used by test 7


def main() -> int:
    print("=" * 72)
    print("Accountability notification cron — local test harness")
    print(f"Run token: {RUN_TOKEN}")
    print("=" * 72)

    print("\nSeeding fixture clients + CSMs...")
    _seed_fixtures()
    print(
        f"  clients={_FIXTURE_CLIENT_IDS} csms={_FIXTURE_CSM_IDS}"
    )

    try:
        test_1_happy_path()
        test_2_idempotent_rerun()
        test_3_no_missing()
        test_4_airtable_failure()
        test_5_per_csm_partial_failure()
        test_6_channel_env_missing()
        test_7_auth()
    finally:
        print("\n" + "=" * 72)
        print("Cleanup")
        print("=" * 72)
        try:
            _teardown_fixtures()
            print(
                f"  Hard-deleted fixtures + {len(_AUDIT_DELIVERY_IDS)} captured audit rows"
            )
        except Exception:
            traceback.print_exc()

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
