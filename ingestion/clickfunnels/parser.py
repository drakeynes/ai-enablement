"""ClickFunnels webhook payload → typeform_responses-shaped rows.

The CF workflow webhook sends ONE FLAT JSON OBJECT per submission whose
keys were mapped by hand in the workflow step (verified against the
first live capture, 2026-09-02):

    email, phone (E.164), phone_formatted, name,
    submitted_at (ISO-8601 UTC),
    campaign_id, adset_id, ad_id, utm_* — the Meta URL macros,
    fbp, fbc, client_ip_address, client_user_agent, event_id,
    funnel (human label, e.g. "Aman VSL Funnel"), page_url,
    has_budget_200 ("Yes"/"No" — the can-pay qualifying answer).

We normalize into the EXACT shape `refresh_dc_ads_facts()` reads from
`typeform_responses` (migration 0154's jsonb paths):

  - answers[]: {"type": "phone_number", "phone_number": ...},
               {"type": "email", "email": ...},
               {"type": "choice", "field": {"ref": QUALIFY_FIELD_REF},
                "choice": {"label": "Yes"|"No"}}
  - hidden: the Typeform hidden-field contract keys (campaign_id,
    adset_id, ad_id, utm_*, fbp, fbc, ip, event_id, funnel, phone,
    email) — LP-summary filtering + identity fallbacks read these.

Form identity: the payload carries no ClickFunnels form/page id, so the
stable identity is the funnel label, slugified with a `cf:` prefix
(e.g. "Aman VSL Funnel" → `cf:aman-vsl-funnel`). That id goes in
`dc_landing_pages.typeform_id` via DC Setup like any Typeform id.
Response identity: `cf:<event_id>` (the LP's per-submission uuid),
falling back to a payload hash — idempotent across webhook retries.

Pure functions, no I/O — the DB writes live in pipeline.py.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

CF_FORM_PREFIX = "cf:"
QUALIFY_FIELD_REF = "cf_has_budget_200"
_QUALIFY_SOURCE_KEY = "has_budget_200"

# Payload keys copied into `hidden` verbatim (the Typeform hidden-field
# contract). client_ip_address is renamed to `ip` to match it.
_HIDDEN_KEYS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "campaign_id",
    "adset_id",
    "ad_id",
    "fbp",
    "fbc",
    "event_id",
    "funnel",
    "phone",
    "email",
)

_YES = {"yes", "y", "true", "1"}
_NO = {"no", "n", "false", "0"}


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "unknown"


def form_id_for(payload: dict[str, Any]) -> str:
    """Stable form id for a submission's funnel: `cf:<slugified label>`."""
    funnel = str(payload.get("funnel") or "").strip()
    return CF_FORM_PREFIX + _slugify(funnel or "unlabeled")


def _normalize_yes_no(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    low = text.lower()
    if low in _YES:
        return "Yes"
    if low in _NO:
        return "No"
    return text  # unknown copy passes through; registry config decides


def parse_submission(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Project one captured CF payload into a typeform_responses row.

    Returns None when the payload has no submitted_at or carries neither
    an email nor a phone (nothing downstream could ever match it).
    """
    if not isinstance(payload, dict):
        return None
    submitted_at = str(payload.get("submitted_at") or "").strip()
    email = str(payload.get("email") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    if not submitted_at or (not email and not phone):
        return None

    event_id = str(payload.get("event_id") or "").strip()
    if event_id:
        response_id = f"cf:{event_id}"
    else:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:24]
        response_id = f"cf:{digest}"

    answers: list[dict[str, Any]] = []
    if phone:
        answers.append(
            {
                "type": "phone_number",
                "phone_number": phone,
                "field": {"ref": "cf_phone", "type": "phone_number"},
            }
        )
    if email:
        answers.append(
            {
                "type": "email",
                "email": email,
                "field": {"ref": "cf_email", "type": "email"},
            }
        )
    qualify_label = _normalize_yes_no(payload.get(_QUALIFY_SOURCE_KEY))
    if qualify_label is not None:
        answers.append(
            {
                "type": "choice",
                "choice": {"label": qualify_label},
                "field": {"ref": QUALIFY_FIELD_REF, "type": "multiple_choice"},
            }
        )

    hidden = {k: str(payload[k]) for k in _HIDDEN_KEYS if payload.get(k)}
    if payload.get("client_ip_address"):
        hidden["ip"] = str(payload["client_ip_address"])

    return {
        "response_id": response_id,
        "form_id": form_id_for(payload),
        "landed_at": None,
        "submitted_at": submitted_at,
        "metadata": {
            "source": "clickfunnels",
            "page_url": payload.get("page_url"),
            "name": payload.get("name"),
            "user_agent": payload.get("client_user_agent"),
        },
        "hidden": hidden,
        "calculated": {},
        "answers": answers,
    }


def form_definition_row(form_id: str, funnel_label: str) -> dict[str, Any]:
    """A typeform_forms-shaped definition row so the DC Setup pickers
    (form dropdown + qualification-question picker) can offer this form
    exactly like a mirrored Typeform."""
    return {
        "form_id": form_id,
        "title": f"{funnel_label or 'ClickFunnels form'} (ClickFunnels)",
        "fields": [
            {
                "id": QUALIFY_FIELD_REF,
                "ref": QUALIFY_FIELD_REF,
                "title": "Has $200 budget for AI tools (ClickFunnels: has_budget_200)",
                "type": "multiple_choice",
                "properties": {"choices": [{"label": "Yes"}, {"label": "No"}]},
            }
        ],
        "hidden_fields": sorted(set(_HIDDEN_KEYS) | {"ip"}),
    }
