"""Unit tests for shared.db.

Mocked — does not open a real Supabase connection.
"""

from __future__ import annotations

import pytest

from shared import db


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure each test sees a fresh client cache."""
    db.get_client.cache_clear()
    yield
    db.get_client.cache_clear()


def test_get_client_uses_env_vars_and_caches(monkeypatch, mocker):
    monkeypatch.setenv("SUPABASE_URL", "http://example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    fake_client = object()
    create = mocker.patch("shared.db.create_client", return_value=fake_client)

    first = db.get_client()
    second = db.get_client()

    assert first is fake_client
    assert second is fake_client
    create.assert_called_once_with("http://example.test", "test-key")


def test_get_client_raises_when_env_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        db.get_client()
