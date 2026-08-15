-- 0146: dc_meta_ads — the per-ad registry (boss batch 2026-08-15, item 9
-- adjustment + item 10 backbone).
--
-- The 15-min creative scan (ingestion/meta_ads/leads_pipeline.py) already
-- fetches every account ad with its creative destination URL to auto-detect
-- landing-page campaigns — then collapses to campaign grain and throws the
-- ad detail away. This table keeps it: one row per Meta ad on a DC campaign
-- (either path), with parentage (campaign/adset), status, and the LANDING
-- PAGE its creative points at (normalized URL → dc_landing_pages slug).
--
-- Consumers:
--   * the Ads & LP summary — with a campaign + LP both selected, LP visits =
--     clicks summed over the campaign's ads whose lp_slug matches (the boss's
--     "count the ads within the campaign and see which page they serve"), so
--     split-test campaigns split correctly instead of showing campaign totals;
--   * the upcoming per-ad table (item 10) — ad names, parentage for the
--     campaign facet, and listing ads with spend but zero opt-ins.

create table if not exists dc_meta_ads (
  ad_id text primary key,
  ad_name text,
  campaign_id text not null,
  adset_id text,
  effective_status text,
  -- Normalized creative destination (shared/lp_urls.normalize_lp_url); null
  -- for ads without a DC landing-page destination (instant-form ads).
  destination_url text,
  -- Resolved against dc_landing_pages by normalized URL at scan time; null
  -- until the page registers (a brand-new LP resolves one tick later).
  lp_slug text,
  last_seen_at timestamptz,
  synced_at timestamptz not null default now()
);

create index if not exists dc_meta_ads_campaign_idx on dc_meta_ads (campaign_id);
create index if not exists dc_meta_ads_adset_idx on dc_meta_ads (adset_id);

alter table dc_meta_ads enable row level security;

comment on table dc_meta_ads is
  'Per-ad registry for the DC Ads page (0146): every Meta ad on a DC campaign, with parentage (campaign/adset), effective_status, and the landing page its creative points at (normalized destination URL -> dc_landing_pages.slug). Upserted by the 15-min meta leads sync creative scan; rows persist after an ad stops serving (last_seen_at tells freshness). Read by the Ads & LP summary (per-LP visit splits within a campaign) and the per-ad table.';
