"""leads_parser: real API shapes (captured live 2026-07-10) → mirror rows."""

from ingestion.meta_ads.leads_parser import (
    creative_destination_urls,
    parse_form,
    parse_landing_page_ad,
    parse_lead,
    parse_leadgen_adset,
)

PAGE_ID = "627212320483048"
ACCOUNT_ID = "act_2293461684485411"

# Captured verbatim from GET /{page_id}/leadgen_forms on 2026-07-10.
FORM_ROW = {
    "id": "1053168367400164",
    "name": "7/8 - Basic Form",
    "status": "ACTIVE",
    "created_time": "2026-07-08T16:29:08+0000",
    "questions": [
        {
            "key": "full_name",
            "label": "Full name",
            "type": "FULL_NAME",
            "id": "1028104442919792",
        },
        {
            "key": "phone_number",
            "label": "Phone number",
            "type": "PHONE",
            "id": "1759976548346776",
        },
    ],
}

# Captured verbatim from GET /{form_id}/leads on 2026-07-10.
LEAD_ROW = {
    "id": "1224990839685018",
    "created_time": "2026-07-10T03:40:05+0000",
    "ad_id": "120249698637820748",
    "ad_name": "07/08 | Img1",
    "adset_id": "120249698637810748",
    "adset_name": "07/08 | Img1 | ABO - Copy 2",
    "campaign_id": "120249697320740748",
    "campaign_name": "07/08 | Test Batch 1 + Old Ads | LeadForm | Wix Funnel",
    "form_id": "1053168367400164",
    "is_organic": False,
    "platform": "fb",
    "field_data": [
        {"name": "phone_number", "values": ["+17086688748"]},
        {"name": "full_name", "values": ["Sharon McKinney"]},
    ],
}

# Captured verbatim from GET /act_<id>/adsets on 2026-07-10: one instant-form
# adset (the discriminator) and one old website-funnel adset.
LEADGEN_ADSET_ROW = {
    "id": "120249698637810748",
    "name": "07/08 | Img1 | ABO - Copy 2",
    "campaign_id": "120249697320740748",
    "campaign": {
        "id": "120249697320740748",
        "name": "07/08 | Test Batch 1 + Old Ads | LeadForm | Wix Funnel",
    },
    "destination_type": "ON_AD",
    "optimization_goal": "LEAD_GENERATION",
    "promoted_object": {"page_id": "627212320483048", "smart_pse_enabled": False},
}
WEBSITE_ADSET_ROW = {
    "id": "120248128714170748",
    "name": "Broad",
    "campaign_id": "120248128714030748",
    "campaign": {"id": "120248128714030748", "name": "6/13/26 | … | Closer Funnel"},
    "destination_type": "WEBSITE",
    "optimization_goal": "OFFSITE_CONVERSIONS",
}


def test_parse_form_maps_registry_row():
    row = parse_form(FORM_ROW, PAGE_ID)
    assert row["form_id"] == "1053168367400164"
    assert row["page_id"] == PAGE_ID
    assert row["name"] == "7/8 - Basic Form"
    assert row["status"] == "ACTIVE"
    assert row["form_created_time"] == "2026-07-08T16:29:08+0000"
    assert [q["key"] for q in row["questions"]] == ["full_name", "phone_number"]
    assert row["raw"] == FORM_ROW


def test_parse_lead_flattens_identity_and_keeps_attribution():
    row = parse_lead(LEAD_ROW, PAGE_ID)
    assert row["lead_id"] == "1224990839685018"
    assert row["form_id"] == "1053168367400164"
    assert row["created_time"] == "2026-07-10T03:40:05+0000"
    # Attribution ids join cortana_*_daily.platform_entity_id + close_leads.
    assert row["ad_id"] == "120249698637820748"
    assert row["adset_id"] == "120249698637810748"
    assert row["campaign_id"] == "120249697320740748"
    assert row["is_organic"] is False
    assert row["platform"] == "fb"
    # field_data flattened regardless of answer order.
    assert row["full_name"] == "Sharon McKinney"
    assert row["phone_number"] == "+17086688748"
    assert row["email"] is None  # the 7/8 Basic Form collects no email
    assert row["field_data"] == LEAD_ROW["field_data"]


