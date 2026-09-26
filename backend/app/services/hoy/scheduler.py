"""One Hoy run per company-local date. A partial source does not become a complete pulse."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.hoy.reasons import reason
from app.services.hoy.signals import DEFAULT_LIMIT, Signal, rank_cards
from app.services.hubspot.account_info import build_contact_record_url
from app.services.pipedrive.record_urls import build_pipedrive_record_url


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
            title = props.get("hs_task_subject") or ""
            if str(title).lower().startswith("(sample"):
                continue
            items.append({
                "remote_id": str(row["id"]),
                "title": title,
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


def task_request(provider: str, cursor: str | None) -> dict:
    if provider == "hubspot":
        body = {
            "limit": 100,
            "properties": ["hs_task_subject", "hs_task_status", "vocify_dedupe_key"],
            "filterGroups": [{"filters": [
                {"propertyName": "hs_task_status", "operator": "NEQ", "value": "COMPLETED"},
            ]}],
        }
        if cursor:
            body["after"] = cursor
        return {"method": "POST", "path": "/crm/v3/objects/tasks/search", "json": body}
    if provider == "pipedrive":
        params = {"done": 0, "limit": 100}
        if cursor:
            params["start"] = cursor
        return {"method": "GET", "path": "/activities", "params": params}
    raise ValueError(f"proveedor no soportado: {provider}")


def _next_cursor(provider: str, payload: dict) -> str | None:
    if provider == "hubspot":
        cursor = ((payload.get("paging") or {}).get("next") or {}).get("after")
        return str(cursor) if cursor else None
    extra = payload.get("additional_data") or {}
    pagination = extra.get("pagination") or {}
    if pagination.get("more_items_in_collection"):
        start = pagination.get("next_start")
        return str(start if start is not None else extra.get("next_cursor") or "next")
    if extra.get("next_cursor"):
        return str(extra["next_cursor"])
    return None


def collect_open_tasks(provider: str, fetch, *, connection_id: str, max_pages: int = 3) -> tuple[list[dict], str]:
    """Walk open-task pages. A failed later page keeps what was already read and stays partial."""
    items: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        try:
            payload = fetch(task_request(provider, cursor)) or {}
        except (TimeoutError, OSError):
            return (items, "partial") if items else ([], "unavailable")
        page, coverage = open_manual_tasks(provider, payload, connection_id=connection_id)
        if coverage in {"forbidden", "unavailable"} and not page:
            return (items, "partial") if items else ([], coverage)
        items.extend(page)
        cursor = _next_cursor(provider, payload)
        if not cursor:
            return items, "complete"
    return items, "partial"


def claim_daily_run_statement(company_id: str, local_date) -> str:
    return (
        "INSERT INTO hoy_daily_runs (company_id, local_date, status) VALUES ("
        f"'{company_id}', '{local_date.isoformat()}', 'started') ON CONFLICT DO NOTHING;"
    )


def claim_if_due(now: datetime, tz_name: str | None, company_id: str, *, hour: int = 8) -> str | None:
    """SQL to claim today's run after the local hour, or None while the day is still closed."""
    tz = tz_name or "Europe/Madrid"
    if not daily_run_due(now, tz, hour):
        return None
    return claim_daily_run_statement(company_id, company_local_date(now, tz))


def attempt_daily_run_claim(
    supabase,
    company_id: str,
    now: datetime,
    tz_name: str | None,
    *,
    hour: int = 8,
) -> None:
    """Best-effort claim on GET /today. Fake Supabase clients without upsert are skipped."""
    if claim_if_due(now, tz_name, company_id, hour=hour) is None:
        return
    table_fn = getattr(supabase, "table", None)
    if table_fn is None:
        return
    table = table_fn("hoy_daily_runs")
    upsert = getattr(table, "upsert", None)
    if upsert is None:
        return
    local_date = company_local_date(now, tz_name or "Europe/Madrid")
    try:
        upsert(
            {"company_id": company_id, "local_date": local_date.isoformat(), "status": "started"},
            on_conflict="company_id,local_date",
            ignore_duplicates=True,
        ).execute()
    except Exception:
        return


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


def card_detail(payload: dict) -> str | None:
    """The line the rep said or heard. The reason already states the type."""
    text = " ".join(str(payload.get("quote") or "").split())
    if len(text) > 160:
        text = text[:157].rstrip() + "…"
    return text or None


def contact_record_url(
    *,
    provider: str | None,
    contact_id: str | None,
    portal_id: str | None = None,
    company_domain: str | None = None,
) -> str | None:
    """Where the card opens. No contact, no link."""
    contact = str(contact_id or "").strip()
    if not contact:
        return None
    name = str(provider or "").strip().lower()
    if name == "hubspot" and portal_id:
        return build_contact_record_url(str(portal_id), contact)
    domain = str(company_domain or "").strip()
    if name == "pipedrive" and domain:
        return build_pipedrive_record_url(domain, "person", contact)
    return None


def build_today_view(
    *,
    signals: list[Signal],
    manual_tasks: list[dict],
    now: datetime,
    coverage: dict,
    generated_at: str,
    lang: str = "es",
    provider: str | None = None,
    portal_id: str | None = None,
    company_domain: str | None = None,
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
            "reason": reason(card.primary, lang=lang),
            "remote_id": payload.get("remote_id"),
            "origins": payload.get("origins") or ["detected"],
            "supporting": [item.type for item in card.supporting],
            "detail": card_detail(payload),
            "open_url": contact_record_url(
                provider=provider,
                contact_id=card.primary.contact_id,
                portal_id=portal_id,
                company_domain=company_domain,
            ),
        })
        if payload.get("contact_name"):
            items[-1]["contact_name"] = payload["contact_name"]
        if payload.get("signal_id"):
            items[-1]["id"] = payload["signal_id"]
            items[-1]["version"] = payload.get("version")
            items[-1]["status"] = payload.get("status") or "pending"
            if payload.get("undo_deadline"):
                items[-1]["undo_deadline"] = payload["undo_deadline"]
            if payload.get("last_action_request_id"):
                items[-1]["last_action_request_id"] = payload["last_action_request_id"]
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
            "open_url": contact_record_url(
                provider=provider,
                contact_id=task.get("contact_id"),
                portal_id=portal_id,
                company_domain=company_domain,
            ),
        })
    visible = items[:DEFAULT_LIMIT]
    folded += len(items) - len(visible)
    complete = bool(coverage) and all(value == "complete" for value in coverage.values())
    return {
        "items": visible,
        "pulse": len(items) if complete else None,
        "folded_count": folded,
        "generated_at": generated_at,
        "coverage": dict(coverage),
    }
