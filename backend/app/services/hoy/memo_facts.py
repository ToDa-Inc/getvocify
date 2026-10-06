"""Facts Vocify captured on calls, keyed by CRM contact, for the priority list."""

from __future__ import annotations

from datetime import datetime

from app.services.hoy.priority import _as_dt

_IN_CHUNK = 200


def _pain(extraction: dict) -> bool:
    intelligence = extraction.get("intelligence") or {}
    return intelligence.get("pain_confirmed") is True or extraction.get("pain_confirmed") is True


def _meeting(extraction: dict) -> dict:
    return (extraction.get("intelligence") or {}).get("meeting") or {}


def memo_facts_by_contact(memos: list[dict], *, now: datetime) -> dict[str, dict]:
    """The newest memo decides. A meeting whose start has passed has happened and no longer blocks a follow-up."""
    ordered = sorted(memos, key=lambda row: _as_dt(row["created_at"]), reverse=True)
    facts: dict[str, dict] = {}
    for row in ordered:
        contact = str(row.get("hubspot_contact_id") or "")
        if not contact:
            continue
        extraction = row.get("extraction") or {}
        entry = facts.setdefault(contact, {"contacted": True})
        if "pain_confirmed" not in entry and _pain(extraction):
            entry.update(pain_confirmed=True, pain_at=row["created_at"], evidence_refs=[str(row["id"])])
        meeting = _meeting(extraction)
        if "meeting_seen" in entry or meeting.get("agreed") is None:
            continue
        entry["meeting_seen"] = True
        if meeting["agreed"] is not True:
            continue
        starts_at = _as_dt(meeting.get("starts_at")) if meeting.get("starts_at") else None
        if starts_at is None:
            entry["meeting_agreed"] = True
        elif starts_at > now:
            entry["scheduled_at"] = meeting["starts_at"]
    for entry in facts.values():
        entry.pop("meeting_seen", None)
    return facts


def apply_memo_facts(candidates: list[dict], facts: dict[str, dict]) -> list[dict]:
    if not facts:
        return candidates
    return [{**row, **facts.get(str(row.get("contact_id")), {})} for row in candidates]


def load_memo_facts(supabase, company_id: str, contact_ids: list[str], *, now: datetime) -> dict[str, dict]:
    ids = sorted({str(contact) for contact in contact_ids if contact})
    memos: list[dict] = []
    for start in range(0, len(ids), _IN_CHUNK):
        result = (
            supabase.table("memos")
            .select("id,created_at,extraction,hubspot_contact_id")
            .eq("company_id", company_id)
            .in_("hubspot_contact_id", ids[start:start + _IN_CHUNK])
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        )
        memos.extend(result.data or [])
    return memo_facts_by_contact(memos, now=now)
