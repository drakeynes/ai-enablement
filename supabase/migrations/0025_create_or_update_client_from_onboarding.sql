-- 0025_create_or_update_client_from_onboarding.sql
-- M5.9 — Path 3 inbound (Airtable onboarding form receiver).
--
-- Single security-definer RPC the api/airtable_onboarding_webhook.py
-- handler calls. Does the match-or-create + history-row writes +
-- slack_channels resolution + tag-append all in one transaction so the
-- receiver stays a thin auth + payload-validation adapter.
--
-- ============================================================================
-- Three branches, mirroring ingestion/fathom/pipeline.py's _lookup_or_create_auto_client
-- ============================================================================
--
--   1. Active match (archived_at IS NULL)        → action='updated'
--   2. Archived match (archived_at IS NOT NULL)  → action='reactivated' (clears archived_at)
--   3. No match                                  → action='created'
--
-- Match logic: case-insensitive against clients.email primary AND
-- clients.metadata.alternate_emails (mirrors update_client_from_nps_segment
-- in migration 0021). When alternate matches, the canonical email
-- column is NOT overwritten with the form-submission email — the
-- alternate is the form's, the primary stays the canonical.
--
-- ============================================================================
-- History-row attribution (Gregory Bot UUID cfcea32a-...)
-- ============================================================================
--
--   - Create: status_history row written DIRECTLY (not via the RPC)
--             because the RPC's idempotent path skips writing when
--             current==new, and the column NOT NULL DEFAULT 'active'
--             means the row is born already at 'active'. Direct insert
--             matches migration 0017's seed pattern. csm_standing seed
--             goes through the RPC because the column is nullable
--             (NULL → 'content' is a real transition, RPC writes
--             history naturally).
--   - Update/Reactivate: status + csm_standing both go through the
--             *_with_history RPCs. Idempotent when value matches.
--
-- Note strings (grep-friendly, distinct from other Gregory Bot writes):
--
--   create:                'onboarding form initial seed'
--   update + reactivate:   'onboarding form submission'
--
-- ============================================================================
-- Backfill semantics on update / reactivate
-- ============================================================================
--
-- phone / start_date / country: backfill ONLY when current value is NULL.
-- Do NOT overwrite established values — the form submission is one
-- snapshot among potentially many; trust pre-existing data.
--
-- slack_user_id: backfill ONLY when current value is NULL. If current
-- value is set AND differs from payload → RAISE 'slack_user_id_conflict'.
-- The receiver translates to HTTP 409.
--
-- ============================================================================
-- slack_channels resolution (full-table UNIQUE on slack_channel_id)
-- ============================================================================
--
-- Six branches:
--
--   A. Active row exists for this client + same channel id   → no-op
--   B. Active row exists for this client + different channel → RAISE 'slack_channel_id_conflict_for_client'
--   C. No active row for this client; channel id unused      → INSERT
--   D. No active row for this client; channel id exists with
--      client_id IS NULL                                     → UPDATE client_id (reattach)
--   E. No active row for this client; channel id exists for
--      same client but archived                              → UPDATE is_archived=false (unarchive)
--   F. No active row for this client; channel id exists for
--      different client                                      → RAISE 'slack_channel_id_owned_by_different_client'
--
-- Reattach pattern (D) mirrors scripts/cleanup_master_sheet_completeness.py.
-- Anti-overwrite (B/F) mirrors the slack_user_id conflict semantics.
--
-- ============================================================================
-- Tag append (idempotent needs_review)
-- ============================================================================
--
-- tags is text[] NOT NULL DEFAULT '{}'. The append idiom dedupes via
-- DISTINCT-on-unnest, then re-aggregates back into an array. Order
-- isn't preserved; for a tags array no consumer cares about order.