def test_parse_lead_joins_split_name_fields():
    split = dict(
        LEAD_ROW,
        field_data=[
            {"name": "first_name", "values": ["Sharon"]},
            {"name": "last_name", "values": ["McKinney"]},
            {"name": "email", "values": ["s@example.com"]},
        ],
    )
    row = parse_lead(split, PAGE_ID)
    assert row["full_name"] == "Sharon McKinney"
    assert row["email"] == "s@example.com"


def test_parse_lead_tolerates_organic_lead_without_attribution():
    organic = dict(LEAD_ROW, is_organic=True)
    for key in (
        "ad_id",
        "ad_name",
        "adset_id",
        "adset_name",
        "campaign_id",
        "campaign_name",
    ):
        organic.pop(key)
    row = parse_lead(organic, PAGE_ID)
    assert row["is_organic"] is True
    assert row["campaign_id"] is None
    assert row["phone_number"] == "+17086688748"


def test_leadgen_adset_discriminator_accepts_instant_form():
    row = parse_leadgen_adset(LEADGEN_ADSET_ROW, ACCOUNT_ID)
    assert row is not None
    assert row["campaign_id"] == "120249697320740748"
    assert row["campaign_name"].endswith("LeadForm | Wix Funnel")
    assert row["account_id"] == ACCOUNT_ID
    assert row["page_id"] == PAGE_ID
    assert row["last_seen_at"]


def test_leadgen_adset_discriminator_rejects_website_funnel():
    assert parse_leadgen_adset(WEBSITE_ADSET_ROW, ACCOUNT_ID) is None


def test_leadgen_adset_discriminator_requires_both_signals():
    half = dict(LEADGEN_ADSET_ROW, destination_type="WEBSITE")
    assert parse_leadgen_adset(half, ACCOUNT_ID) is None
    other_half = dict(LEADGEN_ADSET_ROW, optimization_goal="OFFSITE_CONVERSIONS")
    assert parse_leadgen_adset(other_half, ACCOUNT_ID) is None


# -- landing-page discriminator (0130) --------------------------------------
# Both rows captured verbatim from GET /{campaign_id}/ads on 2026-08-12. Note
# the DC ad carries its destination ONLY under
# object_story_spec.video_data.call_to_action.value.link — there is no
# link_data.link — which is why the parser digs through every known location.

DC_LANDING_AD_ROW = {
    "id": "120250218014210748",
    "name": "07/25 | Creative 7",
    "campaign_id": "120250217875250748",
    "campaign": {"id": "120250217875250748", "name": "07/25 | Aman TY Vsl | DC funnel"},
    "effective_status": "PAUSED",
    "creative": {
        "id": "1943577862881268",
        "object_story_spec": {
            "page_id": PAGE_ID,
            "video_data": {
                "video_id": "4347257485588781",
                "call_to_action": {
                    "type": "SEE_DETAILS",
                    "value": {"link": "https://join.digitalcollege.ai/training"},
                },
            },
        },
    },
}

# The ANDROMEDA / Closer Funnel motion — same ad account, same Facebook page,
# different product. Must never be claimed by the DC page.
CLOSER_FUNNEL_AD_ROW = {
    "id": "120248128714100748",
    "name": "6/13/26 - Broad - Ad Tracking Image (4)",
    "campaign_id": "120248128714030748",
    "campaign": {
        "id": "120248128714030748",
        "name": "6/13/26 | ANDROMEDA | ... | Closer Funnel - Copy",
    },
    "effective_status": "PAUSED",
    "creative": {
        "id": "1006972555216258",
        "object_story_spec": {
            "page_id": PAGE_ID,
            "link_data": {
                "link": "https://go.theaipartner.io/lp-vsl",
                "call_to_action": {
                    "type": "LEARN_MORE",
                    "value": {"link": "https://go.theaipartner.io/lp-vsl"},
                },
            },
        },
    },
}


