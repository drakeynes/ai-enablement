# dc_ads_campaigns

**THE scoping set for the DC ads funnel page** (`/sales-dashboard/dc-ads`) —
both acquisition paths. Migration 0130. Supersedes `meta_leadgen_campaigns` as
the membership/spend scope (that table still exists and still feeds the
instant-form half of this one).

## Why it exists

The DC funnel has run **two** acquisition paths:

| `source_kind` | Path | Era |
|---|---|---|
| `instant_form` | Meta ad → Meta instant form → Close | the original (7/08 campaign) |
| `landing_page` | Meta ad → landing page → Typeform → Close | live since 2026-07-22 |

`meta_leadgen_campaigns` is built by the instant-form discriminator
(`optimization_goal=LEAD_GENERATION` + `destination_type=ON_AD`). Landing-page
campaigns are `OFFSITE_CONVERSIONS`/`UNDEFINED`, so they were never in it — and
`refresh_dc_ads_facts()` gated membership on that set **and** on
`funnel_name='Digital College'`. Close tags landing-page traffic
`Aman Funnel` / `Luke Funnel`, so both clauses excluded it: 801 leads and
~$12.2k of spend were invisible while the page reported a **paused** campaign
as its only source (measured 2026-08-12).

## ⚠ Do not widen this to "all OFFSITE_CONVERSIONS campaigns"

The same ad account runs the unrelated **ANDROMEDA / Closer Funnel** motion
(~$13.4k over Jun–Aug 2026) pointing at `theaipartner.io`. A blanket
`OFFSITE_CONVERSIONS` rule would sweep those onto the DC page and roughly triple
its spend with foreign campaigns. The discriminator is the **destination host**:

- Digital College → `digitalcollege.ai` (`join.digitalcollege.ai/training`, `go.digitalcollege.ai/`)
- Closer Funnel → `theaipartner.io` (`go.theaipartner.io/lp-vsl`, `join.theaipartner.io/training`)

Note `/training` exists on **both** hosts — match on full host, never path alone.

## Columns

| Column | Notes |
|---|---|
| `campaign_id` | PK. Meta campaign id. Joins `close_leads.campaign_id`, `cortana_campaign_daily.platform_entity_id`. |
| `campaign_name` | Meta campaign name, for display/debugging. |
| `source_kind` | `instant_form` \| `landing_page`. Drives the page's path facet. |
| `funnel_label` | Matches `close_leads.funnel_name` for this campaign's leads (`Digital College`, `Aman Funnel`, `Luke Funnel`). Display metadata since 0132 — the filter key is `lp_slug`. |
| `lp_slug` | (0132) The PRIMARY landing page — FK `dc_landing_pages.slug`, derived from the normalized `destination_url` by `resolve_dc_landing_pages()` each sync (= `lp_slugs[0]`). Null for `instant_form`. |
| `lp_slugs` | (0138) EVERY landing page the campaign drives to — several when split-testing (DC Setup checkboxes). The union over ACTIVE campaigns is exactly what the DC Ads page's LP dropdown + Ads & LP summary show. Facts stamping for a >1-LP campaign resolves per lead via the matched Typeform (each page embeds its own form), falling back to the primary. The resolver keeps the destination page present/first and never removes human-added extras. |
| `destination_url` | Landing-page campaigns only — the creative destination, and the evidence for the host rule above. |
| `typeform_id` | Landing-page campaigns only — the Typeform the LP embeds (joins `typeform_responses.form_id`). Inherited from the `dc_landing_pages` row by the resolver when null. |
| `active` | `false` retires a campaign from the page **without deleting it** (spend history must stay scoped). Paused-in-Meta campaigns stay `active=true` — their history still counts. |
| `first_seen_at` / `last_seen_at` | Detection window. |

## Populated by / read by

- **Writes:** seeded in 0130 (instant-form rows from `meta_leadgen_campaigns`;
  the three landing-page campaigns verified live against the Meta API on
  2026-08-12). The adset scan in `ingestion/meta_ads/leads_pipeline.py` keeps
  the `instant_form` rows current; the creative scan (0130) auto-registers new
  landing-page campaigns; `resolve_dc_landing_pages()` (0132) stamps
  `lp_slug` + inherits `typeform_id` from the `dc_landing_pages` registry.
  Humans curate via **DC Setup** (`/sales-dashboard/dc-setup` → Campaigns:
  `active` toggle + `lp_slug` link only — membership stays ingestion-owned).
- **Reads:** `refresh_dc_ads_facts()` (membership + `lp_slug` stamp),
  `spendScope()` in `lib/db/dc-ads.ts` (ad-spend scope), and
  `getDcAdsHierarchy()` (the campaign dropdown lists EVERY active row — a
  registered campaign with zero leads still shows, matching the Meta view).

## Adding a new DC campaign

A new **instant-form** campaign is picked up automatically by the adset scan. A
new **landing-page** campaign currently needs a row here — insert it with its
`destination_url`, `funnel_label` (whatever Close tags its leads) and
`typeform_id`. Watch for this: a new LP campaign that nobody registers is
silently invisible on the page, which is exactly the failure this migration
fixed.

## Example queries

```sql
-- the current scope, both paths
select source_kind, funnel_label, campaign_name from dc_ads_campaigns where active;

-- leads that would be excluded if a campaign were missing from the registry
select cl.campaign_id, count(*)
from close_leads cl
left join dc_ads_campaigns dc on dc.campaign_id = cl.campaign_id
where cl.funnel_name in ('Digital College','Aman Funnel','Luke Funnel')
  and dc.campaign_id is null
group by 1 order by 2 desc;
```

Related: `docs/schema/dc_ads_lead_facts.md` ·
`docs/schema/meta_leadgen_campaigns.md` ·
`docs/runbooks/meta_leads_ingestion.md`
