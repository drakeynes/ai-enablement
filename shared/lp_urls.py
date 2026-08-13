"""DC landing-page URL identity — shared by the Meta and Wistia ingestion.

The `dc_landing_pages` registry (migration 0132) keys landing pages by their
NORMALIZED URL, and the DC Ads page names them by a SHORT form of that URL
('join/training', 'go') — Drake 2026-08-13: LPs are identified by their actual
URLs, like the Advertising Hub's labels, never by the Close funnel name.

Two ingestion adapters consume this identity, which is why it lives in shared/:
  - ingestion/meta_ads — a campaign's creative destination URL → registry row
    (auto-created when unseen) + `dc_ads_campaigns.lp_slug`.
  - ingestion/wistia — a video view event's embed URL → registry row, to
    auto-attach videos to the landing page they play on.

Normalization must be IDENTICAL on both sides or the join silently misses:
lowercase host, strip scheme / www. / port / query / fragment / trailing
slash. 'https://go.digitalcollege.ai/?utm_source=fb' → 'go.digitalcollege.ai'.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# The Digital College landing-page domain(s). The Closer Funnel motion runs on
# theaipartner.io against the SAME ad account — never add it here (see
# docs/schema/dc_ads_campaigns.md).
DC_LANDING_HOSTS: tuple[str, ...] = ("digitalcollege.ai",)


def normalize_lp_url(url: str) -> str:
    """'https://Join.DigitalCollege.ai/training/?x=1#f' → 'join.digitalcollege.ai/training'."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    host = host.removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


def lp_short_label(
    normalized_url: str, domains: tuple[str, ...] = DC_LANDING_HOSTS
) -> str:
    """The dropdown-facing short name: subdomain + path, shared domain stripped.

    'join.digitalcollege.ai/training' → 'join/training'
    'go.digitalcollege.ai'            → 'go'
    'digitalcollege.ai/offer'         → 'offer'
    Anything not under `domains` keeps its full host ('example.com/lp').
    """
    host, _, path = normalized_url.partition("/")
    for domain in domains:
        if host == domain:
            host = ""
            break
        if host.endswith("." + domain):
            host = host[: -len(domain) - 1]
            break
    parts = [p for p in (host, path) if p]
    return "/".join(parts) if parts else normalized_url


def lp_slugify(label: str) -> str:
    """'join/training' → 'join-training' (dc_landing_pages.slug / URL-param safe)."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
