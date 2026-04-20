"""Unit tests for shared.claude_client.

Mocked — does not call the Anthropic API or Supabase.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from shared import claude_client


@pytest.fixture(autouse=True)
def _reset_client_cache():
    claude_client._anthropic_client.cache_clear()
    yield
    claude_client._anthropic_client.cache_clear()


def _fake_message(text: str, input_tokens: int, output_tokens: int):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_estimate_cost_known_model():
    # 1M input @ $3 + 0.5M output @ $15 = $3 + $7.5 = $10.5
    cost = claude_client.estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 500_000)
    assert cost == Decimal("10.50")


def test_estimate_cost_unknown_model_returns_zero():
    assert claude_client.estimate_cost_usd("not-a-real-model", 1000, 500) == Decimal("0")


def test_complete_returns_result_and_skips_db_when_no_run_id(mocker):
    fake_api = mocker.MagicMock()
    fake_api.messages.create.return_value = _fake_message("hi", 100, 20)
    mocker.patch("shared.claude_client._anthropic_client", return_value=fake_api)
    db_spy = mocker.patch("shared.claude_client.get_client")

    result = claude_client.complete(
        system="sys", messages=[{"role": "user", "content": "hello"}]
    )

    assert result.text == "hi"
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.model == claude_client.DEFAULT_MODEL
    assert result.cost_usd > Decimal("0")
    db_spy.assert_not_called()


def test_complete_writes_llm_usage_when_run_id_provided(mocker):
    fake_api = mocker.MagicMock()
    fake_api.messages.create.return_value = _fake_message("ok", 500, 40)
    mocker.patch("shared.claude_client._anthropic_client", return_value=fake_api)

    fake_db = mocker.MagicMock()
    mocker.patch("shared.claude_client.get_client", return_value=fake_db)

    claude_client.complete(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        run_id="run-abc",
    )

    fake_db.table.assert_called_with("agent_runs")
    update_call = fake_db.table.return_value.update.call_args[0][0]
    assert update_call["llm_model"] == claude_client.DEFAULT_MODEL
    assert update_call["llm_input_tokens"] == 500
    assert update_call["llm_output_tokens"] == 40
    assert Decimal(update_call["llm_cost_usd"]) > Decimal("0")
    fake_db.table.return_value.update.return_value.eq.assert_called_with("id", "run-abc")
