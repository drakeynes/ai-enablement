"""Wistia ingestion orchestrator.

Pipeline (post-2026-05-24 cutover):
  1. Refresh media inventory (`wistia_medias`) — paginate /v1/medias.json
     + project lookup + per-media lifetime stats. Idempotent on
     `hashed_id` PK.
  2. For each media: pull /modern/analytics/medias/{id}/timeseries over
     a window → idempotent upsert into `wistia_media_daily` keyed on
     `(hashed_id, day)`. The NEW columns (played_time_seconds,
     engagement_rate, plays_filtered, uniques, CTA/form) get populated;
     the LEGACY columns (load_count, play_count, hours_watched) are
     deliberately NOT touched, preserving pre-cutover audit values.

Verification of why the cutover happened: docs/reports/wistia-watchtime-verify.md.
The legacy by_date endpoint synthesizes hours_watched, producing FAKE
daily engagement-rate variance. The timeseries endpoint returns real
per-bucket variance for played_time + engagement_rate.

Fail-soft per media — one media's stats failing doesn't abort the
whole sync; errors collected in `SyncOutcome.errors` for the audit row.

Used by both the daily cron (`api/wistia_sync_cron.py`, rolling
14-day window) and any ad-hoc backfill (`scripts/backfill_wistia.py`,
30-day window post-cutover).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ingestion.wistia.client import WistiaAPIError, WistiaClient
from ingestion.wistia.parser import (
    embed_urls_from_events,
    parse_media,
    parse_timeseries_entry,
)

logger = logging.getLogger("ai_enablement.wistia.pipeline")


@dataclass
class SyncOutcome:
    """Per-tick summary; serialized into the cron's audit row."""

    medias_synced: int = 0
    medias_failed: int = 0
    daily_rows_upserted: int = 0
    daily_rows_failed: int = 0
    dc_videos_attached: int = 0
    days_in_window: int = 0
    window: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def record_error(self, where: str, err: Exception) -> None:
        self.errors.append(f"{where}: {err}")


