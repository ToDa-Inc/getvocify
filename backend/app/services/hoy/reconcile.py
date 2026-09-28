"""Reconcile Hoy signals. A dismissed key stays dismissed. A down source does not resolve anything."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.services.hoy.signals import Signal


def merge_fresh(signals: list[Signal]) -> list[Signal]:
    """Same dedupe key keeps every commitment and its evidence. Nothing is overwritten."""
    grouped: dict[str, Signal] = {}
    order: list[str] = []
    for signal in signals:
        current = grouped.get(signal.dedupe_key)
        if current is None:
            grouped[signal.dedupe_key] = signal
            order.append(signal.dedupe_key)
            continue
        items = list(current.payload.get("items") or [_item(current)])
        items.append(_item(signal))
        grouped[signal.dedupe_key] = replace(current, payload={**current.payload, "items": items})
    return [grouped[key] for key in order]


def plan_reconcile(*, stored: list[dict], fresh: list[Signal], now: datetime, source_available: bool) -> dict:
    merged = merge_fresh(fresh) if source_available else []
    fresh_by_key = {signal.dedupe_key: signal for signal in merged}
    inserts: list[Signal] = []
    reopens: list[dict] = []
    resolves: list[str] = []
    known = {row["dedupe_key"]: row for row in stored}

    for key, signal in fresh_by_key.items():
        row = known.get(key)
        if row is None:
            inserts.append(signal)
            continue
        if row.get("status") == "snoozed" and _expired(row.get("snoozed_until"), now):
            reopens.append({
                "dedupe_key": key,
                "expected_version": row["version"],
                "version": row["version"] + 1,
                "payload": signal.payload,
            })

    if source_available:
        for key, row in known.items():
            if key in fresh_by_key:
                continue
            status = row.get("status")
            if status == "pending" or (status == "snoozed" and _expired(row.get("snoozed_until"), now)):
                resolves.append(key)
    return {"insert": inserts, "reopen": reopens, "resolve": resolves}


def _item(signal: Signal) -> dict:
    return {
        "type": signal.type,
        "text": signal.payload.get("text"),
        "evidence_refs": list(signal.payload.get("evidence_refs") or []),
        "due_at": signal.due_at.isoformat() if signal.due_at else None,
    }


def _expired(value, now: datetime) -> bool:
    parsed = _as_dt(value)
    return parsed is not None and parsed <= now


def _as_dt(value):
    if value is None or isinstance(value, datetime):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
