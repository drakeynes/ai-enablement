# Data Hygiene

Short, durable rules for what we let into Supabase from any source system.

## Verify field ownership before ingesting

Before a pipeline writes a column or metadata key from an external source, confirm the source is authoritative for that field. If the "real" value lives somewhere else — a person's head, a different tool, a derived calculation — don't import the stale copy. A missing field is a known gap; a stale one is a confident lie, and every downstream consumer (agents, dashboards, reports) treats it as truth.

**Worked example — revenue fields in the Financial Master Sheet.** The sheet has `Contracted Rev`, `Contracted Rev AUD`, and monthly `PP` columns. On review, Scott confirmed the real state of revenue lives in his head; the sheet values drift from reality. So `scripts/seed_clients.py` imports `seed_source`, `country`, `standing`, `nps_standing`, and `owner_raw` — but intentionally drops every revenue column. No `contracted_revenue_usd`, no `contracted_revenue_currency`, no monthly totals. The `owing_money` tag stays because it's derived from the Standing *text* column (a note Scott writes), not from a numeric revenue cell.

## The rule, compressed

1. For each field a pipeline is about to ingest, answer: *who owns this, and is this system the one they update?*
2. If the answer is "nobody reliably" or "a different tool" — skip the field.
3. Note the exclusion in the pipeline's runbook or module docstring so the next person knows why it's missing, not forgotten.
