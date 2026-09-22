"""One Hoy run per company-local date. A partial source does not become a complete pulse."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.hoy.reasons import reason
from app.services.hoy.signals import Signal, rank_cards


def company_local_date(now: datetime, tz_name: str):
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ZoneInfo(tz_name)).date()


def daily_run_due(now: datetime, tz_name: str, hour: int = 8) -> bool:
    """True from the configured local hour onward. Before that hour, the same date is not due."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(tz_name))
    return local.hour >= hour


def due_company_ids(now: datetime, companies: list[dict], hour: int = 8) -> list[str]:
    due = []
    for company in companies:
        tz_name = company.get("timezone") or "Europe/Madrid"
        local_hour = int(company.get("hoy_hour") if company.get("hoy_hour") is not None else hour)
        if daily_run_due(now, tz_name, local_hour):
            due.append(str(company["company_id"]))
    return due


_OPEN = {"NOT_STARTED", "WAITING"}


def open_manual_tasks(provider: str, payload: dict, *, connection_id: str) -> tuple[list[dict], str]:
    """Open CRM tasks only. A next page is partial. A finished task is not today's work."""
    error_kind = str(payload.get("error_kind") or "")
    if error_kind:
        if error_kind in {"401", "403", "forbidden", "email_scope_missing"}:
            return [], "forbidden"
        return [], "unavailable"
    if provider == "hubspot":
        items = []
        for row in payload.get("results") or []:
            props = row.get("properties") or {}
            if str(props.get("hs_task_status") or "NOT_STARTED") not in _OPEN:
                continue
            items.append({
                "remote_id": str(row["id"]),
                "title": props.get("hs_task_subject") or "",
                "contact_id": props.get("contact_id"),
                "connection_id": connection_id,
                "linked_dedupe_key": props.get("vocify_dedupe_key") or None,
            })
        cursor = ((payload.get("paging") or {}).get("next") or {}).get("after")
        return items, "partial" if cursor else "complete"
    if provider == "pipedrive":
        items = []
        for row in payload.get("data") or []:
            if row.get("done"):
                continue
            person = row.get("person_id")
            items.append({
                "remote_id": str(row["id"]),
                "title": row.get("subject") or "",
                "contact_id": str(person) if person else None,
                "connection_id": connection_id,
                "linked_dedupe_key": row.get("vocify_dedupe_key") or None,
            })
        extra = payload.get("additional_data") or {}
        more = (extra.get("pagination") or {}).get("more_items_in_collection") or extra.get("next_cursor")
        return items, "partial" if more else "complete"
    raise ValueError(f"proveedor no soportado: {provider}")


def claim_daily_run_statement(company_id: str, local_date) -> str:
    return (
        "INSERT INTO hoy_daily_runs (company_id, local_date, status) VALUES ("
        f"'{company_id}', '{local_date.isoformat()}', 'started') ON CONFLICT DO NOTHING;"
    )


def attach_manual(signals: list[Signal], tasks: list[dict]) -> tuple[list[Signal], list[dict]]:
    """Link only when the task names the signal. The same title is not a match."""
    by_key = {signal.dedupe_key: signal for signal in signals}
    loose = []
    for task in tasks:
        key = task.get("linked_dedupe_key")
        signal = by_key.get(key) if key else None
        if signal is None:
            loose.append(task)
            continue
        origins = list(signal.payload.get("origins") or ["detected"])
        if "manual" not in origins:
            origins.append("manual")
        by_key[key] = replace(signal, payload={
            **signal.payload,
            "remote_id": task.get("remote_id"),
            "origins": origins,
        })
    return list(by_key.values()), loose


def rebind_contact(rows: list[dict], *, memo_id: str, contact_id: str) -> list[dict]:
    """Move a provisional contact onto the resolved one. Do not keep both."""
    kept = []
    occupied = {
        (row.get("connection_id"), row.get("dedupe_key"), row.get("contact_id"))
        for row in rows
    }
    for row in rows:
        if row.get("memo_id") != memo_id or row.get("contact_id") == contact_id:
            kept.append(row)
            continue
        target = (row.get("connection_id"), row.get("dedupe_key"), contact_id)
        if target in occupied:
            continue
        updated = {**row, "contact_id": contact_id}
        occupied.add(target)
        kept.append(updated)
    return kept


def build_today_view(
    *,
    signals: list[Signal],
    manual_tasks: list[dict],
    now: datetime,
    coverage: dict,
    generated_at: str,
) -> dict:
    linked, loose = attach_manual(signals, manual_tasks)
    cards, folded = rank_cards(linked, now=now) if linked else ([], 0)
    items = []
    for card in cards:
        payload = card.primary.payload
        items.append({
            "type": card.primary.type,
            "dedupe_key": card.primary.dedupe_key,
            "contact_id": card.primary.contact_id,
            "connection_id": card.primary.connection_id,
            "reason": reason(card.primary),
            "remote_id": payload.get("remote_id"),
            "origins": payload.get("origins") or ["detected"],
            "supporting": [item.type for item in card.supporting],
        })
    for task in loose:
        items.append({
            "type": "manual_task",
            "dedupe_key": None,
            "contact_id": task.get("contact_id"),
            "connection_id": task.get("connection_id"),
            "reason": task.get("title") or "",
            "remote_id": task.get("remote_id"),
            "origins": ["manual"],
            "supporting": [],
        })
    complete = bool(coverage) and all(value == "complete" for value in coverage.values())
    return {
        "items": items,
        "pulse": len(items) if complete else None,
        "folded_count": folded,
        "generated_at": generated_at,
        "coverage": dict(coverage),
    }
