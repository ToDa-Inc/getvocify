"""When to highlight a brief. Processing stays immediate. A ready brief is not cleared."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_MODES = {"immediate", "deferred", "end_of_day"}
_STORE: dict[str, dict] = {}
_supabase: Any | None = None
logger = logging.getLogger(__name__)


def set_supabase(client: Any | None) -> None:
    global _supabase
    _supabase = client


def default_preference() -> dict:
    return normalize_preference({})


def _read_from_memory(user_id: str) -> dict:
    raw = _STORE.get(user_id)
    if raw is None:
        return default_preference()
    return normalize_preference(raw)


def read_preference(user_id: str) -> dict:
    if _supabase is not None:
        try:
            response = (
                _supabase.table("brief_preferences")
                .select("highlight_mode,delay_minutes,end_of_day,timezone")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            if rows:
                return normalize_preference(_row_to_raw(rows[0]))
        except Exception:
            logger.exception("brief_preferences read failed for user %s", user_id)
            return _read_from_memory(user_id)
        return default_preference()
    return _read_from_memory(user_id)


def write_preference(user_id: str, raw: dict) -> dict:
    normalized = normalize_preference(raw)
    _STORE[user_id] = normalized
    if _supabase is not None:
        payload = {
            "user_id": user_id,
            "highlight_mode": normalized["highlight_mode"],
            "delay_minutes": normalized["delay_minutes"],
            "end_of_day": normalized["end_of_day"],
            "timezone": normalized["timezone"],
        }
        _supabase.table("brief_preferences").upsert(payload, on_conflict="user_id").execute()
    return normalized


def _row_to_raw(row: dict) -> dict:
    end_of_day = row.get("end_of_day")
    if end_of_day is not None:
        text = str(end_of_day)
        parts = text.split(":")
        if len(parts) >= 2:
            end_of_day = f"{parts[0]}:{parts[1]}"
    return {
        "highlight_mode": row.get("highlight_mode"),
        "delay_minutes": row.get("delay_minutes"),
        "end_of_day": end_of_day,
        "timezone": row.get("timezone"),
    }


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
