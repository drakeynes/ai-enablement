"""Meta leadgen (instant-form) ingestion orchestrator — the DC ads funnel.

One sync pass:
  1. Scan the ad account's adsets → upsert `meta_leadgen_campaigns` (the
     ad-spend scoping set for the DC ads funnel page).
  2. Derive the Page token from the user token (per run, never stored).
  3. Upsert the page's forms → `meta_lead_forms`.
  4. Per form, fetch submissions (incremental via `since_unix` on the cron;
     full on backfill) → upsert `meta_form_leads`.
  5. `refresh_dc_ads_facts()` so the funnel page reflects the new opt-ins.

Idempotent: every table upserts on its Meta id. ⚠ Meta retains leads ~90
days via the API — the mirror is the durable copy, so the cron must keep
running (see docs/runbooks/meta_leads_ingestion.md).

Used by both the cron (`api/meta_leads_sync_cron.py`) and the backfill
(`scripts/backfill_meta_leads.py`); same code path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ingestion.meta_ads.client import MetaAdsAPIError, MetaAdsClient
from ingestion.meta_ads.leads_parser import (
    parse_form,
    parse_landing_page_ad,
    parse_lead,
    parse_leadgen_adset,
)
from shared.lp_urls import lp_short_label, lp_slugify, normalize_lp_url

logger = logging.getLogger("ai_enablement.meta_ads.leads_pipeline")


@dataclass
class LeadsSyncOutcome:
    """Per-run summary; serialized into the cron audit row + HTTP response."""

    campaigns_upserted: int = 0
    lp_campaigns_upserted: int = 0
    lp_pages_created: int = 0
    lp_campaigns_linked: int = 0
    lp_typeforms_resolved: int = 0
    forms_upserted: int = 0
    leads_upserted: int = 0
    facts_rows: int | None = None
    errors: list[str] = field(default_factory=list)


def _chunked(rows: list[dict], size: int = 500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _dedup_by(rows: list[dict], key: str) -> list[dict]:
    """One row per key (last wins) — a batched upsert can't hit a key twice."""
    by_key = {r[key]: r for r in rows if r.get(key)}
    return list(by_key.values())


def fetch_leadgen_campaign_rows(client: MetaAdsClient, account_id: str) -> list[dict]:
    """Adset scan → deduped `meta_leadgen_campaigns` rows."""
    adsets = client.leadgen_adsets()
    rows = [parse_leadgen_adset(a, account_id) for a in adsets]
    return _dedup_by([r for r in rows if r], "campaign_id")


def fetch_landing_page_campaign_rows(client: MetaAdsClient) -> list[dict]:
    """Creative scan → deduped `dc_ads_campaigns` landing-page rows.

    The instant-form discriminator can't see these: a landing-page campaign is
    an ordinary OFFSITE_CONVERSIONS campaign, distinguishable only by where its
    creatives point (docs/schema/dc_ads_campaigns.md).
    """
    ads = client.account_ads_with_creatives()
    rows = [parse_landing_page_ad(a) for a in ads]
    return _dedup_by([r for r in rows if r], "campaign_id")


def _majority(values: list[str]) -> str | None:
    """Most frequent value; ties break to the more recent (later list order)."""
    if not values:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=lambda v: (counts[v], values[::-1].index(v) * -1))


