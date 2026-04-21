"""Unit tests for scripts/seed_clients.py.

Pure-function tests only — no DB, no sheet IO.
"""

from __future__ import annotations

import pytest

from scripts import seed_clients as sc


# ---------------------------------------------------------------------------
# normalize_email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Foo@Bar.com ", "foo@bar.com"),
        ("no-at-sign", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert sc.normalize_email(raw) == expected


# ---------------------------------------------------------------------------
# derive_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Active", "active"),
        ("Churn", "churned"),
        ("Churn (Aus)", "churned"),
        ("Paused", "paused"),
        ("Paused (Leave)", "paused"),
        ("Ghost", "ghost"),
        ("N/A", "active"),
        ("", "active"),
        (None, "active"),
        ("  active  ", "active"),
        ("Unknown label", "active"),
    ],
)
def test_derive_status(raw, expected):
    assert sc.derive_status(raw) == expected


# ---------------------------------------------------------------------------
# derive_tags
# ---------------------------------------------------------------------------


def test_derive_tags_promoter_usa():
    tags = sc.derive_tags("active", standing="Happy", nps_standing="Promoter", is_aus=False)
    assert "promoter" in tags
    assert "at_risk" not in tags
    assert "aus" not in tags


def test_derive_tags_detractor_becomes_at_risk_and_detractor():
    tags = sc.derive_tags(
        "active", standing="Owing Money", nps_standing="Detractor / At Risk", is_aus=False
    )
    assert "at_risk" in tags
    assert "detractor" in tags
    assert "owing_money" in tags


def test_derive_tags_standing_contains_at_risk_sets_tag():
    tags = sc.derive_tags("active", standing="At risk, Owing Money", nps_standing=None, is_aus=False)
    assert "at_risk" in tags
    assert "owing_money" in tags


def test_derive_tags_churned_and_aus():
    tags = sc.derive_tags("churned", standing="N/A (Churn)", nps_standing=None, is_aus=True)
    assert "churned" in tags
    assert "aus" in tags


def test_derive_tags_nps_trailing_whitespace_still_matches():
    # NPS Standing values in the real sheet carry trailing spaces; the
    # transform trims before comparison.
    tags = sc.derive_tags("active", standing=None, nps_standing="Detractor / At Risk ", is_aus=False)
    assert "detractor" in tags
    assert "at_risk" in tags


# ---------------------------------------------------------------------------
# parse_owner
# ---------------------------------------------------------------------------


def test_parse_owner_clean_match():
    parsed = sc.parse_owner("Lou")
    assert parsed.team_email == "lou@theaipartner.io"
    assert parsed.is_clean_match is True


def test_parse_owner_trailing_space_is_clean():
    # "Nico " in the real sheet — trims to a clean match
    parsed = sc.parse_owner("Nico ")
    assert parsed.team_email == "nico@theaipartner.io"
    assert parsed.is_clean_match is True


def test_parse_owner_messy_takes_first_name_and_keeps_raw():
    parsed = sc.parse_owner("Lou (Scott Chasing)")
    assert parsed.team_email == "lou@theaipartner.io"
    assert parsed.is_clean_match is False
    assert parsed.raw == "Lou (Scott Chasing)"


def test_parse_owner_arrow_pattern_takes_first_named():
    parsed = sc.parse_owner("Lou > Nico?")
    assert parsed.team_email == "lou@theaipartner.io"
    assert parsed.is_clean_match is False


def test_parse_owner_unmapped_returns_none_with_raw():
    parsed = sc.parse_owner("Aleks")
    assert parsed.team_email is None
    assert parsed.raw == "Aleks"


@pytest.mark.parametrize("raw", ["N/A", "", None])
def test_parse_owner_blankish_returns_none_clean(raw):
    parsed = sc.parse_owner(raw)
    if raw == "N/A":
        # Not a mappable owner, raw preserved for reporting
        assert parsed.team_email is None
        assert parsed.raw == "N/A"
    else:
        assert parsed.team_email is None
        assert parsed.is_clean_match is True
        assert parsed.raw is None


# ---------------------------------------------------------------------------
# is_aggregate_row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("TOTALS", True),
        ("  totals  ", True),
        ("UF Collection Rate", True),
        ("Total Active Clients", True),
        ("Retention", True),
        ("Referrals", True),
        ("Jane Doe", False),
        (None, False),
        ("", False),
    ],
)
def test_is_aggregate_row(raw, expected):
    assert sc.is_aggregate_row(raw) is expected


def test_load_sheet_rows_filters_aggregates(tmp_path):
    import openpyxl as _openpyxl
    xlsx = tmp_path / "sheet.xlsx"
    wb = _openpyxl.Workbook()
    ws = wb.active
    ws.title = "USA TOTALS"
    ws.append(["Customer Name", "Client Emails", "Status", "Owner "])
    ws.append(["Real Client", "rc@example.com", "Active", "Lou"])
    ws.append(["Client No Email", None, "Active", "Lou"])  # skipped for missing email, not aggregate
    ws.append(["TOTALS", None, None, None])                 # aggregate
    ws.append(["UF Collection Rate", None, None, None])     # aggregate
    aus = wb.create_sheet("AUS TOTALS")
    aus.append(["Customer Name", "Client Emails", "Status", "Owner "])
    wb.save(xlsx)

    rows, aggregate_count = sc.load_sheet_rows(xlsx)

    assert aggregate_count == 2
    # Two rows survive the filter: Real Client and Client No Email.
    # The missing-email one still gets to the next stage so it shows up in the
    # skipped-missing-email report.
    assert len(rows) == 2
    assert {r.values["customer name"] for r in rows} == {"Real Client", "Client No Email"}


# ---------------------------------------------------------------------------
# build_client_payload — skip-missing-email rule
# ---------------------------------------------------------------------------


