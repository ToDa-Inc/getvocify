"""Suggested questions, chosen from what the account holds. An empty account gets none."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

MAX_SUGGESTIONS = 4
_USABLE = frozenset({"pending_review", "approved"})


def _recent_memos(supabase: Any, company_id: str, member_ids: list[str], days: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("memos")
        .select("id,user_id,status,extraction,created_at")
        .in_("user_id", member_ids)
        .or_(f"company_id.eq.{company_id},company_id.is.null")
        .gte("created_at", since)
        .limit(300)
        .execute()
        .data
        or []
    )
    return [m for m in rows if m.get("status") in _USABLE and isinstance(m.get("extraction"), dict)]


def _has_analysed_objection(memos: list[dict]) -> bool:
    for memo in memos:
        block = memo["extraction"].get("intelligence")
        if isinstance(block, dict) and any(isinstance(o, dict) for o in block.get("objections") or []):
            return True
    return False


def _published_playbook(supabase: Any, company_id: str) -> dict:
    """What the playbook that applies to calls holds: {"entries": bool, "steps": bool}."""
    from app.services.playbooks.live import live_snapshots

    live = live_snapshots(supabase, company_id)
    return {"entries": any(v["entries"] for v in live), "steps": any(v["steps"] for v in live)}


def compute(supabase: Any, *, company_id: str, user_id: str, role: str, member_ids: list[str], has_crm: bool) -> list[str]:
    team = role in ("owner", "admin")
    memos = _recent_memos(supabase, company_id, member_ids, 60) if member_ids else []
    last_30 = [m for m in memos if str(m.get("created_at") or "") >= (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()]
    playbook = _published_playbook(supabase, company_id)
    out: list[str] = []
    if memos:
        out.append("next_actions")
    if memos and playbook["steps"]:
        out.append("team_health" if team else "my_coaching")
    if _has_analysed_objection(last_30):
        out.append("objections")
    if has_crm:
        out += ["connection_rate", "lost_reasons"]
    if playbook["entries"] and not team:
        out.append("playbook")
    return out[:MAX_SUGGESTIONS]