def resolve_dc_landing_pages(db) -> tuple[int, int, int]:
    """Auto-maintain the DC landing-page registry (migration 0132).

    Runs after the creative scan so a brand-new funnel needs ZERO manual
    steps to appear on the DC Ads page (Drake 2026-08-13):

      1. A campaign whose normalized destination URL matches no
         `dc_landing_pages.lp_url` gets a new registry row — auto_created,
         label = the short URL ('join/training').
      2. Every landing-page campaign gets `lp_slug` stamped from the registry;
         campaigns missing `typeform_id` inherit the LP's.
      3. An LP row missing `typeform_id` gets it resolved by MAJORITY VOTE over
         `typeform_responses.hidden->>'campaign_id'` for its campaigns (the
         Typeform hidden fields carry the Meta campaign id — 861/862 coverage
         on the Aman form, verified 2026-08-13). Curated values are never
         overwritten — the resolver only ever fills nulls (except lp_slug,
         which follows the destination URL).

    Videos attach separately (the Wistia embed-location scan,
    ingestion/wistia/pipeline.py). Returns (pages_created, campaigns_linked,
    typeforms_resolved).
    """
    camps = (
        db.table("dc_ads_campaigns")
        .select("campaign_id, destination_url, lp_slug, lp_slugs, typeform_id")
        .eq("source_kind", "landing_page")
        .execute()
        .data
        or []
    )
    camps = [c for c in camps if c.get("destination_url")]
    lps = (
        db.table("dc_landing_pages")
        .select("slug, lp_url, typeform_id")
        .execute()
        .data
        or []
    )
    by_url = {lp["lp_url"]: lp for lp in lps}
    slugs = {lp["slug"] for lp in lps}

    # 1. Unseen destination URLs → new auto rows.
    created = 0
    for c in camps:
        norm = normalize_lp_url(c["destination_url"])
        if norm in by_url:
            continue
        label = lp_short_label(norm)
        base = lp_slugify(label) or "lp"
        slug = base
        suffix = 2
        while slug in slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        db.table("dc_landing_pages").insert(
            {"slug": slug, "label": label, "lp_url": norm, "auto_created": True}
        ).execute()
        by_url[norm] = {"slug": slug, "lp_url": norm, "typeform_id": None}
        slugs.add(slug)
        created += 1
        logger.info("dc landing pages: auto-created %s (%s)", slug, norm)

    # 2. Campaigns → lp_slug (follows the destination) + typeform inherit.
    #    lp_slugs (0138, split tests) keeps every page: the destination page
    #    becomes/stays the primary (first) entry; human-added extra pages are
    #    preserved, never removed.
    linked = 0
    for c in camps:
        lp = by_url[normalize_lp_url(c["destination_url"])]
        patch: dict = {}
        current_slugs: list[str] = c.get("lp_slugs") or []
        if c.get("lp_slug") != lp["slug"] or lp["slug"] not in current_slugs:
            patch["lp_slug"] = lp["slug"]
            patch["lp_slugs"] = [lp["slug"], *[s for s in current_slugs if s != lp["slug"]]]
        if not c.get("typeform_id") and lp.get("typeform_id"):
            patch["typeform_id"] = lp["typeform_id"]
        if patch:
            db.table("dc_ads_campaigns").update(patch).eq(
                "campaign_id", c["campaign_id"]
            ).execute()
            c.update(patch)
            linked += 1

    # 3. LP rows missing a typeform → majority vote over hidden-field
    #    campaign attribution.
    resolved = 0
    for lp in by_url.values():
        if lp.get("typeform_id"):
            continue
        camp_ids = [c["campaign_id"] for c in camps if c.get("lp_slug") == lp["slug"]]
        if not camp_ids:
            continue
        responses = (
            db.table("typeform_responses")
            .select("form_id")
            .in_("hidden->>campaign_id", camp_ids)
            .order("submitted_at", desc=False)
            .limit(2000)
            .execute()
            .data
            or []
        )
        form_id = _majority([r["form_id"] for r in responses if r.get("form_id")])
        if not form_id:
            continue
        db.table("dc_landing_pages").update({"typeform_id": form_id}).eq(
            "slug", lp["slug"]
        ).execute()
        lp["typeform_id"] = form_id
        for c in camps:
            if c.get("lp_slug") == lp["slug"] and not c.get("typeform_id"):
                db.table("dc_ads_campaigns").update({"typeform_id": form_id}).eq(
                    "campaign_id", c["campaign_id"]
                ).execute()
                c["typeform_id"] = form_id
        resolved += 1
        logger.info("dc landing pages: %s typeform resolved → %s", lp["slug"], form_id)

    return created, linked, resolved


