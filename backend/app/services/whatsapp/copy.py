"""Contact-first WhatsApp copy for Meta copilot previews."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

IDENTITY_NOISE = frozenset(
    {
        "contact_name",
        "company_name",
        "dealname",
        "email",
        "phone",
        "firstname",
        "lastname",
    }
)

OBJECT_GROUP_LABELS = {
    "contacts": "Contacto",
    "companies": "Empresa",
    "deals": "Deal",
}

GROUP_ORDER = ("contacts", "companies", "deals")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _field_name(update: Any) -> str:
    if isinstance(update, dict):
        return str(update.get("field_name") or "")
    return str(getattr(update, "field_name", "") or "")


def _get(update: Any, key: str, default: Any = None) -> Any:
    if isinstance(update, dict):
        return update.get(key, default)
    return getattr(update, key, default)


def is_identity_noise_field(update: Any) -> bool:
    return _field_name(update) in IDENTITY_NOISE


def is_insights_field(field_name: str) -> bool:
    name = str(field_name or "")
    return (
        name == "description"
        or name == "hs_next_step"
        or name.startswith("next_step_task_")
    )


def values_match(update: Any) -> bool:
    current = _norm(_get(update, "current_value"))
    new = _norm(_get(update, "new_value"))
    if not current or current == "(empty)":
        return False
    if _field_name(update).lower() == "email":
        return current.lower() == new.lower()
    return current == new


def visible_crm_updates(updates: list[Any] | None) -> list[Any]:
    """Port of chrome-extension/lib/review-insights.js visibleCrmUpdates."""
    result: list[Any] = []
    for update in updates or []:
        if not update or not _field_name(update):
            continue
        if is_identity_noise_field(update):
            continue
        if is_insights_field(_field_name(update)):
            continue
        if _get(update, "object_type") == "task":
            continue
        if not _norm(_get(update, "new_value")) and not _get(update, "userAdded"):
            continue
        if values_match(update):
            continue
        result.append(update)
    return result


def _target_line(preview: Any) -> str:
    contact = _get(preview, "selected_contact")
    contact_name = _norm(_get(contact, "name")) if contact else ""
    company_name = _norm(_get(contact, "company_name")) if contact else ""

    if contact_name and company_name:
        header = f"*{contact_name}* · {company_name}"
    elif contact_name:
        header = f"*{contact_name}*"
    elif company_name:
        header = company_name
    else:
        header = "Contacto"

    if _get(preview, "skip_deal"):
        return f"{header}\nSolo contacto"

    deal = _get(preview, "selected_deal")
    if _get(preview, "is_new_deal"):
        return f"{header}\nDeal · Nuevo"
    if deal:
        deal_name = _norm(_get(deal, "deal_name")) or "Deal"
        return f"{header}\nDeal · {deal_name}"
    return f"{header}\nSolo contacto"


def _format_field_line(update: Any) -> str:
    label = _norm(_get(update, "field_label")) or _field_name(update)
    value = _norm(_get(update, "new_value")) or "—"
    return f"· {label}: {value}"


def _group_updates(updates: list[Any], skip_deal: bool) -> list[tuple[str, list[Any]]]:
    grouped: dict[str, list[Any]] = {}
    for update in updates:
        object_type = _get(update, "object_type") or "deals"
        if skip_deal and object_type == "deals":
            continue
        grouped.setdefault(object_type, []).append(update)

    return [
        (OBJECT_GROUP_LABELS.get(object_type, object_type), grouped[object_type])
        for object_type in GROUP_ORDER
        if object_type in grouped
    ]


def _iso_date_or_null(value: Any) -> str | None:
    raw = _norm(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    return None


def format_task_due_label(iso_date: Any, today: str | None = None) -> str:
    """Port of chrome-extension/lib/review-insights.js formatTaskDueLabel."""
    day = _iso_date_or_null(iso_date)
    if not day:
        return ""
    today_iso = _iso_date_or_null(today)
    if today_iso and day == today_iso:
        return "Hoy"
    try:
        parsed = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    return f"{_WEEKDAY_LABELS[parsed.weekday()]} {parsed.day}"


def task_rows_from_preview(
    proposed_updates: list[Any] | None = None,
    next_steps: list[str] | None = None,
    next_step_schedules: list[str] | None = None,
    due_dates_by_index: list[str] | None = None,
) -> list[dict[str, str | None]]:
    """Port of chrome-extension/lib/review-insights.js taskRowsFromPreview."""
    preview_tasks = [
        update
        for update in (proposed_updates or [])
        if _field_name(update).startswith("next_step_task_")
    ]

    def due_for_index(index: int) -> str | None:
        candidates: list[Any] = []
        if due_dates_by_index and index < len(due_dates_by_index):
            candidates.append(due_dates_by_index[index])
        if index < len(preview_tasks):
            candidates.append(_get(preview_tasks[index], "due_date"))
        if next_step_schedules and index < len(next_step_schedules):
            candidates.append(next_step_schedules[index])
        for candidate in candidates:
            due = _iso_date_or_null(candidate)
            if due:
                return due
        return None

    steps = [_norm(step) for step in (next_steps or []) if _norm(step)]
    if steps:
        rows: list[dict[str, str | None]] = []
        for index, step in enumerate(steps):
            task_text = ""
            if index < len(preview_tasks):
                task_text = _norm(_get(preview_tasks[index], "new_value"))
            rows.append({"text": task_text or step, "due_date": due_for_index(index)})
        return rows

    return [
        {
            "text": _norm(_get(update, "new_value")),
            "due_date": due_for_index(index),
        }
        for index, update in enumerate(preview_tasks)
        if _norm(_get(update, "new_value"))
    ]


def _format_tasks(
    task_rows: list[dict[str, str | None]],
    today: str | None = None,
) -> str:
    if not task_rows:
        return ""
    lines: list[str] = []
    for row in task_rows:
        text = _norm(row.get("text"))
        if not text:
            continue
        due_label = format_task_due_label(row.get("due_date"), today=today)
        if due_label:
            lines.append(f"· {text} · {due_label}")
        else:
            lines.append(f"· {text}")
    if not lines:
        return ""
    return f"Tareas\n" + "\n".join(lines)


def _count_label(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def briefing_text(
    preview: Any,
    next_steps: list[str] | None = None,
    next_step_schedules: list[str] | None = None,
    due_dates_by_index: list[str] | None = None,
    today: str | None = None,
) -> str:
    parts = [_target_line(preview)]

    task_rows = task_rows_from_preview(
        proposed_updates=_get(preview, "proposed_updates") or [],
        next_steps=next_steps,
        next_step_schedules=next_step_schedules,
        due_dates_by_index=due_dates_by_index,
    )
    tasks = _format_tasks(task_rows, today=today)
    if tasks:
        parts.append(tasks)

    visible = visible_crm_updates(_get(preview, "proposed_updates") or [])
    for group_label, group_updates in _group_updates(visible, bool(_get(preview, "skip_deal"))):
        lines = "\n".join(_format_field_line(update) for update in group_updates)
        parts.append(f"{group_label}\n{lines}")

    return "\n\n".join(parts)


def button_body(preview: Any, next_steps: list[str] | None = None) -> str:
    target = _target_line(preview).replace("\n", " · ")
    task_count = len([s for s in (next_steps or []) if _norm(s)])
    field_count = len(visible_crm_updates(_get(preview, "proposed_updates") or []))

    counts: list[str] = []
    if task_count:
        counts.append(
            f"{task_count} {_count_label(task_count, 'tarea', 'tareas')}"
        )
    if field_count:
        counts.append(
            f"{field_count} {_count_label(field_count, 'campo', 'campos')}"
        )

    summary = " · ".join(counts) if counts else "Sin cambios"
    return f"{target}\n¿Actualizo HubSpot?\n{summary}"
