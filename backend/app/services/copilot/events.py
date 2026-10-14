"""A small log of what live help did, to review a call afterwards from facts (migration 078).

One row per turn check where the prospect finished a thought, and one per card. The prospect's words are cut to
300 characters and the rolling transcript is not stored. Rows older than RETENTION_DAYS are deleted (at most once
an hour). Everything here runs after the response is sent and never raises: live help is never slowed or broken by
its own log, and until the table exists it does nothing (a failed write pauses logging for ten minutes).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

TABLE = "live_assist_events"
RETENTION_DAYS = 90
TEXT_MAX = 300
PAUSE_AFTER_FAILURE_S = 600.0
PURGE_EVERY_S = 3600.0
PROMPT_VERSION = "copilot_suggest_v4"

_paused_until = 0.0
_last_purge = 0.0
# Until then rows go without the client's timing: its column (migration 080) was not there.
_no_client_until = 0.0
# The words last logged per rep: the same words are not logged twice (a check can repeat on the same turn).
_last_turn: dict[str, str] = {}


def _clip(value: Any, limit: int = TEXT_MAX) -> Optional[str]:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _build() -> Optional[str]:
    return (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:8] or None


# What the client may send about its own timing, and nothing else is stored.
TIMING_PATHS = {"pause", "settled", "timeout", "backstop"}
TIMING_NUMBERS = ("quiet_ms", "words_age_ms", "tail_ms", "wait_ms")
TIMING_BOOLS = ("deferred", "final")
TIMING_LIMIT_MS = 3_600_000


def clean_timing(timing: Any) -> Optional[dict]:
    """The client's timing stamps, kept only if they are the known keys with sane values."""
    if not isinstance(timing, dict):
        return None
    out: dict[str, Any] = {}
    if timing.get("path") in TIMING_PATHS:
        out["path"] = timing["path"]
    for key in TIMING_NUMBERS:
        value = timing.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) <= TIMING_LIMIT_MS:
            out[key] = int(round(value))
    for key in TIMING_BOOLS:
        if isinstance(timing.get(key), bool):
            out[key] = timing[key]
    return out or None


def turn_row(
    *, user_id: str, company_id: Optional[str], sales_motion_key: Optional[str], latest_turn: str,
    reading: dict, check_ms: int, timing: Any = None,
) -> Optional[dict]:
    """The row for a turn check; None when it should not be logged (the prospect is still talking, or the same
    words were logged already)."""
    if reading.get("finished") is False:
        return None
    text = _clip(latest_turn) or ""
    if _last_turn.get(user_id) == text:
        return None
    if len(_last_turn) > 2000:
        _last_turn.clear()
    _last_turn[user_id] = text
    return {
        "kind": "turn", "user_id": user_id, "company_id": company_id,
        "sales_motion_key": sales_motion_key or None, "latest_turn": text or None,
        "finished": reading.get("finished"), "objection": reading.get("objection"),
        "entry_id": reading.get("entry_id"), "check_ms": check_ms, "client": clean_timing(timing),
        "prompt_version": PROMPT_VERSION, "build": _build(),
    }


def suggest_row(
    *, user_id: str, company_id: Optional[str], sales_motion_key: Optional[str], call_mode: str, latest_turn: str,
    objection_type: Optional[str], entry_id: Optional[str], capture_id: Optional[str],
    result: Optional[dict], restarted: bool, error: Optional[str], playbook_version_id: Optional[str],
) -> dict:
    """The row for a card: what it was asked, which approved answer it followed, who wrote it and the line."""
    suggestion = (result or {}).get("suggestion") or {}
    return {
        "kind": "suggest", "user_id": user_id, "company_id": company_id,
        "sales_motion_key": sales_motion_key or None, "call_mode": call_mode,
        "latest_turn": _clip(latest_turn), "objection_type": objection_type, "entry_id": entry_id,
        "is_objection": suggestion.get("is_objection"), "source_id": suggestion.get("source_id"),
        "say_this": _clip(suggestion.get("say_this")), "provider": (result or {}).get("model"),
        "latency_ms": (result or {}).get("latency_ms"), "restarted": restarted or None,
        "error": _clip(error, 200), "playbook_version_id": playbook_version_id,
        "capture_id": _clip(capture_id, 128), "prompt_version": PROMPT_VERSION, "build": _build(),
    }


def record(supabase: Any, row: Optional[dict]) -> None:
    """Writes one row. Blocking (it runs as a background task, off the request). Never raises."""
    global _paused_until, _last_purge, _no_client_until
    if row is None or not settings.COPILOT_LOG_EVENTS:
        return
    now = time.monotonic()
    if now < _paused_until:
        return
    payload = {k: v for k, v in row.items() if v is not None}
    if now < _no_client_until:
        payload.pop("client", None)
    try:
        supabase.table(TABLE).insert(payload).execute()
    except Exception as exc:
        if "client" in payload:
            # Most likely migration 080 is not applied yet: keep the row without the client's timing.
            try:
                supabase.table(TABLE).insert({k: v for k, v in payload.items() if k != "client"}).execute()
                _no_client_until = now + PAUSE_AFTER_FAILURE_S
                logger.warning("live help event log: no client timing column (is migration 080 applied?): %s", str(exc)[:160])
                return
            except Exception:
                pass
        _paused_until = now + PAUSE_AFTER_FAILURE_S
        logger.warning("live help event log unavailable (is migration 078 applied?): %s", str(exc)[:160])
        return
    if now - _last_purge >= PURGE_EVERY_S:
        _last_purge = now
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
            supabase.table(TABLE).delete().lt("created_at", cutoff).execute()
        except Exception:
            logger.warning("live help event log purge failed", exc_info=True)
