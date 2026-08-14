-- 0139_dc_setup_system_health.sql
--
-- DC Setup gains a SYSTEM HEALTH panel at the bottom (boss 2026-08-14): per
-- data source, "✅ Connected · Last sync Xm ago" — so the team can see at a
-- glance that everything feeding the DC Ads page is up, without asking an
-- engineer. Every ingestion path already writes webhook_deliveries audit
-- rows; the panel is just "when did each source last succeed."
--
-- (source, received_at) index: webhook_deliveries is 700k+ rows and the
-- existing indexes can't answer per-source max(received_at) quickly — this
-- makes the health read (and any future per-source audit query) instant.

create index webhook_deliveries_source_received_idx
  on webhook_deliveries (source, received_at desc);

-- Last successful tick per source, over the sources the DC Ads page depends
-- on. 7-day floor: a source silent longer than that reads as absent (the UI
-- shows "no sync in the last 7 days"). Statuses: 'processed' only — a
-- delivery that failed or was skipped is not a heartbeat.
--
-- Shape note: one scalar subquery per source, NOT a group-by — each becomes
-- a backward scan on the (source, received_at) index (~ms); the group-by
-- form seq-scanned 700k rows (~13s measured).
create function dc_setup_system_health()
returns jsonb
language sql
stable
as $function$
with src(name) as (values
  ('meta_leads_sync'),        -- Meta ads → leads + campaign auto-detect (15-min cron)
  ('meta_sync'),              -- Meta ads → spend mirrors (hourly cron)
  ('close_webhook'),          -- Close CRM: leads / calls / SMS (live webhook)
  ('typeform_sync_cron'),     -- Typeform responses (15-min cron)
  ('airtable_sync_cron'),     -- Airtable sale forms / closer reports (15-min cron)
  ('wistia_sync'),            -- Wistia video stats (3-hourly cron)
  ('outbound_facts_refresh')  -- the page's own numbers refresh (15-min cron)
)
select coalesce(jsonb_object_agg(src.name, hit.last_ok), '{}'::jsonb)
from src
cross join lateral (
  select max(w.received_at) as last_ok
  from webhook_deliveries w
  where w.source = src.name
    and w.processing_status = 'processed'
    and w.received_at > now() - interval '7 days'
) hit
where hit.last_ok is not null
$function$;

comment on function dc_setup_system_health() is
  'DC Setup system-health panel: last successful webhook_deliveries tick per DC-relevant source (7-day window, processed only). The UI maps each source to a display name + staleness threshold.';
