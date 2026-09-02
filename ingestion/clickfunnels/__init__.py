"""ClickFunnels form-submission ingestion.

Submissions arrive via a ClickFunnels workflow Webhook step POSTing to
`api/clickfunnels_events.py`, which captures the raw payload into
`webhook_deliveries` (source='clickfunnels_webhook') and then calls
`pipeline.process_pending` to normalize each capture into the
`typeform_responses` shape. Downstream (facts refresh, DC Setup,
dashboards) reads both sources through the same tables and never
distinguishes them. See docs/runbooks/clickfunnels_ingestion.md.
"""

from ingestion.clickfunnels.parser import (  # noqa: F401
    QUALIFY_FIELD_REF,
    form_definition_row,
    form_id_for,
    parse_submission,
)
from ingestion.clickfunnels.pipeline import process_pending  # noqa: F401
