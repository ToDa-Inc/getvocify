"""When to highlight a brief. Processing stays immediate. A ready brief is not cleared."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_MODES = {"immediate", "deferred", "end_of_day"}


def normalize_preference(raw: dict) -> dict:
    mode = raw.get("highlight_mode") or "immediate"
    if mode not in _MODES:
        raise ValueError(f"modo de destaque desconocido: {mode}")
    timezone = raw.get("timezone") or "Europe/Madrid"
    if mode == "deferred":
        delay = 30 if raw.get("delay_minutes") is None else int(raw["delay_minutes"])
        if delay <= 0:
            raise ValueError("delay_minutes debe ser positivo")
        return {"highlight_mode": mode, "delay_minutes": delay, "end_of_day": None, "timezone": timezone}
    if mode == "end_of_day":
        end = raw.get("end_of_day") or "18:00"
        return {"highlight_mode": mode, "delay_minutes": None, "end_of_day": end, "timezone": timezone}
    return {"highlight_mode": "immediate", "delay_minutes": None, "end_of_day": None, "timezone": timezone}


def apply_preference(brief: dict, preference: dict) -> dict:
    """Change when it is highlighted. Do not send it back to pending or drop it."""
    return {**brief, "highlight": normalize_preference(preference)}


def highlight_at(ready_at: datetime, preference: dict) -> datetime:
    preference = normalize_preference(preference)
    if ready_at.tzinfo is None:
        ready_at = ready_at.replace(tzinfo=ZoneInfo("UTC"))
    if preference["highlight_mode"] == "immediate":
        return ready_at
    if preference["highlight_mode"] == "deferred":
        return ready_at + timedelta(minutes=preference["delay_minutes"])
    hour, minute = (int(part) for part in preference["end_of_day"].split(":"))
    local = ready_at.astimezone(ZoneInfo(preference["timezone"]))
    same_day = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local <= same_day:
        return same_day
    return same_day + timedelta(days=1)


def enqueue_brief(jobs: list[dict], *, memo_id: str, input_revision: str) -> list[dict]:
    key = (memo_id, input_revision, "brief")
    if any(job.get("key") == key for job in jobs):
        return jobs
    return [*jobs, {"key": key, "status": "pending", "available_at": "now"}]


def publish_if_newer(stored: dict | None, incoming: dict) -> dict | None:
    if stored and stored["revision_seq"] >= incoming["revision_seq"]:
        return None
    return incoming


def publish_brief_statement(*, memo_id: str, input_revision: str, revision_seq: int, status: str, body: dict) -> str:
    payload = json.dumps(body, ensure_ascii=False).replace("'", "''")
    return (
        "INSERT INTO post_interaction_briefs (memo_id, input_revision, revision_seq, status, body) "
        f"VALUES ('{memo_id}', '{input_revision}', {int(revision_seq)}, '{status}', '{payload}'::jsonb) "
        "ON CONFLICT (memo_id, input_revision) DO UPDATE SET "
        "status = EXCLUDED.status, body = EXCLUDED.body, revision_seq = EXCLUDED.revision_seq "
        "WHERE post_interaction_briefs.revision_seq < EXCLUDED.revision_seq;"
    )
