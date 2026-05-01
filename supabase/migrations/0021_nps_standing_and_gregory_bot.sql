-- 0021_nps_standing_and_gregory_bot.sql
-- Path 1 schema work for the V1 Airtable NPS integration. Three changes
-- bundled because they ship together as the foundation the receiver
-- (next chunk) calls into:
--
--   1. clients.nps_standing column. Mirrors the Airtable NPS Survey
--      segment classification verbatim (normalized to lowercase at the
--      receiver boundary). Source of truth for the segment lives in
--      Airtable; Gregory mirrors it for dashboard surfacing + as the
--      input to csm_standing auto-derivation.
--
--   2. Gregory Bot sentinel team_members row. Pinned UUID
--      cfcea32a-062d-4269-ae0f-959adac8f597. Used as the changed_by on
--      auto-derived client_standing_history rows so the manual-vs-auto
--      distinction is queryable from the history table itself — no
--      separate "is_automated" column on history needed.
--
--   3. update_client_from_nps_segment RPC. Combined update — always
--      writes nps_standing; conditionally auto-derives csm_standing per
--      override-sticky semantics (manual CSM judgment wins). The auto-
--      derive path delegates to update_client_csm_standing_with_history
--      (0018) so audit logic + idempotency stay in one place.
--
-- Override-sticky semantics (Scott-confirmed behavior B):
--
--   - clients.csm_standing IS NULL                    → auto-derive allowed
--   - latest history row.changed_by = Gregory Bot     → auto-derive allowed
--   - latest history row.changed_by = anyone else     → skip (manual win)
--   - csm_standing non-null AND no history row exists → skip (defensive;
--                                                       0 rows match this
--                                                       at apply time)
--
-- Segment → csm_standing mapping (encoded only inside the function;
-- callers pass the segment, the DB does the work):
--
--   'promoter' → 'happy'
--   'neutral'  → 'content'
--   'at_risk'  → 'at_risk'
--
-- 'problem' csm_standing has no auto-derive path — only manual CSM
-- judgment, intentionally.

-- ---------------------------------------------------------------------------
-- 1. clients.nps_standing column
-- ---------------------------------------------------------------------------
alter table clients
  add column nps_standing text
    check (nps_standing is null or nps_standing in ('promoter', 'neutral', 'at_risk'));

comment on column clients.nps_standing is
  'NPS Survey segment classification, mirrored from Airtable. Normalized lowercase at the receiver boundary (Airtable raw strings like ''Strong / Promoter'' / ''Neutral'' / ''At Risk'' map to ''promoter'' / ''neutral'' / ''at_risk''). Always written by update_client_from_nps_segment regardless of csm_standing auto-derive outcome. Distinct from clients.csm_standing — nps_standing is mechanical (Airtable mirror), csm_standing is CSM judgment (with optional auto-derive from this column subject to override-sticky semantics).';

-- ---------------------------------------------------------------------------
-- 2. Gregory Bot sentinel team_members row
-- ---------------------------------------------------------------------------
-- Pinned UUID so the value is stable across environments. Hardcoded
-- literal here AND in update_client_from_nps_segment below — grep for
-- the UUID to find both call sites.
insert into team_members (id, email, full_name, role, is_active, metadata)
values (
  'cfcea32a-062d-4269-ae0f-959adac8f597'::uuid,
  'gregory-bot@theaipartner.io',
  'Gregory Bot',
  'system_bot',
  true,
  jsonb_build_object(
    'seed_source', 'migration_0021',
    'seeded_at', '2026-05-01',
    'sentinel', true,
    'purpose', 'changed_by attribution for auto-derived clients.csm_standing writes from update_client_from_nps_segment'
  )
)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- 3. update_client_from_nps_segment RPC
-- ---------------------------------------------------------------------------
create or replace function update_client_from_nps_segment(
  p_client_email text,
  p_segment text
) returns clients
language plpgsql
security definer
as $$
declare
  v_client_id uuid;
  v_current_csm_standing text;
  v_last_changed_by uuid;
  v_auto_derive_allowed boolean;
  v_derived_csm_standing text;
  v_updated clients%rowtype;