def _row(**overrides):
    base = {
        "customer name": "Jane Doe",
        "client emails": "jane@example.com",
        "client phone no.": "+15551234567",
        "slack user id": None,
        "date": None,
        "status": "Active",
        "standing": None,
        "nps standing": None,
        "owner": "Lou",
        "contracted rev": 9000,
    }
    base.update(overrides)
    return base


def test_build_client_payload_happy_path():
    payload = sc.build_client_payload(_row(), country="USA", seeded_at_iso="2026-04-21")
    assert payload is not None
    assert payload["email"] == "jane@example.com"
    assert payload["full_name"] == "Jane Doe"
    assert payload["status"] == "active"
    assert payload["metadata"]["country"] == "USA"
    assert payload["metadata"]["seeded_at"] == "2026-04-21"
    assert set(payload["metadata"].keys()) == {
        "seed_source", "seeded_at", "country", "standing", "nps_standing", "owner_raw"
    }


def test_build_client_payload_omits_revenue_fields():
    """Revenue fields in the sheet are stale (per Scott) and must not leak
    into clients.metadata. The schema of the metadata blob is fixed to the
    six keys above; no contracted_revenue* keys ever."""
    row = _row(**{"contracted rev": 9000, "contracted rev aud": 12000})
    payload = sc.build_client_payload(row, country="USA", seeded_at_iso="2026-04-21")
    assert payload is not None
    assert "contracted_revenue_usd" not in payload["metadata"]
    assert "contracted_revenue" not in payload["metadata"]
    assert "contracted_revenue_currency" not in payload["metadata"]


def test_build_client_payload_skips_missing_email():
    assert sc.build_client_payload(
        _row(**{"client emails": None}), country="USA", seeded_at_iso="2026-04-21"
    ) is None
    assert sc.build_client_payload(
        _row(**{"client emails": "   "}), country="USA", seeded_at_iso="2026-04-21"
    ) is None


def test_build_client_payload_aus_tag_without_revenue():
    row = _row()
    payload = sc.build_client_payload(row, country="AUS", seeded_at_iso="2026-04-21")
    assert payload is not None
    assert payload["metadata"]["country"] == "AUS"
    assert "aus" in payload["tags"]


# ---------------------------------------------------------------------------
# apply_log_breakdowns
# ---------------------------------------------------------------------------


def test_apply_log_breakdowns_counts_status_journey_and_tags(mocker):
    fake_rows = [
        {"status": "active",  "journey_stage": "onboarding", "tags": ["promoter"]},
        {"status": "active",  "journey_stage": None,         "tags": ["promoter", "aus"]},
        {"status": "churned", "journey_stage": None,         "tags": ["churned"]},
        {"status": "paused",  "journey_stage": None,         "tags": []},
    ]
    fake_db = mocker.MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = fake_rows

    out = sc.apply_log_breakdowns(fake_db)

    assert "Breakdowns across 4 active clients" in out
    assert "active" in out and "churned" in out and "paused" in out
    assert "promoter" in out and "aus" in out
    assert "(null)" in out  # journey_stage is mostly null


# ---------------------------------------------------------------------------
# Dry-run vs apply separation — the main() script short-circuits on no --apply
# ---------------------------------------------------------------------------


def test_main_dry_run_does_not_call_apply_paths(mocker, tmp_path):
    # Craft a trivial sheet
    xlsx = tmp_path / "sheet.xlsx"
    import openpyxl as _openpyxl
    wb = _openpyxl.Workbook()
    ws = wb.active
    ws.title = "USA TOTALS"
    ws.append(["Customer Name", "Client Emails", "Status", "Owner "])
    ws.append(["Test Client", "tc@example.com", "Active", "Lou"])
    aus = wb.create_sheet("AUS TOTALS")
    aus.append(["Customer Name", "Client Emails", "Status", "Owner "])
    wb.save(xlsx)

    fake_db = mocker.MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.in_.return_value.execute.return_value.data = []
    mocker.patch("scripts.seed_clients.get_client", return_value=fake_db)
    apply_clients_spy = mocker.patch("scripts.seed_clients.apply_clients")

    rc = sc.main(["--input", str(xlsx)])

    assert rc == 0
    apply_clients_spy.assert_not_called()


def test_main_apply_calls_apply_paths(mocker, tmp_path):
    xlsx = tmp_path / "sheet.xlsx"
    import openpyxl as _openpyxl
    wb = _openpyxl.Workbook()
    ws = wb.active
    ws.title = "USA TOTALS"
    ws.append(["Customer Name", "Client Emails", "Status", "Owner "])
    ws.append(["Test Client", "tc@example.com", "Active", "Lou"])
    aus = wb.create_sheet("AUS TOTALS")
    aus.append(["Customer Name", "Client Emails", "Status", "Owner "])
    wb.save(xlsx)

    fake_db = mocker.MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.in_.return_value.execute.return_value.data = []
    mocker.patch("scripts.seed_clients.get_client", return_value=fake_db)
    apply_clients_spy = mocker.patch(
        "scripts.seed_clients.apply_clients", return_value=({"tc@example.com": "id-1"}, 1, 0)
    )
    mocker.patch(
        "scripts.seed_clients.resolve_team_member_ids",
        return_value={"lou@theaipartner.io": "tm-lou"},
    )
    mocker.patch("scripts.seed_clients.apply_channels", return_value=0)
    mocker.patch("scripts.seed_clients.apply_assignments", return_value=1)
    mocker.patch("scripts.seed_clients.apply_log_breakdowns", return_value="(breakdown)")
    mocker.patch("scripts.seed_clients.write_log")

    rc = sc.main(["--input", str(xlsx), "--apply"])

    assert rc == 0
    apply_clients_spy.assert_called_once()
