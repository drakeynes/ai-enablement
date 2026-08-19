"""Structural validation tests for the dc_intel synthesis parsers (0152)."""

from __future__ import annotations

import json

import pytest

from agents.dc_intel.exec_summary import _parse_and_validate
from agents.dc_intel.rep_coaching import _parse_recs

_EXEC_OK = {
    "going_well": ["Opt-ins held at 74 vs the 68 baseline."],
    "going_wrong": ["HVC→close fell to 1/16."],
    "traffic_or_sales": "Sales-side: lead quality avg 6.1 vs rep execution 4.2.",
    "changed": [],
}


def test_exec_accepts_valid_payload():
    parsed = _parse_and_validate(json.dumps(_EXEC_OK), "2026-08-18")
    assert parsed["going_well"] == _EXEC_OK["going_well"]
    assert parsed["changed"] == []


def test_exec_strips_fences_and_caps_items():
    payload = {**_EXEC_OK, "going_well": [f"win {i}" for i in range(9)]}
    parsed = _parse_and_validate(f"```json\n{json.dumps(payload)}\n```", "2026-08-18")
    assert len(parsed["going_well"]) == 4


def test_exec_drops_retired_test_next_key():
    # exec-v1 emitted test_next; exec-v2 retired it. A model that still
    # emits it must not leak it into the stored summary.
    payload = {**_EXEC_OK, "test_next": ["Test a payday-timed callback block."]}
    parsed = _parse_and_validate(json.dumps(payload), "2026-08-18")
    assert "test_next" not in parsed


def test_exec_rejects_missing_keys():
    bad = {k: v for k, v in _EXEC_OK.items() if k != "traffic_or_sales"}
    with pytest.raises(RuntimeError, match="missing keys"):
        _parse_and_validate(json.dumps(bad), "2026-08-18")


def test_recs_accepts_and_caps():
    payload = {
        "recommendations": [
            {"focus": f"focus {i}", "why": "w", "drill": "d"} for i in range(5)
        ]
    }
    recs = _parse_recs(json.dumps(payload), "Jake")
    assert len(recs) == 3
    assert recs[0]["focus"] == "focus 0"


def test_recs_rejects_empty():
    with pytest.raises(RuntimeError, match="recommendations"):
        _parse_recs(json.dumps({"recommendations": []}), "Jake")


def test_recs_drops_malformed_items():
    payload = {"recommendations": [{"focus": ""}, {"focus": "real one"}]}
    recs = _parse_recs(json.dumps(payload), "Jake")
    assert recs == [{"focus": "real one", "why": "", "drill": ""}]
