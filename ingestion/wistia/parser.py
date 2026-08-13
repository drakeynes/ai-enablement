"""Parse Wistia API payloads → row dicts for upsert.

Pure projection — no derivations. Engagement-rate + avg-view-duration
live in the future aggregation/dashboard layer; this module only
mirrors raw fields.

Two layout-projecting functions, one for each table:

  - `parse_media(media_json, stats_json, project_name_by_id)` →
    `wistia_medias` row dict. Merges the inventory payload (`name`,
    `hashed_id`, `project`, `duration`, `type`, `created`, `updated`)
    with the lifetime-stats payload (`pageLoads`, `visitors`, `plays`,
    `percentOfVisitorsClickingPlay`, `averagePercentWatched`).

  - `parse_by_date_entry(hashed_id, entry)` → `wistia_media_daily`
    row dict. One entry from the by_date list (one calendar day).

Unit notes (LOAD-BEARING — see migration 0045 header):

  - `hours_watched` stays in HOURS as float. NOT seconds.
  - `duration_seconds` is in SECONDS as float. Wistia's `duration`
    field is already in seconds; we rename to `duration_seconds` in
    the mirror for clarity.
  - `averagePercentWatched` is an INTEGER percentage (e.g. 25 for 25%).
"""

from __future__ import annotations

from typing import Any

from shared.lp_urls import normalize_lp_url


def parse_media(
    media_json: dict[str, Any],
    stats_json: dict[str, Any] | None,
    project_name_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Project /v1/medias.json + /v1/medias/{id}/stats.json into a
    wistia_medias row dict.

    `stats_json` is `None` when the per-media stats fetch failed (the
    caller wants the inventory row to land regardless — lifetime stats
    are a cross-check, not the source of truth).

    `project_name_by_id` is an optional map for richer project_name
    resolution (some media payloads carry `project.name` directly;
    others only carry `project.id` and we need a separate lookup).
    """
    if not media_json.get("hashed_id"):
        # No PK → no row. Caller skips.
        return {}

    project = media_json.get("project") or {}
    project_id = None
    project_name = None
    if isinstance(project, dict):
        project_id = project.get("id")
        if project_id is not None:
            project_id = str(project_id)
        project_name = project.get("name")
    if project_id and not project_name and project_name_by_id:
        project_name = project_name_by_id.get(project_id)

    row: dict[str, Any] = {
        "hashed_id": media_json.get("hashed_id"),
        "name": media_json.get("name"),
        "duration_seconds": media_json.get("duration"),
        "project_id": project_id,
        "project_name": project_name,
        "media_type": media_json.get("type"),
        "wistia_created_at": media_json.get("created"),
        "wistia_updated_at": media_json.get("updated"),
    }

    # Lifetime stats may be missing on a per-media failure — leave NULL.
    stats = (stats_json or {}).get("stats") if stats_json else None
    if isinstance(stats, dict):
        row["lifetime_page_loads"] = stats.get("pageLoads")
        row["lifetime_visitors"] = stats.get("visitors")
        row["lifetime_plays"] = stats.get("plays")
        row["lifetime_percent_of_visitors_clicking_play"] = stats.get(
            "percentOfVisitorsClickingPlay"
        )
        row["lifetime_avg_percent_watched"] = stats.get("averagePercentWatched")
    return row


def parse_by_date_entry(
    hashed_id: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """DEPRECATED post-2026-05-24. Use parse_timeseries_entry.

    Project one entry from /modern/stats/medias/{id}/by_date into a
    wistia_media_daily row dict. Entry shape (verified live during
    discovery):
        {"date": "2026-05-23", "load_count": 12, "play_count": 5,
         "hours_watched": 0.085}

    Retained for ad-hoc legacy queries; the post-cutover pipeline
    uses parse_timeseries_entry. See migration 0046 header for the
    rationale.
    """
    if not entry.get("date"):
        return {}
    return {
        "hashed_id": hashed_id,
        "day": entry.get("date"),
        "load_count": entry.get("load_count", 0) or 0,
        "play_count": entry.get("play_count", 0) or 0,
        "hours_watched": entry.get("hours_watched", 0) or 0,
    }


def parse_timeseries_entry(
    hashed_id: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Project one entry from /modern/analytics/medias/{id}/timeseries
    into a wistia_media_daily row dict (real per-day variance).

    Entry shape (verified live during watchtime-verify probe):
        {"timestamp": "2026-04-27 05:00:00.000Z",
         "plays": 23, "unique_plays": ..., "unique_loads": 8,
         "unique_visitors": ..., "played_time": 494,
         "engagement_rate": 0.09078, "play_rate": 0.75,
         "cta_impressions": 0, "cta_conversions": 0,
         "cta_conversion_rate": 0.0, "form_conversions": 0}

    Field mapping (load-bearing — see migration 0046 column comments):
      - `timestamp` → `day`: date portion (`timestamp[:10]`). Wistia's
        bucket-start timestamp aligns with the account's local calendar
        day (verified to match the legacy by_date `date` field exactly,
        so the cutover boundary doesn't introduce a one-day shift).
      - `played_time` → `played_time_seconds` (INTEGER seconds —
        already correct unit; no conversion).
      - `engagement_rate` → `engagement_rate` (0–1 float — stored RAW,
        not ×100; display layer formats).
      - `play_rate` → `play_rate` (0–1 float, stored raw).
      - `plays` → `plays_filtered` (NEW column distinct from the
        legacy `play_count`; the two endpoints disagree on play counts,
        timeseries is bot-filtered ~14% lower per verification report).
      - `unique_plays`/`unique_visitors`/`unique_loads` → same names.
      - CTA + form fields mirrored 1:1.

    The pipeline upsert deliberately does NOT include the legacy
    `play_count` / `load_count` / `hours_watched` columns, so existing
    pre-cutover values on those columns are preserved (historical audit).
    """
    timestamp = entry.get("timestamp")
    if not timestamp:
        return {}
    # Extract calendar day from the bucket-start timestamp. Wistia
    # returns ISO8601 like "2026-04-27 05:00:00.000Z" — the date
    # portion is the canonical day (account-local-tz calendar day).
    day = timestamp[:10] if isinstance(timestamp, str) and len(timestamp) >= 10 else None
    if not day:
        return {}
    return {
        "hashed_id": hashed_id,
        "day": day,
        "played_time_seconds": entry.get("played_time"),
        "engagement_rate": entry.get("engagement_rate"),
        "play_rate": entry.get("play_rate"),
        "plays_filtered": entry.get("plays"),
        "unique_plays": entry.get("unique_plays"),
        "unique_visitors": entry.get("unique_visitors"),
        "unique_loads": entry.get("unique_loads"),
        "cta_impressions": entry.get("cta_impressions"),
        "cta_conversions": entry.get("cta_conversions"),
        "cta_conversion_rate": entry.get("cta_conversion_rate"),
        "form_conversions": entry.get("form_conversions"),
    }


def embed_urls_from_events(events: list[dict[str, Any]]) -> set[str]:
    """The distinct NORMALIZED pages a media's view events played on.

    Feeds the DC landing-page video auto-attach: normalization
    (shared/lp_urls.py) strips the utm-laden query strings Meta appends,
    so 'https://join.digitalcollege.ai/training?utm_source=fb&…' and the
    bare page collapse to one key that matches dc_landing_pages.lp_url /
    page_urls.
    """
    urls: set[str] = set()
    for event in events:
        raw = event.get("embed_url")
        if isinstance(raw, str) and raw.strip():
            urls.add(normalize_lp_url(raw))
    return urls