create or replace function create_or_update_client_from_onboarding(
  p_full_name        text,
  p_email            text,
  p_phone            text,
  p_country          text,
  p_start_date       date,
  p_slack_user_id    text,
  p_slack_channel_id text,
  p_delivery_id      text
) returns jsonb
language plpgsql
security definer
as $$
declare
  v_gregory_bot         uuid := 'cfcea32a-062d-4269-ae0f-959adac8f597'::uuid;
  v_email_lower         text;
  v_active_id           uuid;
  v_archived_id         uuid;
  v_existing_id         uuid;
  v_existing_archived   boolean;
  v_existing_phone      text;
  v_existing_country    text;
  v_existing_start_date date;
  v_existing_slack_uid  text;
  v_action              text;
  v_metadata            jsonb;

  v_existing_channel_id   text;
  v_existing_channel_arch boolean;
  v_existing_channel_for  uuid;  -- client_id of any existing slack_channels row keyed by p_slack_channel_id
  v_existing_channel_arch_global boolean;
begin
  -- ============================================================
  -- Validate inputs
  -- ============================================================
  if p_full_name is null or trim(p_full_name) = '' then
    raise exception 'create_or_update_client_from_onboarding: full_name is required';
  end if;
  if p_email is null or trim(p_email) = '' then
    raise exception 'create_or_update_client_from_onboarding: email is required';
  end if;
  if p_phone is null or trim(p_phone) = '' then
    raise exception 'create_or_update_client_from_onboarding: phone is required';
  end if;
  if p_country is null or trim(p_country) = '' then
    raise exception 'create_or_update_client_from_onboarding: country is required';
  end if;
  if p_start_date is null then
    raise exception 'create_or_update_client_from_onboarding: start_date is required';
  end if;
  if p_slack_user_id is null or trim(p_slack_user_id) = '' then
    raise exception 'create_or_update_client_from_onboarding: slack_user_id is required';
  end if;
  if p_slack_channel_id is null or trim(p_slack_channel_id) = '' then
    raise exception 'create_or_update_client_from_onboarding: slack_channel_id is required';
  end if;
  if p_delivery_id is null or trim(p_delivery_id) = '' then
    raise exception 'create_or_update_client_from_onboarding: delivery_id is required';
  end if;

  v_email_lower := lower(trim(p_email));

  -- ============================================================
  -- Match: active row first (primary email + alternate_emails)
  -- ============================================================
  select id into v_active_id
  from clients
  where archived_at is null
    and (
      lower(trim(email)) = v_email_lower
      or exists (
        select 1
        from jsonb_array_elements_text(
          coalesce(metadata->'alternate_emails', '[]'::jsonb)
        ) alt
        where lower(trim(alt)) = v_email_lower
      )
    )
  limit 1;

  if v_active_id is not null then
    v_existing_id       := v_active_id;
    v_existing_archived := false;
    v_action            := 'updated';
  else
    -- Match: archived row by primary email + alternate_emails. Reactivate
    -- if found. Mirrors ingestion/fathom/pipeline.py:_lookup_or_create_auto_client
    -- archived-branch handling.
    select id into v_archived_id
    from clients
    where archived_at is not null
      and (
        lower(trim(email)) = v_email_lower
        or exists (
          select 1
          from jsonb_array_elements_text(
            coalesce(metadata->'alternate_emails', '[]'::jsonb)
          ) alt
          where lower(trim(alt)) = v_email_lower
        )
      )
    order by archived_at desc
    limit 1;

    if v_archived_id is not null then
      v_existing_id       := v_archived_id;
      v_existing_archived := true;
      v_action            := 'reactivated';
    end if;
  end if;

  -- ============================================================
  -- Branch 1 + 2: existing client (active or archived)
  -- ============================================================
  if v_existing_id is not null then
    -- Capture pre-existing field values for backfill semantics.
    select phone, country, start_date, slack_user_id
      into v_existing_phone, v_existing_country, v_existing_start_date,
           v_existing_slack_uid
    from clients where id = v_existing_id;

    -- Slack user id anti-overwrite check FIRST. Raise BEFORE any
    -- writes so the conflict path leaves no partial state.
    if v_existing_slack_uid is not null
       and v_existing_slack_uid <> p_slack_user_id then
      raise exception 'slack_user_id_conflict: existing=% new=%',
        v_existing_slack_uid, p_slack_user_id;
    end if;

    -- Slack channel anti-overwrite for THIS client. Look up the
    -- client's most recent active channel (mirrors getClientById).
    select slack_channel_id, is_archived
      into v_existing_channel_id, v_existing_channel_arch
    from slack_channels
    where client_id = v_existing_id
      and is_archived = false
    order by created_at desc
    limit 1;

    if v_existing_channel_id is not null
       and v_existing_channel_id <> p_slack_channel_id then
      raise exception 'slack_channel_id_conflict_for_client: existing=% new=%',
        v_existing_channel_id, p_slack_channel_id;
    end if;

    -- Reactivate the row if it was archived. Do this BEFORE the RPC
    -- calls below — the RPCs select the current row state and need to
    -- see archived_at = null. (Status RPC's lookup uses `where id = X`
    -- with no archived filter, so technically would work either way,
    -- but the order matches operational intent.)
    if v_existing_archived then
      update clients
        set archived_at = null
      where id = v_existing_id;
    end if;

    -- Status → 'active' via the RPC. Idempotent if already active
    -- (the M5.6 cascade trigger fires only on negative-going transitions
    -- so transitioning from any value to 'active' is a no-op for the
    -- cascade — safe).
    perform update_client_status_with_history(
      v_existing_id,
      'active',
      v_gregory_bot,
      'onboarding form submission'
    );

    -- csm_standing → 'content' via the RPC. Idempotent if already
    -- content. M5.7 trustpilot cascade fires only on transitions TO
    -- 'happy' — not relevant here.
    perform update_client_csm_standing_with_history(
      v_existing_id,
      'content',
      v_gregory_bot,
      'onboarding form submission'
    );

    -- Backfill phone / country / start_date / slack_user_id only when
    -- currently NULL. Spec: "do NOT overwrite established data."
    update clients
      set
        phone         = coalesce(v_existing_phone, p_phone),
        country       = coalesce(v_existing_country, p_country),
        start_date    = coalesce(v_existing_start_date, p_start_date),
        slack_user_id = coalesce(v_existing_slack_uid, p_slack_user_id),
        -- Tag append: dedupe via DISTINCT-on-unnest. Order not preserved;
        -- no consumer of `tags` cares about order.
        tags = array(
          select distinct unnest(
            coalesce(tags, '{}'::text[]) || array['needs_review']
          )
        )
    where id = v_existing_id;

  else
    -- ============================================================
    -- Branch 3: create new client
    -- ============================================================
    v_metadata := jsonb_build_object(
      'auto_created_from_onboarding_webhook', true,
      'auto_created_from_delivery_id', p_delivery_id,
      'auto_created_at', now()
    );

    insert into clients (
      full_name, email, phone, country, start_date,
      slack_user_id, status, tags, metadata
    ) values (
      p_full_name,
      v_email_lower,
      p_phone,
      p_country,
      p_start_date,
      p_slack_user_id,
      'active',
      array['needs_review']::text[],
      v_metadata
    )
    returning id into v_existing_id;

    -- Seed status_history directly. The *_with_history RPC's idempotent
    -- path would write zero rows here because column NOT NULL DEFAULT
    -- 'active' means current==new at row birth. Direct insert matches
    -- migration 0017's seed pattern and gives us the audit row Drake's
    -- spec asks for ("audit row exists from row birth").
    insert into client_status_history (
      client_id, status, changed_at, changed_by, note
    ) values (
      v_existing_id,
      'active',
      now(),
      v_gregory_bot,
      'onboarding form initial seed'
    );

    -- csm_standing seed: column is nullable, so RPC null→'content' is
    -- a real transition that writes a history row naturally. Same
    -- pattern as M5.4 NPS-derived csm_standing seeds.
    perform update_client_csm_standing_with_history(
      v_existing_id,
      'content',
      v_gregory_bot,
      'onboarding form initial seed'
    );

    v_action := 'created';
  end if;

  -- ============================================================
  -- slack_channels resolution (six branches; see header doc)
  -- ============================================================
  -- Look up any existing row keyed by p_slack_channel_id (full-table
  -- UNIQUE so at most one match).
  select client_id, is_archived
    into v_existing_channel_for, v_existing_channel_arch_global
  from slack_channels
  where slack_channel_id = p_slack_channel_id;

  -- Note: SELECT INTO that finds no row leaves v_existing_channel_for
  -- NULL — same value as a row with client_id IS NULL. The IS NOT NULL
  -- check below covers branches A, B, E, F (row exists with non-null
  -- client_id). The ELSE branch then re-queries with IS NULL filter
  -- to distinguish "row with NULL client_id" (Branch D, reattach) from
  -- "no row at all" (Branch C, fresh INSERT).
  if v_existing_channel_for is not null then
    if v_existing_channel_for = v_existing_id then
      -- Branches A + E: row exists for THIS client. Active → no-op
      -- (the active-mismatch case was raised above before any writes).
      -- Archived → unarchive.
      if v_existing_channel_arch_global then
        update slack_channels
          set is_archived = false
        where slack_channel_id = p_slack_channel_id;
      end if;
    else
      -- Branch F: row exists for a different client → conflict.
      raise exception 'slack_channel_id_owned_by_different_client: client_id=%',
        v_existing_channel_for;
    end if;
  else
    -- Branch D (NULL client_id reattach) or Branch C (fresh INSERT).
    if exists (
      select 1 from slack_channels
      where slack_channel_id = p_slack_channel_id
        and client_id is null
    ) then
      update slack_channels
        set client_id = v_existing_id, is_archived = false
      where slack_channel_id = p_slack_channel_id;
    else
      -- Fresh INSERT. slack_channels has two NOT NULL columns the
      -- form payload doesn't carry: `name` and `is_private`. We don't
      -- get the real Slack channel name from Zain (only the id), so
      -- use the client's full_name as a human-readable hint. Mirrors
      -- scripts/cleanup_master_sheet_completeness.py:_insert_or_relink_channel.
      -- is_private defaults false (no schema default; must be explicit).
      -- metadata.created_via lets forensics distinguish onboarding-
      -- inserted rows from cleanup-inserted ones.
      insert into slack_channels (
        slack_channel_id, client_id, name, is_private, is_archived,
        ella_enabled, metadata
      ) values (
        p_slack_channel_id,
        v_existing_id,
        p_full_name,
        false,
        false,
        false,
        jsonb_build_object('created_via', 'onboarding_webhook')
      );
    end if;
  end if;

  -- ============================================================
  -- Return
  -- ============================================================
  return jsonb_build_object(
    'client_id', v_existing_id,
    'action', v_action
  );
end;
$$;

comment on function create_or_update_client_from_onboarding is
  'Path 3 inbound RPC (Airtable onboarding form). Match-or-create on email (primary + metadata.alternate_emails, case-insensitive). Three branches: active match → updated; archived match → reactivated; no match → created. Status seeded via direct insert (column NOT NULL DEFAULT precludes RPC-driven seed); csm_standing seeded via RPC (nullable column). Backfill semantics on update/reactivate: phone/country/start_date/slack_user_id NULL-only. Slack ID conflicts raise structured exceptions the receiver translates to HTTP 409. needs_review tag appended idempotently via DISTINCT-on-unnest. Audit attribution via Gregory Bot UUID cfcea32a-062d-4269-ae0f-959adac8f597 with grep-friendly note strings (''onboarding form initial seed'' for create, ''onboarding form submission'' for update/reactivate).';

grant execute on function create_or_update_client_from_onboarding(
  text, text, text, text, date, text, text, text
) to service_role;
