# dc_landing_pages

The **Digital College landing-page registry** — the URL-keyed identity behind
the DC Ads page's landing-page dropdown and its Ads & Landing-Page summary
section. One row per ad-destination landing page on `digitalcollege.ai`.
Migration 0132.

Landing pages are named by their **actual URLs**, shortened (`join/training`,
`go`) — Drake 2026-08-13 — never by the Close `funnel_name` (which cross-tags
a handful of leads and can't be derived for a brand-new campaign until Close
traffic flows). The ad creative's destination URL is known the moment a
campaign is detected, which is what makes the whole chain self-registering.

**Deliberately separate from `landing_pages`** (the high-ticket registry):
that table's form set defines HT funnel membership (`getHighTicketFormIds`),
so adding DC forms there would corrupt the Advertising Hub's numbers.

## Columns

| Column | Notes |
|--------|-------|
| `slug` | PK — `lp_slugify(label)` (`join-training`, `go`). The `?lp=` URL param + `dc_ads_lead_facts.lp_slug` value. The pseudo-slug `instant-form` (no row here) marks the legacy no-LP path in facts. |
| `label` | Short display name: subdomain + path with the shared domain stripped (`join/training`). Editable. |
| `lp_url` | UNIQUE — the normalized ad-destination URL (host+path, no scheme/query/trailing slash; `shared/lp_urls.py`). THE join key from `dc_ads_campaigns.destination_url`. |
| `page_urls` | Additional normalized funnel pages (e.g. Luke's VSL page `join.digitalcollege.ai/t-2`, reached after the opt-in). The Wistia embed scan matches videos against `lp_url` AND these. |
| `typeform_id` | The LP's opt-in Typeform. Auto-resolved by majority vote over `typeform_responses.hidden->>'campaign_id'` (861/862 coverage on the Aman form, verified 2026-08-13). |
| `vsl` | `[{hashedId, label}]` — the funnel's video(s), same shape as `landing_pages.vsl`. Auto-appended by the Wistia embed-location scan; one video can serve several LPs (DC_VSL_Thank you_v2 plays on both funnels). |
| `confirm_video_hashed_id` / `confirm_video_label` | Optional confirmation-page video. Manual for now (the confirmation-page URLs aren't registered). |
| `active` | false retires an LP from the dropdown without deleting history. |
| `auto_created` | true = created by the ingestion resolver from an unseen destination URL. Rename/attach in place — the resolver only fills nulls, never overwrites curated values. |
| `sort_order` | Dropdown order. |

## Populated by / read by

- **Writes:** seeded in 0132 (Aman + Luke, verified live); then
  `resolve_dc_landing_pages()` (`ingestion/meta_ads/leads_pipeline.py`, every
  Meta leads sync) auto-creates rows for unseen destination URLs + resolves
  typeforms, and `attach_dc_lp_videos()` (`ingestion/wistia/pipeline.py`,
  every Wistia sync) auto-attaches videos by embed location.
- **Reads:** `lib/db/dc-ads.ts` (`getDcAdsHierarchy` — the dropdown options;
  `spendScope` — via `dc_ads_campaigns.lp_slug`), `lib/db/dc-ads-summary.ts`
  (the Ads & LP section: typeform + videos per LP),
  `refresh_dc_ads_facts()` (via `dc_ads_campaigns.lp_slug` → facts `lp_slug`).

## A new funnel appears — the auto chain

1. Creative scan sees a campaign pointing at an unseen `digitalcollege.ai`
   URL → `dc_ads_campaigns` row (0130 behavior).
2. `resolve_dc_landing_pages()` → new row here (`auto_created`, label = short
   URL) + `dc_ads_campaigns.lp_slug` stamped → the dropdown shows it and
   spend scopes to it immediately.
3. First opt-ins flow → facts get the `lp_slug` (next `refresh_dc_ads_facts()`)
   → the funnel numbers filter; typeform resolves by hidden-field majority.
4. Wistia sees the funnel's video playing on the page → `vsl` attaches → the
   Videos block populates.

Manual touch-ups (optional, in place): prettier `label`, `page_urls` for
mid-funnel video pages, confirmation video.

## Example queries

```sql
-- The dropdown, with window opt-in counts
select lp.label, count(f.close_id) as opt_ins
from dc_landing_pages lp
left join dc_ads_lead_facts f on f.lp_slug = lp.slug
where lp.active
group by lp.label;

-- Which campaigns drive to each page
select lp.label, c.campaign_name
from dc_ads_campaigns c
join dc_landing_pages lp on lp.slug = c.lp_slug
order by lp.sort_order, c.campaign_name;
```