def sync_meta_leads(
    db,
    client: MetaAdsClient,
    page_id: str,
    account_id: str,
    *,
    since_unix: int | None = None,
) -> LeadsSyncOutcome:
    """One full leadgen sync pass (see module docstring for the steps).

    `since_unix=None` fetches every retained lead (backfill); the cron passes
    a trailing-window timestamp. A MetaAdsAuthError on the page-token step
    aborts lead ingestion (credentials problem); a single form failing is
    recorded and the rest still sync.
    """
    outcome = LeadsSyncOutcome()

    # 1. adset scan → instant-form campaigns (user token; independent of leads)
    try:
        campaign_rows = fetch_leadgen_campaign_rows(client, account_id)
        for chunk in _chunked(campaign_rows):
            db.table("meta_leadgen_campaigns").upsert(
                chunk, on_conflict="campaign_id"
            ).execute()
        # Mirror into the page's real scoping set. on_conflict does NOT overwrite
        # funnel_label/typeform_id — those are curated per campaign.
        dc_rows = [
            {
                "campaign_id": r["campaign_id"],
                "campaign_name": r.get("campaign_name"),
                "source_kind": "instant_form",
                "last_seen_at": r.get("last_seen_at"),
            }
            for r in campaign_rows
        ]
        for chunk in _chunked(dc_rows):
            db.table("dc_ads_campaigns").upsert(chunk, on_conflict="campaign_id").execute()
        outcome.campaigns_upserted = len(campaign_rows)
    except MetaAdsAPIError as exc:
        outcome.errors.append(f"adset_scan: {exc}")
        logger.warning("meta leads sync: adset scan failed: %s", exc)

    # 1b. creative scan → landing-page campaigns. Kept separate from the adset
    # scan so a failure here can't cost us the instant-form scope (or the leads
    # below); a stale landing-page row just means a new LP campaign shows up a
    # tick late.
    try:
        lp_rows = fetch_landing_page_campaign_rows(client)
        for chunk in _chunked(lp_rows):
            db.table("dc_ads_campaigns").upsert(chunk, on_conflict="campaign_id").execute()
        outcome.lp_campaigns_upserted = len(lp_rows)
    except MetaAdsAPIError as exc:
        outcome.errors.append(f"creative_scan: {exc}")
        logger.warning("meta leads sync: creative scan failed: %s", exc)

    # 1c. landing-page registry resolver — a NEW funnel self-registers here
    # (dc_landing_pages row + lp_slug + typeform), no manual steps. Fail-soft:
    # a resolver hiccup never costs the lead sync below.
    try:
        created, linked, resolved = resolve_dc_landing_pages(db)
        outcome.lp_pages_created = created
        outcome.lp_campaigns_linked = linked
        outcome.lp_typeforms_resolved = resolved
    except Exception as exc:  # noqa: BLE001 — third-party client raises broadly
        outcome.errors.append(f"lp_resolver: {exc}")
        logger.warning("meta leads sync: landing-page resolver failed: %s", exc)

    # 2. page token — everything below needs it
    try:
        page_token = client.page_access_token(page_id)
    except MetaAdsAPIError as exc:
        outcome.errors.append(f"page_token: {exc}")
        logger.warning("meta leads sync: page token derivation failed: %s", exc)
        return outcome

    # 3. forms
    try:
        forms = client.leadgen_forms(page_id, page_token)
        form_rows = _dedup_by([parse_form(f, page_id) for f in forms], "form_id")
        for chunk in _chunked(form_rows):
            db.table("meta_lead_forms").upsert(chunk, on_conflict="form_id").execute()
        outcome.forms_upserted = len(form_rows)
    except MetaAdsAPIError as exc:
        outcome.errors.append(f"forms: {exc}")
        logger.warning("meta leads sync: forms fetch failed: %s", exc)
        return outcome

    # 4. leads per form
    for form_row in form_rows:
        form_id = form_row["form_id"]
        try:
            leads = client.form_leads(form_id, page_token, since_unix=since_unix)
            lead_rows = _dedup_by(
                [parse_lead(lead, page_id) for lead in leads], "lead_id"
            )
            for chunk in _chunked(lead_rows):
                db.table("meta_form_leads").upsert(
                    chunk, on_conflict="lead_id"
                ).execute()
            outcome.leads_upserted += len(lead_rows)
        except MetaAdsAPIError as exc:
            outcome.errors.append(f"leads[{form_id}]: {exc}")
            logger.warning("meta leads sync: form %s leads failed: %s", form_id, exc)

    # 5. facts refresh — the DC funnel page reads dc_ads_lead_facts
    try:
        result = db.rpc("refresh_dc_ads_facts", {}).execute()
        outcome.facts_rows = result.data
    except Exception as exc:  # noqa: BLE001 - refresh failure must not sink the sync
        outcome.errors.append(f"facts_refresh: {exc}")
        logger.warning("meta leads sync: refresh_dc_ads_facts failed: %s", exc)

    logger.info(
        "meta leads sync: campaigns=%d lp_campaigns=%d forms=%d leads=%d facts=%s errors=%d",
        outcome.campaigns_upserted,
        outcome.lp_campaigns_upserted,
        outcome.forms_upserted,
        outcome.leads_upserted,
        outcome.facts_rows,
        len(outcome.errors),
    )
    return outcome
