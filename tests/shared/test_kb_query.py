"""Unit tests for shared.kb_query.

Mocked — does not call OpenAI or Supabase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from shared import kb_query


@pytest.fixture(autouse=True)
def _reset_caches():
    kb_query._openai_client.cache_clear()
    kb_query._embed_cached.cache_clear()
    yield
    kb_query._openai_client.cache_clear()
    kb_query._embed_cached.cache_clear()


def _fake_embedding_response(vec):
    return SimpleNamespace(data=[SimpleNamespace(embedding=list(vec))])


def _sample_row(**overrides):
    base = {
        "chunk_id": "c1",
        "document_id": "d1",
        "document_type": "faq",
        "document_title": "FAQ 1",
        "document_created_at": datetime.now(timezone.utc).isoformat(),
        "content": "hello",
        "chunk_index": 0,
        "similarity": 0.87,
        "metadata": {"tag": "x"},
    }
    base.update(overrides)
    return base


class _RpcResult:
    def __init__(self, data):
        self.data = data


def _mock_rpc(mocker, rows):
    fake_db = mocker.MagicMock()
    fake_db.rpc.return_value.execute.return_value = _RpcResult(rows)
    mocker.patch("shared.kb_query.get_client", return_value=fake_db)
    return fake_db


def _mock_openai(mocker, vec=(0.1,) * kb_query.EMBEDDING_DIMENSIONS):
    fake_openai = mocker.MagicMock()
    fake_openai.embeddings.create.return_value = _fake_embedding_response(vec)
    mocker.patch("shared.kb_query._openai_client", return_value=fake_openai)
    return fake_openai


def test_embed_caches_same_text(mocker):
    fake_openai = _mock_openai(mocker)

    v1 = kb_query.embed("hello")
    v2 = kb_query.embed("hello")

    assert v1 == v2
    assert fake_openai.embeddings.create.call_count == 1


def test_search_global_passes_null_client_and_maps_rows(mocker):
    _mock_openai(mocker)
    fake_db = _mock_rpc(mocker, [_sample_row(chunk_id="c1"), _sample_row(chunk_id="c2")])

    results = kb_query.search_global(
        "how do I start?", k=5, document_types=["faq", "course_lesson"]
    )

    assert [c.chunk_id for c in results] == ["c1", "c2"]
    args = fake_db.rpc.call_args
    assert args[0][0] == "match_document_chunks"
    params = args[0][1]
    assert params["client_id"] is None
    assert params["match_count"] == 5
    assert params["document_types"] == ["faq", "course_lesson"]
    assert params["include_global"] is True


def test_search_for_client_passes_client_id_and_include_global_default(mocker):
    _mock_openai(mocker)
    fake_db = _mock_rpc(mocker, [_sample_row()])

    kb_query.search_for_client("recap", client_id="client-123", k=6)

    params = fake_db.rpc.call_args[0][1]
    assert params["client_id"] == "client-123"
    assert params["match_count"] == 6
    assert params["include_global"] is True


def test_search_for_client_can_exclude_global(mocker):
    _mock_openai(mocker)
    fake_db = _mock_rpc(mocker, [])

    kb_query.search_for_client(
        "recap", client_id="client-123", include_global=False
    )

    params = fake_db.rpc.call_args[0][1]
    assert params["include_global"] is False


def test_row_to_chunk_parses_timestamp_and_floats():
    ts = "2026-04-20T12:34:56+00:00"
    row = _sample_row(document_created_at=ts, similarity="0.75")
    chunk = kb_query._row_to_chunk(row)

    assert chunk.document_created_at == datetime.fromisoformat(ts)
    assert isinstance(chunk.similarity, float)
    assert chunk.similarity == pytest.approx(0.75)
    assert chunk.metadata == {"tag": "x"}
