"""Unit tests for ingestion.slack.client.

Uses httpx.MockTransport so we exercise the real `SlackClient` code
path against scripted responses — no network calls.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest

from ingestion.slack import client as sc


def _response(payload: dict[str, Any], *, status: int = 200, headers: dict[str, str] | None = None):
    return httpx.Response(
        status_code=status,
        headers=headers or {},
        content=json.dumps(payload).encode(),
    )


def _make_client(
    handler,
    *,
    token: str = "xoxb-test",
) -> sc.SlackClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(
        base_url="https://slack.com/api",
        transport=transport,
        headers={"Authorization": f"Bearer {token}"},
    )
    return sc.SlackClient(token=token, http_client=http)


# ---------------------------------------------------------------------------
# Basic call + auth
# ---------------------------------------------------------------------------


def test_missing_token_raises_at_construction():
    os.environ.pop("SLACK_BOT_TOKEN", None)
    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        sc.SlackClient(token=None, http_client=httpx.Client())


def test_auth_test_returns_payload():
    def handler(request):
        assert request.url.path.endswith("/auth.test")
        return _response({"ok": True, "user_id": "UBOT", "team_id": "T1"})
    client = _make_client(handler)
    result = client.auth_test()
    assert result["user_id"] == "UBOT"
    assert client.calls_made == 1


def test_slack_error_raises_api_error():
    def handler(request):
        return _response({"ok": False, "error": "invalid_auth"})
    client = _make_client(handler)
    with pytest.raises(sc.SlackAPIError) as exc:
        client.auth_test()
    assert exc.value.error == "invalid_auth"


def test_not_in_channel_raises_specialized_exception():
    def handler(request):
        return _response({"ok": False, "error": "not_in_channel"})
    client = _make_client(handler)
    with pytest.raises(sc.SlackNotInChannel):
        list(client.conversations_history("C1"))


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_conversations_history_paginates_until_cursor_exhausted():
    pages = [
        {
            "ok": True,
            "messages": [{"ts": f"1.{i}"} for i in range(3)],
            "response_metadata": {"next_cursor": "page2"},
        },
        {
            "ok": True,
            "messages": [{"ts": f"2.{i}"} for i in range(2)],
            "response_metadata": {"next_cursor": ""},
        },
    ]
    call_count = {"n": 0}

    def handler(request):
        i = call_count["n"]
        call_count["n"] += 1
        return _response(pages[i])

    client = _make_client(handler)
    all_msgs = list(client.conversations_history("C1"))
    assert len(all_msgs) == 5
    assert client.calls_made == 2


def test_conversations_list_yields_items_across_pages():
    pages = [
        {"ok": True, "channels": [{"id": "C1", "name": "one"}],
         "response_metadata": {"next_cursor": "more"}},
        {"ok": True, "channels": [{"id": "C2", "name": "two"}]},
    ]
    call_count = {"n": 0}

    def handler(request):
        i = call_count["n"]
        call_count["n"] += 1
        return _response(pages[i])

    client = _make_client(handler)
    channels = list(client.conversations_list())
    assert [c["name"] for c in channels] == ["one", "two"]


# ---------------------------------------------------------------------------
# Rate-limit / retry
# ---------------------------------------------------------------------------


def test_429_triggers_retry_after_sleep(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(sc.time, "sleep", lambda s: sleeps.append(s))

    responses = [
        _response({}, status=429, headers={"Retry-After": "2"}),
        _response({"ok": True, "user_id": "UBOT"}),
    ]
    call_count = {"n": 0}

    def handler(request):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r

    client = _make_client(handler)
    result = client.auth_test()
    assert result["user_id"] == "UBOT"
    assert client.calls_made == 2
    assert client.rate_limit_hits == 1
    assert client.retries >= 1
    # Slept at least the Retry-After value
    assert any(s >= 2 for s in sleeps)


def test_5xx_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(sc.time, "sleep", lambda s: None)
    responses = [
        _response({}, status=502),
        _response({"ok": True, "user_id": "UBOT"}),
    ]
    call_count = {"n": 0}

    def handler(request):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r

    client = _make_client(handler)
    result = client.auth_test()
    assert result["user_id"] == "UBOT"
    assert client.retries >= 1


# ---------------------------------------------------------------------------
# find_channel_by_name helper
# ---------------------------------------------------------------------------


def test_find_channel_by_name_accepts_hash_prefix():
    def handler(request):
        return _response({
            "ok": True,
            "channels": [
                {"id": "C1", "name": "ella-test"},
                {"id": "C2", "name": "something-else"},
            ],
        })
    client = _make_client(handler)
    found = sc.find_channel_by_name(client, "#ella-test")
    assert found is not None
    assert found["id"] == "C1"


def test_find_channel_by_name_returns_none_when_missing():
    def handler(request):
        return _response({"ok": True, "channels": [{"id": "C1", "name": "nope"}]})
    client = _make_client(handler)
    assert sc.find_channel_by_name(client, "ella-test") is None
