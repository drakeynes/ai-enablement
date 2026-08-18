"""DC Ads intelligence synthesis (0152) — LLM-over-aggregates generators.

Two dashboard-only outputs on the DC Ads surface:
  - exec_summary: the daily executive summary (dc_ads_exec_summaries).
  - rep_coaching: the weekly per-rep coaching synthesis (dc_rep_coaching).

Both read AGGREGATES (the daily RPC rows + dc_ads_call_reviews() payload
and the reviews' quote-evidenced strengths/weaknesses) — never raw
transcripts. Sales-side isolation per 0054: costs inline, no agent_runs.
"""

from agents.dc_intel.exec_summary import generate_exec_summary
from agents.dc_intel.rep_coaching import generate_rep_coaching

__all__ = ["generate_exec_summary", "generate_rep_coaching"]
