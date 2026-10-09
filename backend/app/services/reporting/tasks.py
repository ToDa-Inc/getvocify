"""T12 bell "Tareas": today's pending Hoy signals, read straight from action_signals.

This module deliberately does not import anything from `app.services.hoy` or
`app.api.today` - those are owned by a different, concurrently running task. It reads the
action_signals rows itself and writes its own (much smaller) reason text, independent of
`hoy/reasons.py`'s wording. Only the two signal types the plan calls out for this bell
block are surfaced: commitment_due and callback_no_answer."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TASK_TYPES: tuple[str, ...] = ("commitment_due", "callback_no_answer")
MAX_TASKS = 8

_REASON_ES = {
    "commitment_due": "Tienes un compromiso pendiente con este contacto.",
    "callback_no_answer": "Le llamaste y no contestó; todavía no habéis vuelto a hablar.",
}


def task_reason(signal_type: str, *, lang: str = "es") -> str:
    """A short, self-contained reason - not hoy/reasons.py's wording, which depends on
    payload shapes this module intentionally does not read."""
    return _REASON_ES.get(signal_type, "Tienes una tarea pendiente en Hoy.")


def pending_tasks(rows: list[dict]) -> list[dict]:
    """Pending commitment_due/callback_no_answer rows, most recently updated first."""
    kept = [row for row in rows if row.get("status") == "pending" and row.get("type") in TASK_TYPES]
    kept.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    return [
        {
            "id": row.get("id"),
            "type": row.get("type"),
            "contact_id": row.get("contact_id"),
            "memo_id": row.get("memo_id"),
            "reason": task_reason(row.get("type")),
        }
        for row in kept[:MAX_TASKS]
    ]


def load_pending_tasks(supabase, *, user_id: str, company_id: str) -> list[dict] | None:
    """None when action_signals cannot be read: an unread queue is not "no tasks"."""
    try:
        rows = (
            supabase.table("action_signals")
            .select("id,type,contact_id,memo_id,status,updated_at,created_at")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .eq("status", "pending")
            .in_("type", list(TASK_TYPES))
            .execute()
        ).data or []
    except Exception:
        logger.exception("bell tasks: read failed")
        return None
    return pending_tasks(rows)
