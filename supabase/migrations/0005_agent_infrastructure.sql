-- 0005_agent_infrastructure.sql
-- Agent infrastructure shared across every agent: runs, HITL escalations, feedback.

-- ---------------------------------------------------------------------------
-- agent_runs
-- ---------------------------------------------------------------------------
create table agent_runs (
  id                 uuid primary key default gen_random_uuid(),
  agent_name         text not null,
  trigger_type       text not null,
  trigger_metadata   jsonb,
  input_summary      text,
  output_summary     text,
  status             text not null,
  confidence_score   float,
  llm_model          text,
  llm_input_tokens   integer,
  llm_output_tokens  integer,
  llm_cost_usd       numeric(10, 4),
  duration_ms        integer,
  error_message      text,
  metadata           jsonb not null default '{}'::jsonb,
  started_at         timestamptz not null default now(),
  ended_at           timestamptz
);

comment on table agent_runs is
  'Every execution of every agent, logged. Universal across the system — analytics, eval, and debugging all read this table.';
comment on column agent_runs.agent_name is
  'Canonical agent name: ella, csm_copilot, sales_call_analysis, etc.';
comment on column agent_runs.trigger_type is
  'What kicked this run off: slack_mention, schedule, webhook, manual.';
comment on column agent_runs.status is
  'Terminal status: success, escalated, error, skipped.';
comment on column agent_runs.confidence_score is
  'Optional self-reported confidence if the agent computes one.';
comment on column agent_runs.llm_model is
  'Specific model used, e.g. claude-sonnet-4-6, claude-opus-4-7.';
comment on column agent_runs.llm_cost_usd is
  'Computed cost for this run. 4-decimal precision is enough at current token prices.';

create index agent_runs_agent_name_started_at_idx on agent_runs (agent_name, started_at desc);
create index agent_runs_status_idx on agent_runs (status);
create index agent_runs_trigger_type_idx on agent_runs (trigger_type);
create index agent_runs_started_at_idx on agent_runs (started_at desc);

alter table agent_runs enable row level security;

-- ---------------------------------------------------------------------------
-- escalations
-- ---------------------------------------------------------------------------
create table escalations (
  id                uuid primary key default gen_random_uuid(),
  agent_run_id      uuid not null references agent_runs(id),
  agent_name        text not null,
  reason            text not null,
  context           jsonb not null,
  proposed_action   jsonb,
  assigned_to       uuid references team_members(id),
  status            text not null default 'open',
  resolution        jsonb,
  resolution_note   text,
  resolved_by       uuid references team_members(id),
  resolved_at       timestamptz,
  created_at        timestamptz not null default now()
);

comment on table escalations is
  'HITL escalations. Created when an agent lacks confidence or an action needs human approval. Resolved by a team member through the approval UI.';
comment on column escalations.reason is
  'Human-readable reason the agent escalated. Surfaced to the reviewer.';
comment on column escalations.context is
  'Full context the reviewer needs: retrieved snippets, agent reasoning, relevant IDs. Shape varies per agent.';
comment on column escalations.proposed_action is
  'What the agent wanted to do. Reviewer can approve, reject, or edit.';
comment on column escalations.status is
  'open, approved, rejected, edited, expired.';
comment on column escalations.resolution is
  'What the human actually decided. Same schema expectations as proposed_action for easier diffing.';

create index escalations_agent_run_id_idx on escalations (agent_run_id);
create index escalations_assigned_to_status_idx on escalations (assigned_to, status);
create index escalations_status_created_at_idx on escalations (status, created_at desc);
create index escalations_agent_name_idx on escalations (agent_name);

alter table escalations enable row level security;

-- ---------------------------------------------------------------------------
-- agent_feedback
-- ---------------------------------------------------------------------------
create table agent_feedback (
  id                 uuid primary key default gen_random_uuid(),
  agent_run_id       uuid not null references agent_runs(id),
  feedback_type      text not null,
  original_output    jsonb,
  corrected_output   jsonb,
  note               text,
  provided_by        uuid references team_members(id),
  created_at         timestamptz not null default now()
);

comment on table agent_feedback is
  'Explicit and implicit human corrections of agent output. Source of truth for building eval golden datasets.';
comment on column agent_feedback.feedback_type is
  'correction, thumbs_up, thumbs_down, edit, override.';
comment on column agent_feedback.original_output is
  'The agent''s output at the time of feedback. May differ from what was ultimately sent if a human edited it.';
comment on column agent_feedback.corrected_output is
  'What the human thinks the output should have been. Null for thumbs-style feedback.';

create index agent_feedback_agent_run_id_idx on agent_feedback (agent_run_id);
create index agent_feedback_type_idx on agent_feedback (feedback_type);
create index agent_feedback_provided_by_idx on agent_feedback (provided_by) where provided_by is not null;

alter table agent_feedback enable row level security;
