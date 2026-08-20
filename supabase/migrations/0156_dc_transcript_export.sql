-- 0156: DC transcript export (Nabeel 2026-08-19: "raw export of the
-- transcripts to feed into AI"). The dashboard's Export button on DC Calls
-- downloads a markdown file — the SQL here is the heavy lifting:
--
--   dc_transcript_turns(words)      one call's Deepgram diarized words →
--                                   "**Speaker N:** …" dialogue turns. Done
--                                   IN Postgres on purpose: the words arrays
--                                   are ~1,500 objects/call, so shipping raw
--                                   jsonb to the route handler would move
--                                   ~90 MB for a full export; only finished
--                                   text leaves the DB.
--   dc_ads_transcript_export(ids)   per-call metadata (review verdict,
--                                   scores) + the turns text, for a batch of
--                                   call ids (the route chunks ~40/request
--                                   to stay inside PostgREST timeouts).
--   dc_ads_transcript_export_ids()  every exportable call id, oldest first
--                                   (the "Export all" id list; the route
--                                   pages it .range()-wise past the REST
--                                   max-rows cap).
--
-- Speaker labels are diarization order (1 = first voice heard), NOT roles —
-- the repo's talk-time heuristic deliberately abstains from rep-identifying,
-- and the export's per-call header names the rep instead.
-- scripts/export_dc_transcripts.py is the offline sibling (same shape).

create or replace function dc_transcript_turns(p_words jsonb)
returns text
language sql
stable
as $function$
  with w as (
    select e.ord,
      coalesce(nullif(e.elem->>'punctuated_word', ''), e.elem->>'word', '') as tok,
      coalesce((e.elem->>'speaker')::int, -1) as spk
    from jsonb_array_elements(coalesce(p_words, '[]'::jsonb))
      with ordinality as e(elem, ord)
  ),
  -- Label speakers 1..N by first appearance; mark turn boundaries.
  labeled as (
    select w2.*,
      dense_rank() over (order by w2.first_ord) as spk_label,
      case when w2.spk is distinct from lag(w2.spk) over (order by w2.ord)
           then 1 else 0 end as chg
    from (
      select w.*, min(w.ord) over (partition by w.spk) as first_ord from w
    ) w2
  ),
  turns as (
    select spk_label, tok, ord,
      sum(chg) over (order by ord rows unbounded preceding) as turn_id
    from labeled
  ),
  agg as (
    select turn_id, min(spk_label) as lbl,
      string_agg(tok, ' ' order by ord) as txt
    from turns
    where tok <> ''
    group by turn_id
  )
  select string_agg('**Speaker ' || lbl || ':** ' || txt, E'\n\n' order by turn_id)
  from agg
$function$;

comment on function dc_transcript_turns(jsonb) is
  '0156: Deepgram diarized words jsonb → markdown dialogue turns ("**Speaker N:** …", blank-line separated). Labels are order-of-first-appearance, not roles. Null/empty words → null.';

create or replace function dc_ads_transcript_export(p_call_ids text[])
returns table (
  call_id text,
  at timestamptz,
  lead_name text,
  rep_name text,
  duration_s int,
  closed boolean,
  why_not_closed text,
  rep_gap text,
  archetype text,
  lead_score int,
  intent int,
  offer_understanding int,
  rep_score int,
  turns text
)
language sql
stable
as $function$
  select r.close_call_id, c.activity_at,
    coalesce(nullif(trim(cl.display_name), ''), '(no name)'),
    coalesce(tm.full_name, nullif(c.raw_payload->>'user_name', ''), c.user_id),
    c.duration, r.closed, r.why_not_closed, r.rep_gap, r.archetype,
    r.lead_score, r.intent, r.offer_understanding, r.rep_score,
    dc_transcript_turns(t.words)
  from setter_call_reviews r
  join setter_call_transcripts t on t.close_call_id = r.close_call_id
  join close_calls c on c.close_id = r.close_call_id
  left join close_leads cl on cl.close_id = c.lead_id
  left join team_members tm on tm.close_user_id = c.user_id
  where r.call_type = 'dc_ads'
    and r.close_call_id = any(p_call_ids)
  order by c.activity_at
$function$;

comment on function dc_ads_transcript_export(text[]) is
  '0156: batch transcript export — review verdict + speaker-turn text per dc_ads-reviewed call id. Non-dc_ads / unknown ids silently drop. Called by the DC Calls Export button''s route handler in ~40-id chunks.';

create or replace function dc_ads_transcript_export_ids()
returns setof text
language sql
stable
as $function$
  select r.close_call_id
  from setter_call_reviews r
  join setter_call_transcripts t on t.close_call_id = r.close_call_id
  join close_calls c on c.close_id = r.close_call_id
  where r.call_type = 'dc_ads'
  order by c.activity_at
$function$;

comment on function dc_ads_transcript_export_ids() is
  '0156: every exportable dc_ads call id, oldest first — the Export-all id list (route pages with .range past REST max-rows).';
