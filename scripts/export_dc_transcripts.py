"""Export the DC Ads call transcripts as one AI-readable markdown file.

Nabeel's ask (2026-08-19): a raw export of the DC call transcripts he can
feed to an AI and interrogate. One markdown file, one section per
reviewed DC call: a metadata header (when, lead, rep, duration, the AI
review's outcome + scores + archetype) followed by the conversation as
speaker-labelled turns rebuilt from the Deepgram diarized words array
(labels are "Speaker 1/2/…" — diarization can't reliably say which is
the rep, but the header names the rep and an AI infers roles trivially).

Scope: every call with a call_type='dc_ads' review (the same set the DC
Calls page shows), optionally narrowed by --start/--end (ET dates).

⚠ PII: the output contains prospect names, phone numbers and whatever
was said on the calls. It is written OUTSIDE the repo (default
~/exports/) and must never be committed. Hand it to Nabeel directly.

Usage:
  python scripts/export_dc_transcripts.py                    # everything
  python scripts/export_dc_transcripts.py --start 2026-08-01 --end 2026-08-19
  python scripts/export_dc_transcripts.py --plain            # raw text, no turns
  python scripts/export_dc_transcripts.py --out /tmp/dc.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import psycopg2

_ET = ZoneInfo("America/New_York")
_REPO_ROOT = Path(__file__).resolve().parent.parent

_QUERY = """
select
  c.activity_at,
  coalesce(nullif(trim(cl.display_name), ''), '(no name)') as lead_name,
  coalesce(tm.full_name,
           nullif(c.raw_payload ->> 'user_name', ''), c.user_id) as rep_name,
  c.duration,
  r.closed, r.why_not_closed, r.rep_gap, r.archetype,
  r.lead_score, r.intent, r.offer_understanding, r.rep_score,
  t.transcript_text, t.words
from setter_call_reviews r
join setter_call_transcripts t on t.close_call_id = r.close_call_id
join close_calls c on c.close_id = r.close_call_id
left join close_leads cl on cl.close_id = c.lead_id
left join team_members tm on tm.close_user_id = c.user_id
where r.call_type = 'dc_ads'
  and (%(start)s::timestamptz is null or c.activity_at >= %(start)s)
  and (%(end)s::timestamptz is null or c.activity_at < %(end)s)
order by c.activity_at
"""


def _pg_conn() -> psycopg2.extensions.connection:
    """Cloud connection from .env.local (pool URL + password splice)."""
    env: dict[str, str] = {}
    for ln in (_REPO_ROOT / ".env.local").read_text().splitlines():
        if "=" in ln and not ln.startswith("#"):
            key, _, val = ln.partition("=")
            env[key] = val.strip().strip('"').strip("'")
    pool, pw = env["SUPABASE_DB_POOL_URL"], env["SUPABASE_DB_PASSWORD"]
    scheme, _, rest = pool.partition("://")
    creds, _, hostpart = rest.rpartition("@")
    user = creds.split(":")[0]
    dsn = f"{scheme}://{user}:{quote(pw, safe='')}@{hostpart}"
    return psycopg2.connect(dsn, connect_timeout=20)


def _turns(words: list[dict[str, Any]]) -> str:
    """Rebuild the conversation as speaker-labelled turns.

    Consecutive same-speaker words merge into one turn; raw Deepgram
    speaker ints map to Speaker 1/2/… in order of first appearance.
    """
    label_of: dict[int, int] = {}
    lines: list[str] = []
    current_spk: int | None = None
    current: list[str] = []

    def flush() -> None:
        if current and current_spk is not None:
            lines.append(f"**Speaker {label_of[current_spk]}:** {' '.join(current)}")

    for w in words:
        spk = w.get("speaker")
        if not isinstance(spk, int):
            spk = -1
        if spk not in label_of:
            label_of[spk] = len(label_of) + 1
        token = (w.get("punctuated_word") or w.get("word") or "").strip()
        if not token:
            continue
        if spk != current_spk:
            flush()
            current_spk, current = spk, []
        current.append(token)
    flush()
    return "\n\n".join(lines)


def _fmt_duration(seconds: int | None) -> str:
    s = int(seconds or 0)
    return f"{s // 60}:{s % 60:02d}"


def _call_section(row: tuple[Any, ...], plain: bool) -> str:
    (at, lead, rep, dur, closed, why, gap, archetype,
     lead_s, intent, offer, rep_s, text, words) = row
    at_et = at.astimezone(_ET).strftime("%b %-d, %Y · %-I:%M %p ET")
    outcome = "CLOSED on this call" if closed else f"not closed — {why or 'unknown'}"
    if gap:
        outcome += f" (rep gap: {gap})"
    meta = (
        f"Outcome: {outcome} · archetype {archetype or '—'} · "
        f"AI scores: lead {lead_s} / intent {intent} / "
        f"offer understanding {offer} / rep execution {rep_s}"
    )
    body = (text or "").strip() if plain else _turns(words or [])
    if not body:
        body = "_(no transcript text)_"
    return (
        f"## {at_et} — {lead} × rep {rep} ({_fmt_duration(dur)})\n\n"
        f"{meta}\n\n{body}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", help="ET date (YYYY-MM-DD), inclusive")
    ap.add_argument("--end", help="ET date (YYYY-MM-DD), exclusive")
    ap.add_argument("--out", help="output path (default ~/exports/…)")
    ap.add_argument(
        "--plain", action="store_true",
        help="raw transcript text instead of speaker-labelled turns",
    )
    args = ap.parse_args()

    start_utc = (
        datetime.fromisoformat(args.start).replace(tzinfo=_ET).isoformat()
        if args.start else None
    )
    end_utc = (
        datetime.fromisoformat(args.end).replace(tzinfo=_ET).isoformat()
        if args.end else None
    )

    conn = _pg_conn()
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '120s'")
        cur.execute(_QUERY, {"start": start_utc, "end": end_utc})
        rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No DC-reviewed transcripts in that window.")
        return 1

    span = f"{args.start or 'all'}-to-{args.end or 'now'}"
    out = Path(
        args.out
        or Path.home() / "exports" / f"dc-call-transcripts-{span}.md"
    ).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    first_at = rows[0][0].astimezone(_ET).strftime("%b %-d, %Y")
    last_at = rows[-1][0].astimezone(_ET).strftime("%b %-d, %Y")
    header = (
        "# Digital College — ad-lead call transcripts\n\n"
        f"{len(rows)} connected calls ({first_at} → {last_at}), transcribed by "
        "Deepgram, each headed by the AI call review's verdict (outcome, "
        "archetype, 0-10 scores for lead quality / buying intent / offer "
        "understanding / rep execution). Speaker labels come from automatic "
        "diarization and don't say who the rep is — the header names the rep. "
        "CONTAINS PII — do not publish.\n"
    )
    sections = [_call_section(r, args.plain) for r in rows]
    out.write_text(header + "\n---\n\n" + "\n---\n\n".join(sections))
    size_mb = out.stat().st_size / 1e6
    print(f"Wrote {len(rows)} calls → {out} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
