"""Unit tests for ingestion.slack.pipeline.

Mocks both the Supabase DB and the Slack client — no network, no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ingestion.slack import pipeline
from ingestion.slack.client import SlackNotInChannel


# ---------------------------------------------------------------------------
# Fake DB matching the subset of supabase-py shape we use
# ---------------------------------------------------------------------------


class _FakeDB:
    def __init__(self):
        self.ops: list[tuple[str, str, dict]] = []
        self.responses: dict[tuple[str, str], list] = {}

    def respond(self, op, table, data):
        self.responses.setdefault((op, table), []).append(data)

    def table(self, name):
        return _FakeTable(self, name)


class _FakeTable:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._op = None
        self._payload = None
        self._filters: list = []
        self._on_conflict = None

    def select(self, _cols, *, count=None):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload, *, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is_", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in_", col, vals))
        return self

    def execute(self):
        self.db.ops.append((self._op, self.name, {
            "payload": self._payload,
            "filters": list(self._filters),
            "on_conflict": self._on_conflict,
        }))
        scripted = self.db.responses.get((self._op, self.name))
        data = scripted.pop(0) if scripted else []
        return SimpleNamespace(data=data, count=len(data) if isinstance(data, list) else None)


class _FakeSlackClient:
    def __init__(self):
        self.calls_made = 0
        self._history: dict[str, list[dict]] = {}
        self._replies: dict[tuple[str, str], list[dict]] = {}
        self._members: dict[str, list[str]] = {}
        self._channels_list: list[dict] = []
        self._auth_user_id = "UBOT"

    def set_auth(self, user_id):
        self._auth_user_id = user_id

    def set_history(self, channel, events):
        self._history[channel] = events

    def set_replies(self, channel, parent_ts, events):
        self._replies[(channel, parent_ts)] = events

    def set_members(self, channel, members):
        self._members[channel] = members

    def set_channels(self, channels):
        self._channels_list = channels

    def auth_test(self):
        self.calls_made += 1
        return {"ok": True, "user_id": self._auth_user_id}

    def conversations_history(self, channel, *, oldest=None, latest=None):
        self.calls_made += 1
        yield from self._history.get(channel, [])

    def conversations_replies(self, channel, thread_ts):
        self.calls_made += 1
        yield from self._replies.get((channel, thread_ts), [])

    def conversations_members(self, channel):
        self.calls_made += 1
        return list(self._members.get(channel, []))

    def conversations_list(self, **_):
        self.calls_made += 1
        yield from self._channels_list


# ---------------------------------------------------------------------------
# Client target resolution
# ---------------------------------------------------------------------------


def test_resolve_client_target_happy_path():
    db = _FakeDB()
    db.respond("select", "clients", [{"id": "c-1", "full_name": "Jenny Burnett"}])
    db.respond("select", "slack_channels", [{
        "id": "sc-1", "slack_channel_id": "C999",
        "name": "Jenny Burnett", "client_id": "c-1",
    }])

    target = pipeline._resolve_client_target(db, "Jenny Burnett")

    assert target.resolved
    assert target.slack_channel_id == "C999"
    assert target.client_name == "Jenny Burnett"
    assert target.db_row_exists


def test_resolve_client_target_client_missing_reports_blocker():
    db = _FakeDB()
    db.respond("select", "clients", [])

    target = pipeline._resolve_client_target(db, "Nobody")
    assert not target.resolved
    assert "client_not_found" in target.resolution_error


def test_resolve_client_target_slack_channel_missing_reports_blocker():
    db = _FakeDB()
    db.respond("select", "clients", [{"id": "c-1", "full_name": "Some Client"}])
    db.respond("select", "slack_channels", [])

    target = pipeline._resolve_client_target(db, "Some Client")
    assert not target.resolved
    assert "no_slack_channel_for_client" in target.resolution_error


# ---------------------------------------------------------------------------
# Channel name resolution (e.g. ella-test)
# ---------------------------------------------------------------------------


def test_resolve_channel_name_target_inserts_slack_channels_row_on_apply():
    db = _FakeDB()
    # select: no existing row
    db.respond("select", "slack_channels", [])

    slack = _FakeSlackClient()
    slack.set_channels([{"id": "CTEST", "name": "ella-test", "is_private": False}])

    target = pipeline._resolve_channel_name_target(db, slack, "ella-test", dry_run=False)

    assert target.resolved
    assert target.slack_channel_id == "CTEST"
    insert_ops = [op for op in db.ops if op[0] == "insert" and op[1] == "slack_channels"]
    assert len(insert_ops) == 1


def test_resolve_channel_name_target_does_not_insert_on_dry_run():
    db = _FakeDB()
    db.respond("select", "slack_channels", [])
    slack = _FakeSlackClient()
    slack.set_channels([{"id": "CTEST", "name": "ella-test", "is_private": False}])

    target = pipeline._resolve_channel_name_target(db, slack, "ella-test", dry_run=True)

    assert target.resolved
    assert not target.db_row_exists
    insert_ops = [op for op in db.ops if op[0] == "insert"]
    assert len(insert_ops) == 0


def test_resolve_channel_name_target_not_found_reports_blocker():
    db = _FakeDB()
    slack = _FakeSlackClient()
    slack.set_channels([{"id": "C1", "name": "other"}])

    target = pipeline._resolve_channel_name_target(db, slack, "ella-test", dry_run=True)
    assert not target.resolved
    assert "channel_not_found_in_slack" in target.resolution_error


# ---------------------------------------------------------------------------
# Membership check
# ---------------------------------------------------------------------------


def test_membership_true_when_bot_in_members():
    slack = _FakeSlackClient()
    slack.set_members("C1", ["USOMEONE", "UBOT", "UOTHER"])
    assert pipeline._check_bot_membership(slack, "C1", "UBOT") is True


def test_membership_false_when_bot_absent():
    slack = _FakeSlackClient()
    slack.set_members("C1", ["USOMEONE", "UOTHER"])
    assert pipeline._check_bot_membership(slack, "C1", "UBOT") is False


# ---------------------------------------------------------------------------
# End-to-end happy-path (dry run)
# ---------------------------------------------------------------------------


def test_run_ingest_dry_run_surfaces_counts_without_writing():
    db = _FakeDB()
    # resolvers
    db.respond("select", "clients", [{"slack_user_id": "UCLIENT1"}])
    db.respond("select", "team_members", [{"slack_user_id": "UTEAM1"}])
    # client target resolution
    db.respond("select", "clients", [{"id": "c-1", "full_name": "Jenny Burnett"}])
    db.respond("select", "slack_channels", [{
        "id": "sc-1", "slack_channel_id": "C999",
        "name": "Jenny Burnett", "client_id": "c-1",
    }])
    # ella-test: not in DB
    db.respond("select", "slack_channels", [])

    slack = _FakeSlackClient()
    slack.set_members("C999", ["UBOT"])      # bot is member
    slack.set_members("CTEST", ["UBOT"])     # bot is member
    slack.set_channels([{"id": "CTEST", "name": "ella-test"}])

    slack.set_history("C999", [
        {"type": "message", "user": "UCLIENT1", "text": "Hey team",
         "ts": "1745500000.0001"},
        {"type": "message", "user": "UTEAM1", "text": "re: sure",
         "ts": "1745500100.0001"},
    ])
    slack.set_history("CTEST", [])

    report = pipeline.run_ingest(
        db, slack,
        client_full_names=["Jenny Burnett"],
        extra_channel_names=["ella-test"],
        dry_run=True,
    )

    assert report.bot_user_id == "UBOT"
    assert len(report.outcomes) == 2
    client_outcome = report.outcomes[0]
    assert client_outcome.resolved.client_name == "Jenny Burnett"
    assert client_outcome.messages_in_window == 2
    assert client_outcome.author_breakdown.get("client") == 1
    assert client_outcome.author_breakdown.get("team_member") == 1
    # No writes happened
    upserts = [op for op in db.ops if op[0] == "upsert" and op[1] == "slack_messages"]
    assert upserts == []


def test_run_ingest_surfaces_bot_not_in_channel_without_fetching():
    db = _FakeDB()
    db.respond("select", "clients", [])
    db.respond("select", "team_members", [])
    db.respond("select", "clients", [{"id": "c-1", "full_name": "Some Client"}])
    db.respond("select", "slack_channels", [{
        "id": "sc-1", "slack_channel_id": "C1",
        "name": "Some Client", "client_id": "c-1",
    }])

    slack = _FakeSlackClient()
    slack.set_members("C1", ["UNOT_BOT"])     # bot NOT a member

    report = pipeline.run_ingest(
        db, slack,
        client_full_names=["Some Client"],
        extra_channel_names=[],
        dry_run=True,
    )

    outcome = report.outcomes[0]
    assert outcome.error == "bot_not_in_channel"
    assert outcome.messages_in_window == 0


def test_run_ingest_follows_thread_parents_and_collapses_reply():
    db = _FakeDB()
    db.respond("select", "clients", [])
    db.respond("select", "team_members", [])
    db.respond("select", "clients", [{"id": "c-1", "full_name": "Client"}])
    db.respond("select", "slack_channels", [{
        "id": "sc-1", "slack_channel_id": "C1",
        "name": "Client", "client_id": "c-1",
    }])

    slack = _FakeSlackClient()
    slack.set_members("C1", ["UBOT"])
    parent_ts = "1745500000.0001"
    slack.set_history("C1", [
        {"type": "message", "user": "UX", "text": "parent", "ts": parent_ts,
         "thread_ts": parent_ts, "reply_count": 2},
    ])
    slack.set_replies("C1", parent_ts, [
        {"type": "message", "user": "UX", "text": "parent (again)", "ts": parent_ts,
         "thread_ts": parent_ts},  # same ts, should be skipped
        {"type": "message", "user": "UY", "text": "reply 1", "ts": "1745500001.0001",
         "thread_ts": parent_ts},
    ])

    report = pipeline.run_ingest(
        db, slack,
        client_full_names=["Client"],
        extra_channel_names=[],
        dry_run=True,
    )

    outcome = report.outcomes[0]
    # parent + 1 reply (the dup-ts reply is dropped)
    assert outcome.messages_in_window == 2
    assert outcome.threads_followed == 1


def test_run_ingest_upsert_count_split_inserts_vs_updates():
    db = _FakeDB()
    db.respond("select", "clients", [])
    db.respond("select", "team_members", [])
    db.respond("select", "clients", [{"id": "c-1", "full_name": "Client"}])
    db.respond("select", "slack_channels", [{
        "id": "sc-1", "slack_channel_id": "C1",
        "name": "Client", "client_id": "c-1",
    }])
    # Existing ts lookup — one already exists
    db.respond("select", "slack_messages", [{"slack_ts": "1.0"}])

    slack = _FakeSlackClient()
    slack.set_members("C1", ["UBOT"])
    slack.set_history("C1", [
        {"type": "message", "user": "UX", "text": "hi", "ts": "1.0"},
        {"type": "message", "user": "UX", "text": "new", "ts": "2.0"},
    ])

    report = pipeline.run_ingest(
        db, slack,
        client_full_names=["Client"],
        extra_channel_names=[],
        dry_run=False,
    )
    outcome = report.outcomes[0]
    assert outcome.messages_inserted == 1   # ts=2.0 is new
    assert outcome.messages_updated == 1    # ts=1.0 existed

    # Verify upsert uses the right on_conflict key
    upsert_ops = [op for op in db.ops if op[0] == "upsert" and op[1] == "slack_messages"]
    assert len(upsert_ops) == 1
    assert upsert_ops[0][2]["on_conflict"] == "slack_channel_id,slack_ts"