begin
  -- Validate inputs.
  if p_client_email is null or trim(p_client_email) = '' then
    raise exception 'update_client_from_nps_segment: client_email is required'
      using hint = 'Provide a non-empty email string';
  end if;

  if p_segment is null
     or p_segment not in ('promoter', 'neutral', 'at_risk') then
    raise exception 'update_client_from_nps_segment: invalid segment %', p_segment
      using hint = 'Allowed values: promoter, neutral, at_risk';
  end if;

  -- Look up the client. Primary clients.email match first, then
  -- fallback to clients.metadata->'alternate_emails'. Case-insensitive,
  -- whitespace-stripped, mirrors CLAUDE.md § "Client Identity
  -- Resolution". Filter on archived_at IS NULL — only active clients.
  -- LIMIT 1 because alternate_emails has no DB-side uniqueness;
  -- ambiguous matches silently pick the first row (no known collisions
  -- in production data; revisit if logs ever show ambiguity).
  select id into v_client_id from clients
  where archived_at is null
    and (
      lower(trim(email)) = lower(trim(p_client_email))
      or exists (
        select 1
        from jsonb_array_elements_text(
          coalesce(metadata->'alternate_emails', '[]'::jsonb)
        ) alt
        where lower(trim(alt)) = lower(trim(p_client_email))
      )
    )
  limit 1;

  if v_client_id is null then
    raise exception 'update_client_from_nps_segment: no active client matches email %', p_client_email
      using hint = 'Check primary email and clients.metadata.alternate_emails';
  end if;

  -- Always mirror the segment to clients.nps_standing.
  update clients set nps_standing = p_segment where id = v_client_id;

  -- Override-sticky check: is csm_standing currently null, or is the
  -- most recent history row attributed to Gregory Bot? Either path
  -- means we own the column and can auto-derive.
  select csm_standing into v_current_csm_standing
  from clients where id = v_client_id;

  if v_current_csm_standing is null then
    v_auto_derive_allowed := true;
  else
    v_last_changed_by := null;
    select changed_by into v_last_changed_by
    from client_standing_history
    where client_id = v_client_id
    order by changed_at desc
    limit 1;

    -- coalesce so a null v_last_changed_by (no history row) explicitly
    -- evaluates to false rather than null. Conservative: csm_standing
    -- non-null + no history → skip (don't clobber data of unknown
    -- provenance). 0 rows match this condition in production today.
    v_auto_derive_allowed := coalesce(
      v_last_changed_by = 'cfcea32a-062d-4269-ae0f-959adac8f597'::uuid,
      false
    );
  end if;

  -- Auto-derive when allowed. Mapping is encoded here only.
  if v_auto_derive_allowed then
    v_derived_csm_standing := case p_segment
      when 'promoter' then 'happy'
      when 'neutral'  then 'content'
      when 'at_risk'  then 'at_risk'
    end;

    -- Delegate to the 0018 RPC for the actual write + history-row
    -- insert. PERFORM discards the returned clients row; we re-SELECT
    -- below for our own return value. The 0018 RPC handles idempotency
    -- (no history row written when current = new).
    perform update_client_csm_standing_with_history(
      v_client_id,
      v_derived_csm_standing,
      'cfcea32a-062d-4269-ae0f-959adac8f597'::uuid,
      'auto-derived from NPS segment ' || p_segment
    );
  end if;

  -- Re-SELECT to capture post-update state (nps_standing definitely
  -- changed; csm_standing may have via the delegated RPC).
  select * into v_updated from clients where id = v_client_id;
  return v_updated;
end;
$$;

comment on function update_client_from_nps_segment is
  'Combined NPS-segment update for the V1 Airtable webhook receiver. Always writes clients.nps_standing; conditionally auto-derives clients.csm_standing per override-sticky semantics (manual CSM judgment wins — auto-derive runs only when csm_standing is null OR the most recent client_standing_history row is attributed to Gregory Bot). Looks up the client by p_client_email against clients.email primary + clients.metadata.alternate_emails fallback (case-insensitive, whitespace-stripped, archived_at IS NULL). Segment → csm_standing mapping is encoded only inside this function: promoter→happy, neutral→content, at_risk→at_risk. ''problem'' has no auto-derive path. Auto-write delegates to update_client_csm_standing_with_history (0018) for audit consistency. Raises with descriptive hints on invalid segment, missing email, or no client match. See migration 0021 header for the full architecture story.';

grant execute on function update_client_from_nps_segment(text, text) to service_role;
