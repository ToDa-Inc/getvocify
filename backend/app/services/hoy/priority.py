"""Priority ranking. Incomplete history is not 'never called', and an agreed meeting is not a cold call."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def candidate_id(connection_id: str, contact_id: str, deal_id: Optional[str]) -> str:
    return f"{connection_id}:{contact_id}:{deal_id or ''}"


def empty_priority_copy(*, connected: bool, coverage: str) -> dict:
    if not connected:
        return {"title": "Conecta tu CRM", "action": "Conectar CRM"}
    if coverage == "complete":
        return {"title": "No hay contactos prioritarios ahora", "action": "Abrir contactos en CRM"}
    return {"title": "Falta parte del historial", "action": "Reintentar"}


def rank_candidates(candidates: list[dict], now: datetime, recent_days: int = 14) -> list[dict]:
    window = timedelta(days=recent_days)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ranked = []
    for raw in candidates:
        if raw.get("meeting_agreed") is True:
            continue
        if raw.get("deal_status") == "closed":
            continue
        if raw.get("owner_ambiguous"):
            continue
        coverage = raw.get("coverage") or "partial"
        last_call = raw.get("last_call_at")
        pain_at = _as_dt(raw.get("pain_at"))
        recent_pain = bool(raw.get("pain_confirmed") and pain_at and now - pain_at <= window)
        never_called = last_call is None
        if recent_pain:
            tier = 1
            reason = "Confirmó el problema; falta acordar el siguiente paso"
        elif never_called and coverage != "complete":
            tier = None
            reason = "Falta parte del historial"
        elif never_called:
            tier = 2
            reason = "Sin llamadas registradas"
        else:
            tier = 3
            reason = "Seguimiento pendiente"
        identity = candidate_id(raw["connection_id"], raw["contact_id"], raw.get("deal_id"))
        ranked.append({
            "id": identity,
            "connection_id": raw["connection_id"],
            "contact_id": raw["contact_id"],
            "deal_id": raw.get("deal_id"),
            "tier": tier,
            "reason": reason,
            "evidence_refs": list(raw.get("evidence_refs") or []),
            "coverage": coverage,
            "never_called": never_called and coverage == "complete",
        })
    ranked.sort(key=lambda row: (row["tier"] is None, row["tier"] or 0, row["id"]))
    return ranked


def _as_dt(value):
    if value is None or isinstance(value, datetime):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
