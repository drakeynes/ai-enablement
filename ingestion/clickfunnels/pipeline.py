"""Process captured ClickFunnels webhook deliveries into the mirror.

Reads `webhook_deliveries` rows (source='clickfunnels_webhook',
processing_status='received') that `api/clickfunnels_events.py` captured,
normalizes each payload via parser.parse_submission, ensures a
typeform_forms definition row exists for the form, upserts the response
into typeform_responses (idempotent on response_id), and marks the
delivery row processed.

Status semantics on the capture row:
  received  → captured, not yet normalized (the replay queue)
  processed → normalized into typeform_responses
  malformed → payload unusable (no submitted_at / no email+phone) —
              processing_error says why; the raw payload stays for triage
  failed    → unexpected exception; processing_error carries the message.
              Re-run by setting processing_status back to 'received'.

Called inline by the webhook endpoint after each capture (drains up to a
small batch per invocation, so one failed delivery heals on the next
submission). Safe to call from a script for larger replays.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ingestion.clickfunnels.parser import (
    form_definition_row,
    parse_submission,
)

logger = logging.getLogger("ai_enablement.clickfunnels_pipeline")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark(db, webhook_id: str, status: str, error: str | None = None) -> None:
    patch: dict[str, Any] = {
        "processing_status": status,
        "processed_at": _now_iso(),
    }
    if error:
        patch["processing_error"] = error[:500]
    db.table("webhook_deliveries").update(patch).eq("webhook_id", webhook_id).execute()


def _ensure_form_definition(db, form_id: str, funnel_label: str) -> None:
    existing = (
        db.table("typeform_forms")
        .select("form_id")
        .eq("form_id", form_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return
    row = form_definition_row(form_id, funnel_label)
    row["last_updated_at"] = _now_iso()
    row["definition_synced_at"] = _now_iso()
    db.table("typeform_forms").upsert(
        row, on_conflict="form_id", ignore_duplicates=True
    ).execute()
    logger.info("clickfunnels: registered form definition %s", form_id)


def process_pending(db, limit: int = 20) -> dict[str, int]:
    """Normalize up to `limit` captured-but-unprocessed deliveries."""
    counts = {"processed": 0, "malformed": 0, "failed": 0}
    pending = (
        db.table("webhook_deliveries")
        .select("webhook_id, payload")
        .eq("source", "clickfunnels_webhook")
        .eq("processing_status", "received")
        .order("received_at")
        .limit(limit)
        .execute()
    )
    for row in pending.data or []:
        webhook_id = row["webhook_id"]
        try:
            parsed = parse_submission(row.get("payload") or {})
            if parsed is None:
                _mark(db, webhook_id, "malformed", "no submitted_at or no email/phone")
                counts["malformed"] += 1
                continue
            funnel_label = str((row.get("payload") or {}).get("funnel") or "").strip()
            _ensure_form_definition(db, parsed["form_id"], funnel_label)
            parsed["ingested_at"] = _now_iso()
            db.table("typeform_responses").upsert(
                parsed, on_conflict="response_id"
            ).execute()
            _mark(db, webhook_id, "processed")
            counts["processed"] += 1
            logger.info(
                "clickfunnels: normalized %s -> %s (%s)",
                webhook_id,
                parsed["response_id"],
                parsed["form_id"],
            )
        except Exception as exc:  # per-row fail-soft; the rest still drain
            logger.exception("clickfunnels: processing %s failed: %s", webhook_id, exc)
            try:
                _mark(db, webhook_id, "failed", str(exc))
            except Exception:
                pass
            counts["failed"] += 1
    return counts
