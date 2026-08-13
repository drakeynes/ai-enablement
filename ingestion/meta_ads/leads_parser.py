"""Map Meta leadgen (instant-form) API rows → mirror-table row dicts.

Three projections, one per table (see migration 0122):
  - `parse_form(row, page_id)`        → `meta_lead_forms` row
  - `parse_lead(row, page_id)`        → `meta_form_leads` row
  - `parse_leadgen_adset(row, account_id)` → `meta_leadgen_campaigns` row,
    or None when the adset is NOT an instant-form adset.

The instant-form discriminator (verified live 2026-07-10): leadgen adsets have
optimization_goal=LEAD_GENERATION + destination_type=ON_AD; the old
website/Wix-funnel campaigns are OFFSITE_CONVERSIONS + WEBSITE/UNDEFINED.

Lead `field_data` arrives as [{"name": "full_name", "values": ["…"]}, …]; the
known identity keys are flattened to columns, the raw list is preserved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from shared.lp_urls import DC_LANDING_HOSTS


def _first_value(field_data: list[dict[str, Any]], name: str) -> str | None:
    for item in field_data:
        if item.get("name") == name:
            values = item.get("values") or []
            if values and str(values[0]).strip():
                return str(values[0]).strip()
    return None


def parse_form(row: dict[str, Any], page_id: str) -> dict[str, Any]:
    """Project a /leadgen_forms row into a `meta_lead_forms` row."""
    return {
        "form_id": str(row.get("id")),
        "page_id": page_id,
        "name": row.get("name"),
        "status": row.get("status"),
        "form_created_time": row.get("created_time"),
        "questions": row.get("questions") or [],
        "raw": row,
    }


def parse_lead(row: dict[str, Any], page_id: str) -> dict[str, Any]:
    """Project a /{form_id}/leads row into a `meta_form_leads` row.

    `full_name` falls back to "first_name last_name" for forms that split the
    name; the current 7/8 Basic Form uses full_name + phone_number only.
    """
    field_data = row.get("field_data") or []
    full_name = _first_value(field_data, "full_name")
    if not full_name:
        parts = [
            _first_value(field_data, "first_name"),
            _first_value(field_data, "last_name"),
        ]
        joined = " ".join(p for p in parts if p)
        full_name = joined or None
    return {
        "lead_id": str(row.get("id")),
        "form_id": str(row.get("form_id")) if row.get("form_id") else None,
        "page_id": page_id,
        "created_time": row.get("created_time"),
        "ad_id": row.get("ad_id"),
        "ad_name": row.get("ad_name"),
        "adset_id": row.get("adset_id"),
        "adset_name": row.get("adset_name"),
        "campaign_id": row.get("campaign_id"),
        "campaign_name": row.get("campaign_name"),
        "is_organic": bool(row.get("is_organic", False)),
        "platform": row.get("platform"),
        "full_name": full_name,
        "phone_number": _first_value(field_data, "phone_number"),
        "email": _first_value(field_data, "email"),
        "field_data": field_data,
        "raw": row,
    }


# DC_LANDING_HOSTS (imported above) — the hosts whose traffic belongs to the
# Digital College funnel; canonical definition in shared/lp_urls.py (the Wistia
# embed scan shares it). Deliberately NOT theaipartner.io — that is the separate
# ANDROMEDA / Closer Funnel motion on the same ad account, and counting it here
# would corrupt DC spend and ROAS.


def creative_destination_urls(creative: dict[str, Any] | None) -> set[str]:
    """Every destination URL a creative might carry.

    Meta stores the click destination in a different place per creative type
    (plain link ads, video ads, Advantage+ asset feeds, CTA overrides), so we
    check all of them — a missed location means a DC campaign looks like a
    foreign one and silently drops off the page.
    """
    found: set[str] = set()
    if not creative:
        return found
    if str(creative.get("link_url") or "").startswith("http"):
        found.add(str(creative["link_url"]))
    spec = creative.get("object_story_spec") or {}
    for sub in ("link_data", "video_data", "photo_data"):
        data = spec.get(sub) or {}
        if str(data.get("link") or "").startswith("http"):
            found.add(str(data["link"]))
        cta_link = ((data.get("call_to_action") or {}).get("value") or {}).get("link")
        if str(cta_link or "").startswith("http"):
            found.add(str(cta_link))
    for link in (creative.get("asset_feed_spec") or {}).get("link_urls") or []:
        if str(link.get("website_url") or "").startswith("http"):
            found.add(str(link["website_url"]))
    return found


def _host_matches(url: str, hosts: tuple[str, ...]) -> bool:
    try:
        netloc = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except ValueError:
        return False
    return any(netloc == h or netloc.endswith("." + h) for h in hosts)


def parse_landing_page_ad(
    row: dict[str, Any],
    hosts: tuple[str, ...] = DC_LANDING_HOSTS,
) -> dict[str, Any] | None:
    """Project an /ads row into a `dc_ads_campaigns` landing-page row.

    Returns None unless the ad's creative points at one of `hosts`. Matching on
    HOST, never path: `/training` exists on both digitalcollege.ai (DC) and
    theaipartner.io (the unrelated Closer Funnel motion), and mixing them would
    corrupt the DC page's spend.
    """
    campaign_id = row.get("campaign_id")
    if not campaign_id:
        return None
    urls = creative_destination_urls(row.get("creative"))
    hit = next((u for u in sorted(urls) if _host_matches(u, hosts)), None)
    if not hit:
        return None
    campaign = row.get("campaign") or {}
    return {
        "campaign_id": str(campaign_id),
        "campaign_name": campaign.get("name"),
        "source_kind": "landing_page",
        "destination_url": hit,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_leadgen_adset(row: dict[str, Any], account_id: str) -> dict[str, Any] | None:
    """Project an /adsets row into a `meta_leadgen_campaigns` row.

    Returns None unless the adset matches the instant-form discriminator.
    The pipeline dedupes by campaign_id (many adsets → one campaign).
    """
    if row.get("optimization_goal") != "LEAD_GENERATION":
        return None
    if row.get("destination_type") != "ON_AD":
        return None
    campaign_id = row.get("campaign_id")
    if not campaign_id:
        return None
    campaign = row.get("campaign") or {}
    promoted = row.get("promoted_object") or {}
    return {
        "campaign_id": str(campaign_id),
        "campaign_name": campaign.get("name"),
        "account_id": account_id,
        "page_id": str(promoted["page_id"]) if promoted.get("page_id") else None,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }
