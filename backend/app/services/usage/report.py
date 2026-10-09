"""Read side of the cost columns on memos (staff only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

_PAGE = 1000
_COLS = "id,user_id,created_at,source_type,cost_usd,cost_breakdown"


def memo_cost_report(supabase: Any, memo_id: str) -> Optional[dict]:
    rows = supabase.table("memos").select(_COLS).eq("id", memo_id).limit(1).execute().data
    if not rows:
        return None
    memo = rows[0]
    breakdown = memo.get("cost_breakdown") or {}
    return {
        "memo_id": memo["id"],
        "total_cost_usd": float(memo.get("cost_usd") or 0),
        "unpriced_events": sum(int(step.get("unpriced") or 0) for step in breakdown.values()),
        "by_purpose": breakdown,
    }


def period_summary(supabase: Any, days: int) -> dict:
    """Totals per step across every memo created in the last `days` days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    memos = 0
    total = 0.0
    by_purpose: dict[str, dict[str, float]] = {}
    start = 0
    while True:
        page = (
            supabase.table("memos")
            .select(_COLS)
            .gte("created_at", since)
            .gt("cost_usd", 0)
            .order("created_at")
            .range(start, start + _PAGE - 1)
            .execute()
            .data
        ) or []
        for memo in page:
            memos += 1
            total += float(memo.get("cost_usd") or 0)
            for purpose, step in (memo.get("cost_breakdown") or {}).items():
                agg = by_purpose.setdefault(purpose, {"usd": 0.0, "events": 0, "unpriced": 0, "audio_seconds": 0.0})
                for field in agg:
                    agg[field] += float(step.get(field) or 0)
        if len(page) < _PAGE:
            break
        start += _PAGE
    return {
        "days": days,
        "memos_with_cost": memos,
        "total_cost_usd": round(total, 6),
        "avg_cost_per_memo_usd": round(total / memos, 6) if memos else 0.0,
        "by_purpose": {k: {f: round(v, 6) for f, v in agg.items()} for k, agg in by_purpose.items()},
    }
