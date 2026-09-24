"""Turn stored memo intelligence into Hoy signals. No model call."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.hoy.signals import signals_for_contact, touch_from_intelligence


def _as_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _intelligence(memo: dict) -> dict:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    block = extraction.get("intelligence")
    return block if isinstance(block, dict) else {}


def _objections(extraction: dict, intelligence: dict) -> list[dict]:
    raw = intelligence.get("objections") or extraction.get("objections") or []
    open_rows: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                open_rows.append({"state": "open", "category": "other", "quote": text[:160]})
            continue
        if not isinstance(item, dict):
            continue
        if item.get("commercial_objection") is False:
            continue
        state = item.get("state") or item.get("resolution") or "open"
        if state not in {"open", "unknown"}:
            continue
        open_rows.append({
            "state": "open",
            "category": item.get("category") or "other",
            "quote": item.get("quote") or item.get("text") or "",
        })
    return open_rows


def _commitments(intelligence: dict) -> list[dict]:
    kept: list[dict] = []
    for item in intelligence.get("commitments") or []:
        if isinstance(item, dict) and item.get("due_at") and item.get("text"):
            kept.append(item)
    return kept


def fresh_signals(memos: list[dict], *, now: datetime, day_end: datetime) -> list:
    """One contact, one set of signals, from intelligence already on the memo."""
    groups: dict[str, list] = {}
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = _intelligence(memo)
        shaped = {
            **intelligence,
            "objections": _objections(extraction, intelligence),
            "commitments": _commitments(intelligence),
        }
        at = _as_dt(memo.get("capture_started_at") or memo.get("created_at"))
        contact = memo.get("hubspot_contact_id") or memo.get("contact_id")
        touch = touch_from_intelligence(
            memo_id=str(memo.get("id") or ""),
            contact_id=str(contact) if contact else None,
            deal_id=str(memo.get("hubspot_deal_id")) if memo.get("hubspot_deal_id") else None,
            at=at,
            connection_id=memo.get("connection_id"),
            intelligence=shaped if shaped.get("objections") or shaped.get("commitments") or shaped.get("interest") else None,
            history_complete=True,
        )
        if touch is None:
            continue
        groups.setdefault(touch.contact_id or touch.memo_id, []).append(touch)
    signals = []
    for touches in groups.values():
        signals.extend(signals_for_contact(touches, now=now, day_end=day_end))
    return signals


def day_end(now: datetime, tz_name: str) -> datetime:
    local = now.astimezone(ZoneInfo(tz_name or "Europe/Madrid"))
    end = local.replace(hour=23, minute=59, second=59, microsecond=0)
    return end.astimezone(timezone.utc)


def persist_new_signals(supabase, *, company_id: str, user_id: str, signals: list, known: set[str]) -> int:
    """Insert missing keys. Do not resolve older rows from a partial memo window."""
    written = 0
    for signal in signals:
        if signal.dedupe_key in known:
            continue
        supabase.table("action_signals").upsert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "connection_id": signal.connection_id or "",
                "contact_id": signal.contact_id,
                "deal_id": signal.deal_id,
                "memo_id": signal.source_memo_id,
                "type": signal.type,
                "dedupe_key": signal.dedupe_key,
                "payload": {
                    **signal.payload,
                    **({"due_at": signal.due_at.isoformat()} if signal.due_at else {}),
                },
                "status": "pending",
                "coverage": "complete",
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
        ).execute()
        known.add(signal.dedupe_key)
        written += 1
    return written


def refresh_hoy_signals(supabase, *, company_id: str, user_id: str, now: datetime, tz_name: str) -> int:
    try:
        stored = (
            supabase.table("memos")
            .select("id,hubspot_contact_id,hubspot_deal_id,extraction,capture_started_at,created_at")
            .eq("user_id", user_id)
            .or_(f"company_id.eq.{company_id},company_id.is.null")
            .order("created_at", desc=True)
            .limit(40)
            .execute()
        )
        existing = (
            supabase.table("action_signals")
            .select("dedupe_key")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        return 0
    signals = fresh_signals(list(stored.data or []), now=now, day_end=day_end(now, tz_name))
    known = {str(row.get("dedupe_key") or "") for row in (existing.data or [])}
    try:
        return persist_new_signals(
            supabase,
            company_id=company_id,
            user_id=user_id,
            signals=signals,
            known=known,
        )
    except Exception:
        return 0
