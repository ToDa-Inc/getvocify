"""Read side of the cost ledger: per-memo breakdown and period summaries (staff only)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

_PAGE = 1000


def total_cost(rows: Iterable[dict]) -> float:
    return round(sum(float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None), 6)


def summarize(events: list[dict], key: str) -> list[dict]:
    """Group by `key` (purpose, model, provider, user_id, kind). Unpriced events are counted, not priced."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        groups[str(e.get(key) or "unknown")].append(e)
    out = [
        {
            key: name,
            "events": len(rows),
            "cost_usd": total_cost(rows),
            "unpriced_events": sum(1 for r in rows if r.get("cost_usd") is None),
            "audio_seconds": round(sum(float(r.get("audio_seconds") or 0) for r in rows), 2),
            "prompt_tokens": sum(int(r.get("prompt_tokens") or 0) for r in rows),
            "completion_tokens": sum(int(r.get("completion_tokens") or 0) for r in rows),
        }
        for name, rows in groups.items()
    ]
    return sorted(out, key=lambda g: g["cost_usd"], reverse=True)


def memo_events(supabase: Any, memo_id: str) -> Optional[list[dict]]:
    """Events tied to the memo directly or through its desktop capture. None if the memo is unknown."""
    memo = supabase.table("memos").select("id,client_capture_id").eq("id", memo_id).limit(1).execute().data
    if not memo:
        return None
    capture_id = memo[0].get("client_capture_id")
    cond = f"memo_id.eq.{memo_id}" + (f",capture_id.eq.{capture_id}" if capture_id else "")
    rows = supabase.table("usage_events").select("*").or_(cond).order("created_at").execute().data
    return rows or []


def memo_cost_report(supabase: Any, memo_id: str) -> Optional[dict]:
    events = memo_events(supabase, memo_id)
    if events is None:
        return None
    return {
        "memo_id": memo_id,
        "total_cost_usd": total_cost(events),
        "unpriced_events": sum(1 for e in events if e.get("cost_usd") is None),
        "by_kind": summarize(events, "kind"),
        "by_purpose": summarize(events, "purpose"),
        "events": events,
    }


def period_events(supabase: Any, days: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            supabase.table("usage_events")
            .select("kind,provider,model,purpose,user_id,prompt_tokens,completion_tokens,audio_seconds,cost_usd")
            .gte("created_at", since)
            .order("created_at")
            .range(start, start + _PAGE - 1)
            .execute()
            .data
        ) or []
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        start += _PAGE
