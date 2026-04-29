-- 0015_merge_clients_function.sql
-- Atomic merge of an auto-created client (source) into a canonical
-- client row (target). Used by the Gregory dashboard's "Merge into…"
-- flow on the Clients detail page — visible only on rows tagged
-- needs_review.
--
-- Mirrors scripts/merge_client_duplicates.py:_perform_merge() +
-- _sync_alternates(). That script remains as historical record of the
-- four pilot pairs already merged; new merges go through this RPC.
--
-- Single transaction: all 5 steps land or none do. Idempotency: if
-- source.metadata.merged_into is already set, steps 1–4 are skipped;
-- step 5 (alternates sync on target) always runs and dedupes, which
-- mirrors the Python script's "fill retroactive gaps" behavior.

create or replace function merge_clients(
  p_source_id uuid,
  p_target_id uuid
) returns jsonb
language plpgsql
security definer
as $$
declare
  v_source clients%rowtype;
  v_target clients%rowtype;
  v_source_metadata jsonb;
  v_target_metadata jsonb;
  v_already_merged boolean;
  v_call_ids uuid[];
  v_call_id_texts text[];
  v_participant_count int := 0;
  v_call_count int := 0;
  v_doc_count int := 0;
  v_now timestamptz := now();
  v_alt_emails jsonb;
  v_alt_names jsonb;
begin
  -- ------------------------------------------------------------------
  -- Step 0: load + validate
  -- ------------------------------------------------------------------
  if p_source_id = p_target_id then
    raise exception 'merge_clients: source and target are the same client (%)', p_source_id;
  end if;

  select * into v_source from clients where id = p_source_id;
  if not found then
    raise exception 'merge_clients: source client not found (%)', p_source_id;
  end if;

  select * into v_target from clients where id = p_target_id;
  if not found then
    raise exception 'merge_clients: target client not found (%)', p_target_id;
  end if;

  if v_target.archived_at is not null then
    raise exception 'merge_clients: target client is archived (%)', p_target_id;
  end if;

  if not coalesce(v_source.tags @> array['needs_review']::text[], false) then
    raise exception 'merge_clients: source client does not have needs_review tag (%)', p_source_id;
  end if;

  v_source_metadata := coalesce(v_source.metadata, '{}'::jsonb);
  v_already_merged := (v_source_metadata ? 'merged_into');

  -- ------------------------------------------------------------------
  -- Steps 1–4: skip if source is already merged.
  -- ------------------------------------------------------------------
  if not v_already_merged then
    -- Snapshot source's call ids before mutations. Step 3 needs them
    -- to find the right transcript_chunk documents, and step 2 will
    -- have already re-pointed them by the time step 3 runs.
    select coalesce(array_agg(id), array[]::uuid[]) into v_call_ids
    from calls
    where primary_client_id = p_source_id;

    -- Step 1: reattribute call_participants.
    update call_participants
    set client_id = p_target_id
    where client_id = p_source_id;
    get diagnostics v_participant_count = row_count;

    -- Step 2: re-point calls + flip retrievability. The real client
    -- is now known; this is a human-directed promotion (the
    -- asymmetric rule's "only a human promotes" — same justification
    -- as the Python script).
    update calls
    set primary_client_id = p_target_id,
        is_retrievable_by_client_agents = true
    where primary_client_id = p_source_id;
    get diagnostics v_call_count = row_count;

    -- Step 3: reactivate transcript_chunk documents whose
    -- metadata.call_id is in the source's call set; re-point
    -- metadata.client_id to target. The Python script fetches all
    -- call_transcript_chunk docs and filters in Python; we do the
    -- same shape here, but server-side via a text-array IN check.
    if cardinality(v_call_ids) > 0 then
      v_call_id_texts := array(
        select id::text from unnest(v_call_ids) as id
      );

      update documents
      set metadata = jsonb_set(
            coalesce(metadata, '{}'::jsonb),
            '{client_id}',
            to_jsonb(p_target_id::text)
          ),
          is_active = true
      where document_type = 'call_transcript_chunk'
        and metadata->>'call_id' = any(v_call_id_texts);
      get diagnostics v_doc_count = row_count;
    end if;

    -- Step 4: soft-archive source + stamp merged_into / merged_at.
    update clients
    set archived_at = v_now,
        metadata = v_source_metadata
                   || jsonb_build_object(
                        'merged_into', p_target_id::text,
                        'merged_at', to_jsonb(v_now)
                      )
    where id = p_source_id;
  end if;

  -- ------------------------------------------------------------------
  -- Step 5: alternates sync on target. Always runs — idempotent via
  -- dedup. Re-read target metadata so we see fresh state if a prior
  -- run partially filled the alternates and is being resumed.
  -- ------------------------------------------------------------------
  select metadata into v_target_metadata from clients where id = p_target_id;
  v_target_metadata := coalesce(v_target_metadata, '{}'::jsonb);

  v_alt_emails := coalesce(v_target_metadata->'alternate_emails', '[]'::jsonb);
  if v_source.email is not null
     and v_source.email <> ''
     and not (v_alt_emails @> to_jsonb(v_source.email)) then
    v_alt_emails := v_alt_emails || to_jsonb(v_source.email);
  end if;

  v_alt_names := coalesce(v_target_metadata->'alternate_names', '[]'::jsonb);
  if v_source.full_name is not null
     and v_source.full_name <> ''
     and v_source.full_name is distinct from v_target.full_name
     and not (v_alt_names @> to_jsonb(v_source.full_name)) then
    v_alt_names := v_alt_names || to_jsonb(v_source.full_name);
  end if;

  update clients
  set metadata = v_target_metadata
                 || jsonb_build_object(
                      'alternate_emails', v_alt_emails,
                      'alternate_names', v_alt_names
                    )
  where id = p_target_id;

  -- ------------------------------------------------------------------
  -- Return a structured summary the dashboard can show in the toast /
  -- inline confirmation.
  -- ------------------------------------------------------------------
  return jsonb_build_object(
    'source_id', p_source_id,
    'target_id', p_target_id,
    'already_merged', v_already_merged,
    'participants_reattributed', v_participant_count,
    'calls_reattributed', v_call_count,
    'transcript_chunks_reactivated', v_doc_count
  );
end;
$$;

comment on function merge_clients is
  'Atomic merge of an auto-created (needs_review-tagged) client into a canonical client. Mirrors scripts/merge_client_duplicates.py:_perform_merge() + _sync_alternates() in a single transaction. Idempotent via source.metadata.merged_into. Called by the Gregory dashboard from the Clients detail page. See docs/agents/gregory.md M3.2 build log.';
