# dc_meta_ads

The per-ad registry for the DC Ads page (migration `0146`, boss batch
2026-08-15): one row per Meta ad on a DC campaign — either acquisition path —
with its parentage, status, and the landing page its creative points at.

The 15-min creative scan (`ingestion/meta_ads/leads_pipeline.py`) has always
fetched every account ad with its creative destination fields to auto-detect
landing-page campaigns, then collapsed to campaign grain. This table keeps the
ad grain. Ads from the unrelated Closer Funnel motion on the shared ad account
never enter (same host discriminator as campaign detection: an ad is kept only
if its campaign is already a registered DC campaign OR its creative points at
a `digitalcollege.ai` host).

## Columns

| column | type | notes |
|---|---|---|
| `ad_id` | text PK | Meta ad id — joins `cortana_ad_daily.platform_entity_id` and `dc_ads_lead_facts.ad_id`. |
| `ad_name` | text | Meta ad name ("08/12 \| Creative 18 \| Adj3"). |
| `campaign_id` | text not null | Parent campaign — joins `dc_ads_campaigns.campaign_id`. Indexed. |
| `adset_id` | text | Parent ad set. Indexed. |
| `effective_status` | text | Meta's effective status at last scan (ACTIVE / PAUSED / …). |
| `destination_url` | text | The creative's DC destination, **normalized** (`shared/lp_urls.normalize_lp_url` — `join.digitalcollege.ai/training`). Null for ads without one (instant-form ads). |
| `lp_slug` | text | Resolved against `dc_landing_pages.lp_url` at scan time. Null until the page registers (a brand-new LP resolves one tick later — the registry step runs AFTER the LP resolver). |
| `last_seen_at` | timestamptz | Last scan that saw the ad. Rows persist after an ad stops serving. |
| `synced_at` | timestamptz | Row write time. |

## Populated by / read by

- **Writes:** step 1d of `sync_meta_leads()` (`fetch_dc_meta_ad_rows()` →
  upsert on `ad_id`), every 15-min `api/meta_leads_sync_cron.py` tick and the
  backfill. Fail-soft: a registry error never costs the lead sync.
- **Reads:** `lib/db/dc-ads-summary.ts` — with a cascade entity **and** an LP
  both selected, LP visits sum `cortana_ad_daily` over only this registry's
  matching ads (per-LP split inside a split-test campaign); the per-ad table
  (item 10) seeds its ad list, names, and campaign facet from here.

## Example queries

```sql
-- Which landing page does each active ad in a campaign serve?
select ad_id, ad_name, lp_slug, effective_status
from dc_meta_ads where campaign_id = '120250217875250748';

-- Adds-up check: a campaign's per-ad clicks vs its campaign-level mirror.
select (select sum(unique_clicks) from cortana_ad_daily c
         join dc_meta_ads a on a.ad_id = c.platform_entity_id
        where a.campaign_id = :cid and c.day between :d1 and :d2) as ads_sum,
       (select sum(unique_clicks) from cortana_campaign_daily
        where platform_entity_id = :cid and day between :d1 and :d2) as campaign_total;
```
