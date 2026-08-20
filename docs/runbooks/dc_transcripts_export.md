# DC call-transcripts export

`scripts/export_dc_transcripts.py` — one markdown file with every DC Ads
reviewed call (the DC Calls page's set: `call_type='dc_ads'` reviews),
each section = a metadata header (ET time, lead, rep, duration, the AI
review's outcome / rep_gap / archetype / four 0-10 scores) + the
conversation as Speaker-1/2 turns rebuilt from the Deepgram diarized
words. Built for Nabeel's "feed the raw calls to an AI and ask it
questions" ask (2026-08-19).

## Usage

```bash
python scripts/export_dc_transcripts.py                      # everything
python scripts/export_dc_transcripts.py --start 2026-08-01 --end 2026-08-19
python scripts/export_dc_transcripts.py --plain              # raw text, no turns
python scripts/export_dc_transcripts.py --out /tmp/dc.md
```

Needs `psycopg2` + `.env.local` (`SUPABASE_DB_POOL_URL`,
`SUPABASE_DB_PASSWORD`). `--start`/`--end` are ET dates (end exclusive).
Full export ≈ 500 calls / ~5 MB — fine as a single upload to a Claude
Project / NotebookLM; split by month with `--start/--end` if a tool
chokes.

## PII (non-negotiable)

The output contains prospect names, phones, and everything said on the
calls. Default output is `~/exports/` — OUTSIDE the repo. Never commit
an export; hand it to Nabeel directly. Speaker labels are diarization
order, not roles (the repo's own talk-time heuristic deliberately
abstains from rep-identification) — the header names the rep, which is
enough for any reader to infer roles.
