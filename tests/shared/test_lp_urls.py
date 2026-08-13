"""shared/lp_urls — the DC landing-page URL identity.

Normalization is load-bearing on BOTH sides of a join (campaign destination
URLs from Meta creatives vs video embed URLs from Wistia events) — a drift
between the two silently detaches videos/campaigns from their landing page.
"""

from shared.lp_urls import (
    DC_LANDING_HOSTS,
    lp_short_label,
    lp_slugify,
    normalize_lp_url,
)


def test_normalize_strips_scheme_query_fragment_and_trailing_slash():
    assert (
        normalize_lp_url("https://join.digitalcollege.ai/training/?utm_source=fb#top")
        == "join.digitalcollege.ai/training"
    )


def test_normalize_lowercases_host_and_drops_www_and_port():
    assert (
        normalize_lp_url("HTTPS://WWW.Go.DigitalCollege.ai:443/")
        == "go.digitalcollege.ai"
    )


def test_normalize_accepts_already_bare_urls():
    # The registry stores normalized URLs; re-normalizing must be idempotent.
    assert normalize_lp_url("go.digitalcollege.ai") == "go.digitalcollege.ai"


def test_normalize_collapses_meta_utm_variants_to_one_key():
    variants = [
        "https://join.digitalcollege.ai/training",
        "https://join.digitalcollege.ai/training?utm_source=an&utm_campaign=08%2F12",
        "https://join.digitalcollege.ai/training?utm_source=ig&utm_medium=Instagram_Reels",
    ]
    assert {normalize_lp_url(v) for v in variants} == {
        "join.digitalcollege.ai/training"
    }


def test_short_label_is_subdomain_plus_path():
    assert lp_short_label("join.digitalcollege.ai/training") == "join/training"


def test_short_label_subdomain_only_for_root_page():
    assert lp_short_label("go.digitalcollege.ai") == "go"


def test_short_label_apex_domain_uses_path():
    assert lp_short_label("digitalcollege.ai/offer") == "offer"


def test_short_label_keeps_foreign_hosts_whole():
    # Non-DC hosts shouldn't be shortened into ambiguity.
    assert lp_short_label("example.com/lp") == "example.com/lp"


def test_slugify_matches_seeded_registry_slugs():
    # The 0132 seeds were derived with exactly this rule.
    assert (
        lp_slugify(lp_short_label("join.digitalcollege.ai/training")) == "join-training"
    )
    assert lp_slugify(lp_short_label("go.digitalcollege.ai")) == "go"


def test_dc_hosts_never_include_the_closer_funnel_domain():
    # theaipartner.io is the separate Closer Funnel motion on the same ad
    # account; sweeping it in would corrupt DC spend (docs/schema/dc_ads_campaigns.md).
    assert "theaipartner.io" not in DC_LANDING_HOSTS
