-- 0026_onboarding_webhook_optional_slack.sql
-- M6.x — Make slack_user_id, slack_channel_id, and phone optional on
-- the onboarding webhook RPC. The other 4 fields (full_name, email,
-- country, start_date, delivery_id) stay required.
--
-- ============================================================================
-- Why this change
-- ============================================================================
--
-- Original 0025 contract required all 7 form fields. Operationally, Zain
-- frequently runs onboarding for a new client without slack identifiers
-- in hand (and sometimes without phone). He'd then re-run the same form
-- later when the Slack channel + invite have actually completed and the
-- IDs are known. Old contract forced him to either (a) wait to submit
-- the form until everything was lined up — delaying the client's birth
-- in Gregory — or (b) submit dummy values and clean up later.
--
-- New contract: phone / slack_user_id / slack_channel_id are nullable.
-- A first submission lands the client in Gregory immediately; the
-- re-fire with slack IDs filled in backfills via the existing
-- NULL-only backfill semantics (slack_user_id) and runs the existing
-- slack_channels six-branch resolution block on the second pass.
--
-- ============================================================================
-- What changed structurally
-- ============================================================================
--
-- 1. Drop the input-validation RAISEs for p_phone, p_slack_user_id,
--    p_slack_channel_id. The other 5 RAISEs stay.
--
-- 2. The slack_user_id anti-overwrite check inside Branch 1+2 (existing
--    client path) is null-guarded: only fires when p_slack_user_id IS
--    NOT NULL. NULL-payload-with-existing-set is a no-op (existing
--    sticks; backfill via coalesce already handles this).
--
-- 3. The slack_channel_id anti-overwrite check inside Branch 1+2
--    (`v_existing_channel_id <> p_slack_channel_id` raise) is also
--    null-guarded.
--
-- 4. The entire bottom slack_channels six-branch resolution block is
--    wrapped in `if p_slack_channel_id is not null and trim(...) <> ''`.
--    When skipped, the client just doesn't get a slack_channels row
--    this time. A later re-fire with the channel id set will hit
--    Branch C (no row anywhere with this channel id → fresh INSERT)
--    via the update path — `v_existing_channel_id` from the earlier
--    same-client lookup is null (no active row for this client),
--    anti-overwrite guard skipped, bottom block reached, INSERT runs.
--
-- ============================================================================
-- Compatibility
-- ============================================================================
--
-- Signature unchanged (CREATE OR REPLACE same 8-arg signature, all
-- types identical). Existing receiver call shape (passing every
-- argument) still works — passing the literal string '' is rejected
-- at the receiver layer now (wrong_type), but the RPC tolerates it
-- via the trim() = '' guards on the slack_channel_id wrapper.
-- Conflict semantics on populated re-fires unchanged.

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
  v_existing_channel_for  uuid;
  v_existing_channel_arch_global boolean;
