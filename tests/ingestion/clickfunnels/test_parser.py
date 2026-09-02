"""Parser tests for the ClickFunnels → typeform_responses projection.

The payload fixture mirrors the first live capture (2026-09-02) with
identity values swapped for synthetic ones.
"""

from __future__ import annotations

from ingestion.clickfunnels.parser import (
    QUALIFY_FIELD_REF,
    form_definition_row,
    form_id_for,
    parse_submission,
)


def _payload(**overrides):
    base = {
        "email": "jane@example.com",
        "phone": "+15551239907",
        "phone_formatted": "+1 (555) 123-9907",
        "name": "Jane",
        "submitted_at": "2026-09-02T19:16:12.000Z",
        "campaign_id": "120251021193170748",
        "adset_id": "120251021193210748",
        "ad_id": "120251021864410748",
        "utm_source": "ig",
        "utm_medium": "Instagram_Reels",
        "utm_campaign": "09/01 | Aman New Vsl | CBO | DC Funnel",
        "utm_content": "09/01 | Why he gives it away",
        "utm_term": "09/01  | Qualifed Leads CBO",
        "fbp": "fb.1.1785878.111",
        "fbc": "fb.1.1788376.222",
        "client_ip_address": "203.0.113.9",
        "client_user_agent": "Mozilla/5.0 test",
        "event_id": "c9ffcf01-b850-4000-8000-000000000001",
        "funnel": "Aman VSL Funnel",
        "page_url": "https://go.digitalcollege.ai/lp-v2?utm_source=ig",
        "has_budget_200": "Yes",
        "medium_id": "120251021193210748",
        "content_id": "120251021864410748",
    }
    base.update(overrides)
    return base


def test_form_id_slugifies_funnel_label():
    assert form_id_for(_payload()) == "cf:aman-vsl-funnel"
    assert form_id_for({"funnel": "  She Sells!! Q4 "}) == "cf:she-sells-q4"
    assert form_id_for({}) == "cf:unlabeled"


def test_parse_full_payload_matches_facts_refresh_paths():
    row = parse_submission(_payload())
    assert row is not None
    assert row["response_id"] == "cf:c9ffcf01-b850-4000-8000-000000000001"
    assert row["form_id"] == "cf:aman-vsl-funnel"
    assert row["submitted_at"] == "2026-09-02T19:16:12.000Z"

    # The exact jsonb paths refresh_dc_ads_facts() (0154) reads:
    by_type = {a["type"]: a for a in row["answers"]}
    assert by_type["phone_number"]["phone_number"] == "+15551239907"
    assert by_type["email"]["email"] == "jane@example.com"
    assert by_type["choice"]["field"]["ref"] == QUALIFY_FIELD_REF
    assert by_type["choice"]["choice"]["label"] == "Yes"

    # Hidden-field contract: attribution ids + identity fallbacks + ip rename.
    hidden = row["hidden"]
    for key in ("campaign_id", "adset_id", "ad_id", "utm_source", "fbp", "fbc",
                "event_id", "funnel", "phone", "email"):
        assert hidden[key], key
    assert hidden["ip"] == "203.0.113.9"
    assert "client_ip_address" not in hidden

    assert row["metadata"]["source"] == "clickfunnels"


def test_yes_no_normalization_and_passthrough():
    for raw, expected in [("yes", "Yes"), ("TRUE", "Yes"), ("1", "Yes"),
                          ("No", "No"), ("false", "No"), ("0", "No")]:
        row = parse_submission(_payload(has_budget_200=raw))
        assert row["answers"][-1]["choice"]["label"] == expected
    # Unknown copy passes through untouched — registry config decides.
    row = parse_submission(_payload(has_budget_200="Absolutely, sign me up"))
    assert row["answers"][-1]["choice"]["label"] == "Absolutely, sign me up"
    # Absent answer → no choice answer emitted at all.
    row = parse_submission(_payload(has_budget_200=""))
    assert [a["type"] for a in row["answers"]] == ["phone_number", "email"]


def test_unusable_payloads_return_none():
    assert parse_submission(_payload(submitted_at="")) is None
    assert parse_submission(_payload(email="", phone="")) is None
    assert parse_submission("not a dict") is None


def test_missing_event_id_hashes_deterministically():
    a = parse_submission(_payload(event_id=""))
    b = parse_submission(_payload(event_id=""))
    assert a["response_id"] == b["response_id"]
    assert a["response_id"].startswith("cf:")
    assert a["response_id"] != parse_submission(_payload(event_id="", email="other@example.com"))["response_id"]


def test_form_definition_row_shape_for_dc_setup_picker():
    row = form_definition_row("cf:aman-vsl-funnel", "Aman VSL Funnel")
    assert row["form_id"] == "cf:aman-vsl-funnel"
    assert "ClickFunnels" in row["title"]
    field = row["fields"][0]
    assert field["ref"] == QUALIFY_FIELD_REF
    labels = [c["label"] for c in field["properties"]["choices"]]
    assert labels == ["Yes", "No"]
    assert "ip" in row["hidden_fields"]