def test_landing_page_ad_claims_digital_college():
    row = parse_landing_page_ad(DC_LANDING_AD_ROW)
    assert row is not None
    assert row["campaign_id"] == "120250217875250748"
    assert row["source_kind"] == "landing_page"
    assert row["destination_url"] == "https://join.digitalcollege.ai/training"
    assert row["last_seen_at"]


def test_landing_page_ad_rejects_closer_funnel():
    """The regression that matters: theaipartner.io must not land on the DC page."""
    assert parse_landing_page_ad(CLOSER_FUNNEL_AD_ROW) is None


def test_landing_page_ad_matches_host_not_path():
    """/training exists on BOTH domains — a path-based rule would be wrong."""
    imposter = {
        "campaign_id": "999",
        "creative": {
            "object_story_spec": {
                "link_data": {"link": "https://join.theaipartner.io/training"}
            }
        },
    }
    assert parse_landing_page_ad(imposter) is None


def test_landing_page_ad_matches_subdomains_only_of_configured_host():
    for url, expected in (
        ("https://go.digitalcollege.ai/", True),
        ("https://digitalcollege.ai/x", True),
        ("https://digitalcollege.ai.evil.com/x", False),
        ("https://notdigitalcollege.ai/x", False),
    ):
        row = {
            "campaign_id": "1",
            "creative": {"object_story_spec": {"link_data": {"link": url}}},
        }
        assert (parse_landing_page_ad(row) is not None) is expected, url


def test_landing_page_ad_without_destination_is_ignored():
    assert parse_landing_page_ad({"campaign_id": "1", "creative": {}}) is None
    assert parse_landing_page_ad({"creative": DC_LANDING_AD_ROW["creative"]}) is None


# -- per-ad registry (0146) --------------------------------------------------


def test_parse_meta_ad_claims_dc_landing_ad_with_normalized_destination():
    from ingestion.meta_ads.leads_parser import parse_meta_ad

    row = parse_meta_ad(DC_LANDING_AD_ROW, known_campaign_ids=set())
    assert row is not None
    assert row["ad_id"] == "120250218014210748"
    assert row["ad_name"] == "07/25 | Creative 7"
    assert row["campaign_id"] == "120250217875250748"
    assert row["effective_status"] == "PAUSED"
    # Destination is NORMALIZED (registry join key), unlike the campaign row's.
    assert row["destination_url"] == "join.digitalcollege.ai/training"


def test_parse_meta_ad_keeps_known_campaign_ads_without_dc_destination():
    """Instant-form ads have no LP destination but their campaign is registered."""
    from ingestion.meta_ads.leads_parser import parse_meta_ad

    row = parse_meta_ad(
        {"id": "a1", "campaign_id": "c1", "adset_id": "s1", "creative": {}},
        known_campaign_ids={"c1"},
    )
    assert row is not None
    assert row["destination_url"] is None
    assert row["adset_id"] == "s1"


def test_parse_meta_ad_rejects_closer_funnel_and_unknown_campaigns():
    from ingestion.meta_ads.leads_parser import parse_meta_ad

    assert parse_meta_ad(CLOSER_FUNNEL_AD_ROW, known_campaign_ids=set()) is None
    assert (
        parse_meta_ad({"id": "a1", "creative": {}}, known_campaign_ids={"c1"}) is None
    )


def test_creative_destination_urls_finds_every_location():
    creative = {
        "link_url": "https://digitalcollege.ai/a",
        "object_story_spec": {"link_data": {"link": "https://digitalcollege.ai/b"}},
        "asset_feed_spec": {
            "link_urls": [{"website_url": "https://digitalcollege.ai/c"}]
        },
    }
    assert creative_destination_urls(creative) == {
        "https://digitalcollege.ai/a",
        "https://digitalcollege.ai/b",
        "https://digitalcollege.ai/c",
    }