begin
  -- ============================================================
  -- Validate inputs (5 required; phone / slack_user_id /
  -- slack_channel_id are now optional)
  -- ============================================================
  if p_full_name is null or trim(p_full_name) = '' then
    raise exception 'create_or_update_client_from_onboarding: full_name is required';
  end if;
  if p_email is null or trim(p_email) = '' then
    raise exception 'create_or_update_client_from_onboarding: email is required';
  end if;
  if p_country is null or trim(p_country) = '' then
    raise exception 'create_or_update_client_from_onboarding: country is required';
  end if;
  if p_start_date is null then
    raise exception 'create_or_update_client_from_onboarding: start_date is required';
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
    select phone, country, start_date, slack_user_id
      into v_existing_phone, v_existing_country, v_existing_start_date,
           v_existing_slack_uid
    from clients where id = v_existing_id;

    -- Slack user id anti-overwrite check. Null-guarded: a NULL-payload
    -- re-fire on a client that already has slack_user_id set is a no-op
    -- (existing sticks; backfill coalesce below handles the symmetric
    -- case where existing is null and payload is null — stays null).
    if p_slack_user_id is not null
       and v_existing_slack_uid is not null
       and v_existing_slack_uid <> p_slack_user_id then
      raise exception 'slack_user_id_conflict: existing=% new=%',
        v_existing_slack_uid, p_slack_user_id;
    end if;

    -- Slack channel anti-overwrite for THIS client. Null-guarded for
    -- the same reason as the user-id check above. Also short-circuits
    -- the lookup query when payload is null — no point reading
    -- slack_channels if we have nothing to compare it against.
    if p_slack_channel_id is not null
       and trim(p_slack_channel_id) <> '' then
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
    end if;

    if v_existing_archived then
      update clients
        set archived_at = null
      where id = v_existing_id;
    end if;

    perform update_client_status_with_history(
      v_existing_id,
      'active',
      v_gregory_bot,
      'onboarding form submission'
    );

    perform update_client_csm_standing_with_history(
      v_existing_id,
      'content',
      v_gregory_bot,
      'onboarding form submission'
    );

    -- Backfill phone / country / start_date / slack_user_id only when
    -- currently NULL. With p_phone or p_slack_user_id null, coalesce
    -- yields the existing value (still NULL if both are null) — no
    -- behavior change vs the existing semantics.
    update clients
      set
        phone         = coalesce(v_existing_phone, p_phone),
        country       = coalesce(v_existing_country, p_country),
        start_date    = coalesce(v_existing_start_date, p_start_date),
        slack_user_id = coalesce(v_existing_slack_uid, p_slack_user_id),
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

    -- p_phone / p_slack_user_id may be null on the create path. clients
    -- columns are nullable for both; partial unique on slack_user_id
    -- (where archived_at is null) tolerates multiple-null rows.
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

    insert into client_status_history (
      client_id, status, changed_at, changed_by, note
    ) values (
      v_existing_id,
      'active',
      now(),
      v_gregory_bot,
      'onboarding form initial seed'
    );

    perform update_client_csm_standing_with_history(
      v_existing_id,
      'content',
      v_gregory_bot,
      'onboarding form initial seed'
    );

    v_action := 'created';
  end if;

  -- ============================================================
  -- slack_channels resolution (six branches; see header doc).
  -- Wrapped: only execute when p_slack_channel_id is non-null and
  -- non-empty. When skipped, no slack_channels row is created or
  -- modified for this client. A later re-fire with the channel id
  -- supplied will hit Branch C on the update path (no active row
  -- for this client → bottom block lookup finds no global match
  -- → fresh INSERT).
  -- ============================================================
  if p_slack_channel_id is not null
     and trim(p_slack_channel_id) <> '' then
    select client_id, is_archived
      into v_existing_channel_for, v_existing_channel_arch_global
    from slack_channels
    where slack_channel_id = p_slack_channel_id;

    if v_existing_channel_for is not null then
      if v_existing_channel_for = v_existing_id then
        if v_existing_channel_arch_global then
          update slack_channels
            set is_archived = false
          where slack_channel_id = p_slack_channel_id;
        end if;
      else
        raise exception 'slack_channel_id_owned_by_different_client: client_id=%',
          v_existing_channel_for;
      end if;
    else
      if exists (
        select 1 from slack_channels
        where slack_channel_id = p_slack_channel_id
          and client_id is null
      ) then
        update slack_channels
          set client_id = v_existing_id, is_archived = false
        where slack_channel_id = p_slack_channel_id;
      else
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
  end if;

  return jsonb_build_object(
    'client_id', v_existing_id,
    'action', v_action
  );
end;
$$;

comment on function create_or_update_client_from_onboarding is
  'Path 3 inbound RPC (Airtable onboarding form). Match-or-create on email (primary + metadata.alternate_emails, case-insensitive). Three branches: active match → updated; archived match → reactivated; no match → created. Required inputs: full_name, email, country, start_date, delivery_id. Optional inputs (M6 — 0026): phone, slack_user_id, slack_channel_id — all nullable; null on create lands the client without those fields, null on update is a no-op (existing values stick). Re-fire flow: first submission without slack IDs creates the client; later re-fire with slack IDs populated backfills slack_user_id (NULL-only) and creates a fresh slack_channels row via Branch C. Status seeded via direct insert (column NOT NULL DEFAULT precludes RPC-driven seed); csm_standing seeded via RPC (nullable column). Slack ID conflicts raise structured exceptions the receiver translates to HTTP 409 — only when the corresponding payload field is non-null. needs_review tag appended idempotently via DISTINCT-on-unnest. Audit attribution via Gregory Bot UUID cfcea32a-062d-4269-ae0f-959adac8f597 with grep-friendly note strings (''onboarding form initial seed'' for create, ''onboarding form submission'' for update/reactivate).';

grant execute on function create_or_update_client_from_onboarding(
  text, text, text, text, date, text, text, text
) to service_role;
