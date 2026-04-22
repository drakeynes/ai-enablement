"""Unit tests for ingestion.content.pipeline."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ingestion.content import pipeline


# ---------------------------------------------------------------------------
# Fake DB harness (same shape pattern used in other ingestion tests)
# ---------------------------------------------------------------------------


class _FakeDB:
    def __init__(self):
        self.ops: list[tuple] = []
        self.responses: dict[tuple[str, str], list] = {}
        self.insert_returns: dict[str, list] = {}

    def respond(self, op, table, data):
        self.responses.setdefault((op, table), []).append(data)

    def insert_returning(self, table, ids):
        self.insert_returns[table] = list(ids)

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
        self._count_mode = count
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, payload, *, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def execute(self):
        self.db.ops.append((self._op, self.name, {
            "payload": self._payload,
            "filters": list(self._filters),
            "on_conflict": self._on_conflict,
        }))
        if self._op == "insert" and self.name in self.db.insert_returns:
            ids = self.db.insert_returns[self.name]
            payloads = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            returned = [{"id": ids.pop(0), **p} for p in payloads]
            if not isinstance(self._payload, list):
                returned = returned[:1]
            return SimpleNamespace(data=returned, count=None)
        scripted = self.db.responses.get((self._op, self.name))
        data = scripted.pop(0) if scripted else []
        count = len(data) if isinstance(data, list) else None
        return SimpleNamespace(data=data, count=count)


def _embed(_text: str) -> list[float]:
    return [0.0] * 1536


# ---------------------------------------------------------------------------
# Fixtures — build a tiny content tree
# ---------------------------------------------------------------------------


def _make_tree(tmp_path: Path) -> Path:
    """Three files: one flat, one nested, one to mutate for idempotency tests."""
    root = tmp_path / "course_content"
    root.mkdir()
    (root / "FOUNDATION MODULE").mkdir()
    (root / "TRAFFIC ACQUISITION MODULE").mkdir()
    (root / "TRAFFIC ACQUISITION MODULE" / "COLD CALLING").mkdir()

    (root / "FOUNDATION MODULE" / "lesson_a.html").write_text(
        "<html><body><h1>Lesson A</h1><p>Short content for A.</p></body></html>",
        encoding="utf-8",
    )
    (root / "TRAFFIC ACQUISITION MODULE" / "COLD CALLING" / "lesson_b.html").write_text(
        "<html><body><h1>Lesson B</h1><p>Cold calling basics go here.</p></body></html>",
        encoding="utf-8",
    )
    (root / "FOUNDATION MODULE" / "lesson_c.html").write_text(
        "<html><body><h1>Lesson C</h1><p>Version one of lesson C.</p></body></html>",
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# First-ingest path
# ---------------------------------------------------------------------------


def test_first_ingest_inserts_document_and_chunks(tmp_path):
    root = _make_tree(tmp_path)
    db = _FakeDB()
    db.respond("select", "documents", [])   # no existing doc
    db.insert_returning("documents", ["doc-1"])

    outcome = pipeline.ingest_file(
        root / "FOUNDATION MODULE" / "lesson_a.html",
        content_root=root,
        db=db,
        embed_fn=_embed,
        dry_run=False,
    )

    assert outcome.action == "inserted"
    assert outcome.document_id == "doc-1"
    assert outcome.tags == ["module_foundation", "v1_content"]
    assert outcome.chunks_written >= 1
    assert outcome.title == "Lesson A"

    upsert_ops = [op for op in db.ops if op[0] == "upsert" and op[1] == "document_chunks"]
    assert upsert_ops, "expected at least one chunk upsert"


# ---------------------------------------------------------------------------
# Idempotent re-ingest
# ---------------------------------------------------------------------------


def test_reingest_same_hash_skips_embedding(tmp_path):
    root = _make_tree(tmp_path)
    path = root / "FOUNDATION MODULE" / "lesson_a.html"
    import hashlib
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    db = _FakeDB()
    # Pre-existing doc with the SAME hash
    db.respond("select", "documents", [{
        "id": "doc-existing",
        "is_active": True,
        "metadata": {"source_content_hash": content_hash},
    }])
    # count response for _count_chunks
    db.respond("select", "document_chunks", [{"id": "ch1"}])

    outcome = pipeline.ingest_file(
        path, content_root=root, db=db, embed_fn=_embed, dry_run=False,
    )

    assert outcome.action == "skipped_unchanged"
    assert outcome.document_id == "doc-existing"
    chunk_writes = [op for op in db.ops if op[1] == "document_chunks" and op[0] in ("upsert", "insert")]
    assert chunk_writes == [], "expected NO chunk writes on unchanged re-ingest"


def test_reingest_changed_hash_deletes_and_reinserts_chunks(tmp_path):
    root = _make_tree(tmp_path)
    path = root / "FOUNDATION MODULE" / "lesson_a.html"

    db = _FakeDB()
    db.respond("select", "documents", [{
        "id": "doc-existing",
        "is_active": True,
        "metadata": {"source_content_hash": "old_hash_differs"},
    }])

    outcome = pipeline.ingest_file(
        path, content_root=root, db=db, embed_fn=_embed, dry_run=False,
    )

    assert outcome.action == "updated_content_changed"
    assert outcome.document_id == "doc-existing"
    # document was updated and chunks deleted + re-inserted
    updates = [op for op in db.ops if op[0] == "update" and op[1] == "documents"]
    deletes = [op for op in db.ops if op[0] == "delete" and op[1] == "document_chunks"]
    upserts = [op for op in db.ops if op[0] == "upsert" and op[1] == "document_chunks"]
    assert len(updates) == 1
    assert len(deletes) == 1
    assert len(upserts) >= 1


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_touch_db(tmp_path):
    root = _make_tree(tmp_path)
    path = root / "FOUNDATION MODULE" / "lesson_a.html"
    db = _FakeDB()

    outcome = pipeline.ingest_file(
        path, content_root=root, db=db, embed_fn=_embed, dry_run=True,
    )
    assert outcome.action == "dry-run"
    assert outcome.document_id is None
    assert db.ops == []


# ---------------------------------------------------------------------------
# Nested folder → section tag resolution path integration
# ---------------------------------------------------------------------------


def test_nested_file_produces_section_tag(tmp_path):
    root = _make_tree(tmp_path)
    path = root / "TRAFFIC ACQUISITION MODULE" / "COLD CALLING" / "lesson_b.html"
    db = _FakeDB()
    db.respond("select", "documents", [])
    db.insert_returning("documents", ["doc-new"])

    outcome = pipeline.ingest_file(
        path, content_root=root, db=db, embed_fn=_embed, dry_run=False,
    )

    assert outcome.tags == [
        "module_traffic_acquisition", "section_cold_calling", "v1_content"
    ]
    assert outcome.external_id == "TRAFFIC ACQUISITION MODULE/COLD CALLING/lesson_b.html"


# ---------------------------------------------------------------------------
# NOT IN USE flag — is_active=false + not_in_use tag
# ---------------------------------------------------------------------------


def test_not_in_use_file_inserts_with_is_active_false_and_tag(tmp_path):
    root = _make_tree(tmp_path)
    retired = root / "SALES PROCESS MODULE"
    retired.mkdir(exist_ok=True)
    path = retired / "NOT IN USE - 39 - Retired Lesson.html"
    path.write_text(
        "<html><body><h1>Retired Lesson</h1><p>Old content.</p></body></html>",
        encoding="utf-8",
    )

    db = _FakeDB()
    db.respond("select", "documents", [])
    db.insert_returning("documents", ["doc-retired"])

    outcome = pipeline.ingest_file(
        path, content_root=root, db=db, embed_fn=_embed, dry_run=False,
    )

    assert outcome.action == "inserted"
    assert "not_in_use" in outcome.tags
    # The document row insert carries is_active=false
    inserts = [op for op in db.ops if op[0] == "insert" and op[1] == "documents"]
    assert len(inserts) == 1
    assert inserts[0][2]["payload"]["is_active"] is False


def test_active_file_unchanged_by_not_in_use_logic(tmp_path):
    root = _make_tree(tmp_path)
    db = _FakeDB()
    db.respond("select", "documents", [])
    db.insert_returning("documents", ["doc-active"])

    outcome = pipeline.ingest_file(
        root / "FOUNDATION MODULE" / "lesson_a.html",
        content_root=root, db=db, embed_fn=_embed, dry_run=False,
    )
    assert outcome.action == "inserted"
    assert "not_in_use" not in outcome.tags
    inserts = [op for op in db.ops if op[0] == "insert" and op[1] == "documents"]
    assert inserts[0][2]["payload"]["is_active"] is True


def test_is_not_in_use_detection_cases(tmp_path):
    from pathlib import Path as P
    assert pipeline._is_not_in_use(P("/x/NOT IN USE 5.html")) is True
    assert pipeline._is_not_in_use(P("/x/NOT IN USE - 39 - blah.html")) is True
    assert pipeline._is_not_in_use(P("/x/not in use 10.html")) is True
    assert pipeline._is_not_in_use(P("/x/Not In Use Today.html")) is True  # prefix still matches
    assert pipeline._is_not_in_use(P("/x/Lesson About Not Using X.html")) is False
    assert pipeline._is_not_in_use(P("/x/lesson.html")) is False


# ---------------------------------------------------------------------------
# Cost estimate
# ---------------------------------------------------------------------------


def test_estimate_embedding_cost_is_small():
    cost = pipeline.estimate_embedding_cost_usd(1000)
    assert 0 < cost < 1.0
