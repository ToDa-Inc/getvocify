"""When a Pipedrive task is due: the day the call gave it, else the default HubSpot's review suggests too.

The preview shows this date and the sync writes it, so the rep sees what lands in the CRM.
"""

from __future__ import annotations

from datetime import datetime

from app.models.memo import MemoExtraction
from app.services.hubspot.tasks import (
    _next_step_schedule_hints,
    default_task_due_at,
    detected_task_due_iso,
    format_next_step_task,
)


def next_step_due(extraction: MemoExtraction, index: int, step: str) -> tuple[datetime, bool]:
    """(due, inferred) of the index-th next step; inferred when the call named no day."""
    hints = _next_step_schedule_hints(extraction)
    hint = hints[index] if index < len(hints) else None
    due = format_next_step_task(step, contact_name=extraction.contactName, schedule_hint=hint or None).due_date
    return due, detected_task_due_iso(step, hint) is None


def commitment_due(due_at: datetime | None) -> tuple[datetime, bool]:
    return (due_at, False) if due_at else (default_task_due_at(), True)
