"""Turn stored memo intelligence into Hoy signals. No model call."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.hoy.heat import heat_score
from app.services.hoy.memo_facts import _pain
from app.services.hoy.signals import Signal, never_contacted_signal, signals_for_contact, touch_from_intelligence
from app.services.intelligence import extract


HOY_MEMO_LIMIT = 40
DEFAULT_CALLBACK_AFTER_DAYS = 2


def as_dt(value) -> datetime | None:
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


def _objections(extraction: dict, intelligence: dict, *, current: bool) -> list[dict]:
    c04 = intelligence.get("objections")
    # An empty list from current C04 means "no objection"; from a stale run it proves nothing.
    trusted = isinstance(c04, list) and (bool(c04) or current)
    raw = c04 if trusted else extraction.get("objections") or []
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


def fresh_signals(
    memos: list[dict],
    *,
    now: datetime,
    day_end: datetime,
    lead_tiers_enabled: bool = False,
    callback_after_days: int = DEFAULT_CALLBACK_AFTER_DAYS,
) -> list:
    """One contact, one set of signals, from intelligence already on the memo.

    `lead_tiers_enabled` is HOY_LEAD_TIERS_ENABLED for a SDR/General rep (T5): off, this
    is byte-identical to before (no callback_no_answer, no heat on the payload)."""
    groups: dict[str, list] = {}
    pain_by_memo: dict[str, bool] = {}
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = _intelligence(memo)
        shaped = {
            **intelligence,
            "objections": _objections(extraction, intelligence, current=bool(intelligence) and extract.is_current(memo)),
            "commitments": _commitments(intelligence),
        }
        at = as_dt(memo.get("capture_started_at") or memo.get("created_at"))
        contact = memo.get("hubspot_contact_id") or memo.get("contact_id")
        memo_id = str(memo.get("id") or "")
        pain_by_memo[memo_id] = _pain(extraction) or intelligence.get("pain_confirmed") is True
        touch = touch_from_intelligence(
            memo_id=memo_id,
            contact_id=str(contact) if contact else None,
            deal_id=str(memo.get("hubspot_deal_id")) if memo.get("hubspot_deal_id") else None,
            at=at,
            connection_id=memo.get("connection_id"),
            intelligence=shaped if shaped.get("objections") or shaped.get("commitments") or shaped.get("interest") else None,
            history_complete=True,
            screening_outcome=memo.get("screening_outcome"),
        )
        if touch is None:
            continue
        groups.setdefault(touch.contact_id or touch.memo_id, []).append(touch)
    signals = []
    for touches in groups.values():
        contact_signals = signals_for_contact(
            touches,
            now=now,
            day_end=day_end,
            callback_after_days=callback_after_days if lead_tiers_enabled else None,
        )
        if lead_tiers_enabled and contact_signals:
            last = max(touches, key=lambda t: t.at)
            heat = heat_score({
                "interest": last.interest,
                "pain_confirmed": pain_by_memo.get(last.memo_id, False),
                "objection_open": bool(last.objections),
                "days_silent": (now - last.at).days,
            })
            contact_signals = [replace(s, payload={**s.payload, "heat": heat}) for s in contact_signals]
        signals.extend(contact_signals)
    return signals


def never_contacted_signals(
    assigned_items: list[dict],
    *,
    connection_id: str,
    touched_contact_ids: set[str],
    coverage: str,
) -> list[Signal]:
    """T5 (D never_contacted): an assigned contact (hoy/assigned.py) never called and with
    no memo of its own. Never with a partial read - a contact CRM paging has not reached
    yet is not "never contacted", it is "not seen yet"."""
    if coverage != "complete":
        return []
    out: list[Signal] = []
    for item in assigned_items:
        contact_id = str(item.get("contact_id") or "")
        if not contact_id or contact_id in touched_contact_ids:
            continue
        if item.get("contacted"):
            continue
        out.append(never_contacted_signal(contact_id=contact_id, connection_id=connection_id, deal_id=item.get("deal_id")))
    return out


def exclude_handoff_contacts(signals: list[Signal], handoff_contact_ids: set[str]) -> list[Signal]:
    """T5 (D6/T3): a contact under an active SDR->AE handoff leaves the SDR's Hoy."""
    if not handoff_contact_ids:
        return signals
    return [signal for signal in signals if signal.contact_id not in handoff_contact_ids]


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


def retracted_objection_ids(existing: list[dict], *, memo_ids: set[str], fresh_keys: set[str]) -> list[str]:
    """A pending objection whose memo was re-read and no longer yields it (C04 found none, or it was resolved)."""
    return [
        str(row["id"])
        for row in existing
        if row.get("type") == "objection_open"
        and row.get("status") == "pending"
        and str(row.get("memo_id") or "") in memo_ids
        and str(row.get("dedupe_key") or "") not in fresh_keys
    ]


def read_hoy_memos(supabase, *, company_id: str, user_id: str) -> list[dict]:
    """The rep's newest memos: the only window Hoy materializes signals from."""
    stored = (
        supabase.table("memos")
        .select(
            "id,hubspot_contact_id,hubspot_deal_id,extraction,capture_started_at,created_at,"
            "company_id,user_id,playbook_version_id,screening_outcome"
        )
        .eq("user_id", user_id)
        .or_(f"company_id.eq.{company_id},company_id.is.null")
        .order("created_at", desc=True)
        .limit(HOY_MEMO_LIMIT)
        .execute()
    )
    return list(stored.data or [])


def refresh_hoy_signals(
    supabase,
    *,
    company_id: str,
    user_id: str,
    now: datetime,
    tz_name: str,
    lead_tiers_enabled: bool = False,
    callback_after_days: int = DEFAULT_CALLBACK_AFTER_DAYS,
) -> int:
    try:
        memos = read_hoy_memos(supabase, company_id=company_id, user_id=user_id)
        existing = (
            supabase.table("action_signals")
            .select("id,dedupe_key,type,status,memo_id")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        return 0
    signals = fresh_signals(
        memos,
        now=now,
        day_end=day_end(now, tz_name),
        lead_tiers_enabled=lead_tiers_enabled,
        callback_after_days=callback_after_days,
    )
    known = {str(row.get("dedupe_key") or "") for row in (existing.data or [])}
    retracted = retracted_objection_ids(
        list(existing.data or []),
        memo_ids={str(memo.get("id") or "") for memo in memos},
        fresh_keys={signal.dedupe_key for signal in signals},
    )
    if retracted:
        try:
            supabase.table("action_signals").update({"status": "resolved"}).in_("id", retracted).execute()
        except Exception:
            pass
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
