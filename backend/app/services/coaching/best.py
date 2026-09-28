"""T11/PLAYBOOK_TAB_ENABLED: the week's best interactions per flow, for the Playbook tab.

Every company member sees the top 3 per flow (author name, score, highlight quotes).
Opening the memo stays governed by the existing memo visibility rules; this module only
ranks and formats, it never decides who can open a memo."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.coaching.briefs import build_highlights
from app.services.playbooks.motion import flow_for_motion

FLAG = "PLAYBOOK_TAB_ENABLED"
_FLOWS = ("sdr", "ae")


def _parse_instant(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        dt = datetime.fromisoformat(text)
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def best_by_flow(
    rows: list[dict],
    *,
    start: datetime,
    end: datetime,
    limit: int = 3,
) -> dict[str, list[dict]]:
    """Rank scored interactions into the top `limit` per flow, best score first, ties
    broken by the most recent. A row without a `sales_motion_key` that maps to a known
    flow, without a date in [start, end), or without a numeric score does not count."""
    candidates: dict[str, list[tuple[float, datetime, dict]]] = {flow: [] for flow in _FLOWS}
    for row in rows:
        flow = flow_for_motion(row.get("sales_motion_key"))
        if flow not in candidates:
            continue
        instant = _parse_instant(row.get("observed_at"))
        if instant is None or instant < start or instant >= end:
            continue
        value = row.get("value")
        if not isinstance(value, (int, float)):
            continue
        memo_id = str(row.get("memo_id") or "").strip()
        if not memo_id:
            continue
        item = {
            "memo_id": memo_id,
            "user_id": str(row.get("user_id") or ""),
            "author": str(row.get("author") or ""),
            "date": instant.isoformat().replace("+00:00", "Z"),
            "value": value,
            "highlights": build_highlights(row.get("evidence") or []),
        }
        candidates[flow].append((float(value), instant, item))
    result: dict[str, list[dict]] = {}
    for flow, items in candidates.items():
        items.sort(key=lambda entry: (-entry[0], -entry[1].timestamp()))
        result[flow] = [item for _, _, item in items[:limit]]
    return result
