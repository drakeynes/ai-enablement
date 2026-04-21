# Data Hygiene

Short, durable rules for what we let into Supabase from any source system.

## Verify field ownership before ingesting

Before a pipeline writes a column or metadata key from an external source, confirm the source is authoritative for that field. If the "real" value lives somewhere else — a person's head, a different tool, a derived calculation — don't import the stale copy. A missing field is a known gap; a stale one is a confident lie, and every downstream consumer (agents, dashboards, reports) treats it as truth.

**Worked example — revenue fields in the Financial Master Sheet.** The sheet has `Contracted Rev`, `Contracted Rev AUD`, and monthly `PP` columns. On review, Scott confirmed the real state of revenue lives in his head; the sheet values drift from reality. So `scripts/seed_clients.py` drops every revenue column at ingestion — no `contracted_revenue_usd`, no `contracted_revenue_currency`, no monthly totals. The importer's metadata shape is five keys (`seed_source`, `seeded_at`, `country`, `nps_standing`, `owner_raw`), and that's final.

The same reasoning later removed the `Standing` column and its derived tags (`owing_money`, the Standing-half of `at_risk`). Standing reliability is unclear; the tags carried that uncertainty into agent behavior.

## Spreadsheet imports — three questions before you write a line of code

When the source is a spreadsheet, ask the owner — not yourself — these questions before designing the importer:

1. **Which views do you use day-to-day?** Saved filters like `Active++` or `Aus Active++` are the working definition of "who counts." Rows outside those views are likely noise, historical residue, or ad-hoc notes. Use the working view as the filter rule; don't try to encode "what the full sheet implies" yourself.
2. **Which rows are hidden or filtered out?** Hidden rows, grouped rows, and "archive" tabs usually encode human judgment we can't reconstruct ("this client left, don't look at them"). Import what the owner sees, not everything in the file.
3. **Which columns are stale?** Revenue numbers, NPS snapshots, anything manually transcribed from another system — ask directly. The owner knows which columns they update and which they stopped caring about five quarters ago.

**Worked example — the Active++ miss.** The initial `seed_clients.py` imported every row with a non-blank Customer Name and mapped `Churn` status to `archived=false, status=churned`. That pulled ~49 historical churned clients into the DB. On review, Scott confirmed the churn history predates the current team's ownership, the data quality is unclear, and the team has no use for it — it was noise, not history. The importer now follows the sheet's `Active++` and `Aus Active++` saved views as the canonical rule: USA keeps `active/ghost/paused`, AUS keeps `active/paused`. Everything else isn't imported; previously-imported churned rows are soft-archived on re-run via the cascade in `scripts/seed_clients.py`.

## Historical data without ownership is noise, not history

If nobody on the team can vouch for a batch of historical data — its source, its accuracy at ingest time, or the judgment calls that shaped it — don't import it. Soft-archive it, drop it, or leave it out. Real history accumulates forward, under current ownership, with context. Pretending to preserve a pre-ownership batch leaves agents and dashboards reading confidently-wrong context. The cheap fix is starting fresh and writing the playbook for how future events get captured properly.

## The rule, compressed

1. For each field a pipeline is about to ingest, answer: *who owns this, and is this system the one they update?*
2. If the answer is "nobody reliably" or "a different tool" — skip the field.
3. For spreadsheets, import the owner's working view, not the whole file.
4. Note every exclusion in the pipeline's runbook or module docstring so the next person knows why it's missing, not forgotten.