def sync_wistia(
    client: WistiaClient,
    db,
    *,
    start_date: date,
    end_date: date,
    max_medias: int | None = None,
) -> SyncOutcome:
    """One full pull: refresh inventory, then per-day stats per media.

    `start_date` + `end_date` (INCLUSIVE on both, YYYY-MM-DD) bound the
    per-day window. Cron passes a rolling 14-day window; backfill passes
    a 30-day one. The client's `fetch_timeseries` converts to the new
    endpoint's EXCLUSIVE end_date semantic internally — callers stay on
    the inclusive convention.

    `max_medias` caps how many medias get the timeseries treatment (for
    --smoke / --limit). None = all of them.
    """
    outcome = SyncOutcome(
        days_in_window=(end_date - start_date).days + 1,
        window={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )

    # ---- 1. Project lookup (for project_name resolution on medias) ----
    project_name_by_id: dict[str, str] = {}
    try:
        for proj in client.iter_projects():
            pid = proj.get("id")
            if pid is None:
                continue
            project_name_by_id[str(pid)] = proj.get("name") or ""
    except WistiaAPIError as e:
        # Non-fatal — most media payloads carry project.name inline; the
        # lookup is a fallback. Log + continue.
        outcome.warnings.append(f"projects fetch failed: {e}")

    # ---- 2. Media inventory + lifetime stats ---------------------------
    medias_seen: list[dict[str, Any]] = []
    try:
        medias_seen = list(client.iter_medias())
    except WistiaAPIError as e:
        outcome.record_error("iter_medias", e)
        return outcome

    for media in medias_seen:
        hid = media.get("hashed_id")
        if not hid:
            outcome.medias_failed += 1
            outcome.warnings.append("media payload missing hashed_id — skipped")
            continue
        # Lifetime stats. Fail-soft per-media; if stats 404 we still
        # write the inventory row.
        try:
            stats_payload = client.fetch_lifetime_stats(hid)
        except WistiaAPIError as e:
            stats_payload = None
            outcome.warnings.append(f"lifetime_stats {hid}: {e}")
        row = parse_media(media, stats_payload, project_name_by_id)
        if not row:
            outcome.medias_failed += 1
            continue
        try:
            db.table("wistia_medias").upsert(
                row, on_conflict="hashed_id"
            ).execute()
            outcome.medias_synced += 1
        except Exception as e:
            outcome.medias_failed += 1
            outcome.record_error(f"upsert media {hid}", e)

    # ---- 3. Per-day stats per media ------------------------------------
    target_medias = [m for m in medias_seen if m.get("hashed_id")]
    if max_medias is not None:
        target_medias = target_medias[:max_medias]

    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    # Medias with any real activity in this window — the bounded candidate set
    # for the DC embed-location scan below (quiet medias skip the events call).
    active_hids: set[str] = set()
    for media in target_medias:
        hid = media["hashed_id"]
        try:
            entries = client.fetch_timeseries(
                hid, start_date=start_iso, end_date=end_iso
            )
        except WistiaAPIError as e:
            outcome.record_error(f"timeseries {hid}", e)
            continue
        for entry in entries:
            row = parse_timeseries_entry(hid, entry)
            if not row:
                continue
            if (row.get("unique_visitors") or 0) > 0 or (row.get("plays_filtered") or 0) > 0:
                active_hids.add(hid)
            try:
                # Upsert only the timeseries-sourced columns. The legacy
                # load_count / play_count / hours_watched columns are
                # NOT in `row`, so pre-cutover values on existing rows
                # are preserved (historical audit trail). New rows get
                # the column defaults (0 for the legacy int columns,
                # 0 for hours_watched).
                db.table("wistia_media_daily").upsert(
                    row, on_conflict="hashed_id,day"
                ).execute()
                outcome.daily_rows_upserted += 1
            except Exception as e:
                outcome.daily_rows_failed += 1
                outcome.record_error(f"upsert daily {hid} {row.get('day')}", e)

    # ---- 4. DC landing-page video auto-attach --------------------------
    # A video that plays on a registered DC landing page (or one of its
    # funnel pages) attaches itself to that page's registry row — so a new
    # funnel's VSL appears on the DC Ads page with zero manual steps
    # (Drake 2026-08-13). Fail-soft: never costs the stats sync above.
    try:
        outcome.dc_videos_attached = attach_dc_lp_videos(
            client, db, target_medias, active_hids
        )
    except Exception as e:  # noqa: BLE001 — third-party client raises broadly
        outcome.record_error("dc_video_attach", e)

    logger.info(
        "wistia sync: medias=%d/%d daily_upserted=%d daily_failed=%d dc_attached=%d window=%s..%s",
        outcome.medias_synced,
        outcome.medias_synced + outcome.medias_failed,
        outcome.daily_rows_upserted,
        outcome.daily_rows_failed,
        outcome.dc_videos_attached,
        start_iso,
        end_iso,
    )
    return outcome


def attach_dc_lp_videos(
    client: WistiaClient,
    db,
    target_medias: list[dict[str, Any]],
    active_hids: set[str],
) -> int:
    """Map recently-active medias to DC landing pages by embed location.

    For each media with activity in the sync window, sample its recent view
    events (embed_url per view), normalize the pages, and match them against
    `dc_landing_pages.lp_url` + `page_urls`. A match appends
    {hashedId, label} to that LP's `vsl` list (never removes, never
    duplicates — curated entries stay). One embed can serve several LPs
    (DC_VSL_Thank you_v2 plays on both funnels today).
    """
    if not active_hids:
        return 0
    lps = (
        db.table("dc_landing_pages")
        .select("slug, lp_url, page_urls, vsl")
        .eq("active", True)
        .execute()
        .data
        or []
    )
    if not lps:
        return 0
    slugs_by_url: dict[str, list[dict[str, Any]]] = {}
    for lp in lps:
        for url in [lp["lp_url"], *(lp.get("page_urls") or [])]:
            slugs_by_url.setdefault(url, []).append(lp)

    name_by_hid = {
        m["hashed_id"]: (m.get("name") or m["hashed_id"]) for m in target_medias
    }
    attached = 0
    for hid in sorted(active_hids):
        try:
            events = client.fetch_recent_events(hid)
        except WistiaAPIError as e:
            logger.warning("wistia dc attach: events for %s failed: %s", hid, e)
            continue
        for url in embed_urls_from_events(events):
            for lp in slugs_by_url.get(url, []):
                vsl = lp.get("vsl") or []
                if any(v.get("hashedId") == hid for v in vsl):
                    continue
                vsl = [*vsl, {"hashedId": hid, "label": name_by_hid.get(hid, hid)}]
                db.table("dc_landing_pages").update({"vsl": vsl}).eq(
                    "slug", lp["slug"]
                ).execute()
                lp["vsl"] = vsl
                attached += 1
                logger.info(
                    "wistia dc attach: %s (%s) → %s via %s",
                    hid, name_by_hid.get(hid, "?"), lp["slug"], url,
                )
    return attached


def sync_wistia_rolling(
    client: WistiaClient,
    db,
    *,
    window_days: int = 14,
    max_medias: int | None = None,
) -> SyncOutcome:
    """Convenience wrapper for the cron: rolling [today-N+1, today] window."""
    end = date.today()
    start = end - timedelta(days=window_days - 1)
    return sync_wistia(
        client, db, start_date=start, end_date=end, max_medias=max_medias,
    )
