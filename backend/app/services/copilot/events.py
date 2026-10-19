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
# The live call assistant's rows (migration 082) pause on their own: until it is applied their insert fails, and that
# must not silence the turn checks and cards.
_brain_paused_until = 0.0
BRAIN_KINDS = ("points", "progress", "recap")
# The "Qué decir" view's UI events (migration 086) pause on their own too.
_ui_paused_until = 0.0
UI_EVENTS = frozenset({
    "shown", "dismissed", "reopened", "rewrite", "ask_step", "tick", "untick", "responder", "bubble",
    "open_recap", "open_steps", "open_brief", "marker_shown", "marker_seen",
})
UI_DETAIL_KEYS = 12
_last_purge = float("-inf")  # never purged yet (monotonic time may be small right after a boot)
# Until then rows go without the client's timing: its column (migration 080) was not there.
_no_client_until = 0.0
# The words and verdict last logged per rep: the same pair is not logged twice (a check can repeat on the same turn).
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
TIMING_NUMBERS = ("quiet_ms", "words_age_ms", "tail_ms", "wait_ms", "level_pct", "floor_pct")
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


SERVER_TIMING_CACHE = {"hit", "cold", "partial", "off"}


def clean_server_timing(timing: Any) -> Optional[dict]:
    """The server's own timing of a card, from the server: milliseconds before the model started, and where what the
    card reads came from (the `client` column holds both sides' timing)."""
    if not isinstance(timing, dict):
        return None
    out: dict[str, Any] = {}
    prep = timing.get("prep_ms")
    if isinstance(prep, (int, float)) and not isinstance(prep, bool) and 0 <= prep <= TIMING_LIMIT_MS:
        out["prep_ms"] = int(round(prep))
    if timing.get("cache") in SERVER_TIMING_CACHE:
        out["cache"] = timing["cache"]
    return out or None


def turn_row(
    *, user_id: str, company_id: Optional[str], sales_motion_key: Optional[str], latest_turn: str,
    reading: dict, check_ms: int, timing: Any = None, capture_id: Optional[str] = None,
) -> Optional[dict]:
    """The row for a turn check; None when the same words were already logged with the same verdict. A check that
    found the prospect still going is logged too: how often it happens, and on which words, is what shows whether
    a cut-off ending delays the card."""
    text = _clip(latest_turn) or ""
    seen = f"{text}|{reading.get('finished')}"
    if _last_turn.get(user_id) == seen:
        return None
    if len(_last_turn) > 2000:
        _last_turn.clear()
    _last_turn[user_id] = seen
    return {
        "kind": "turn", "user_id": user_id, "company_id": company_id,
        "sales_motion_key": sales_motion_key or None, "latest_turn": text or None,
        "finished": reading.get("finished"), "objection": reading.get("objection"),
        "entry_id": reading.get("entry_id"), "check_ms": check_ms, "client": clean_timing(timing),
        "capture_id": _clip(capture_id, 128), "prompt_version": PROMPT_VERSION, "build": _build(),
    }


def suggest_row(
    *, user_id: str, company_id: Optional[str], sales_motion_key: Optional[str], call_mode: str, latest_turn: str,
    objection_type: Optional[str], entry_id: Optional[str], capture_id: Optional[str],
    result: Optional[dict], restarted: bool, error: Optional[str], playbook_version_id: Optional[str],
    server_timing: Optional[dict] = None,
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
        "client": clean_server_timing(server_timing),
    }


UNANSWERED_MAX = 3
UNANSWERED_SAID_MAX = 120


def unanswered_points(points: Optional[list]) -> Optional[list[dict]]:
    """The new points of a reading that neither the playbook nor the company's knowledge could answer: the prospect's
    words (clipped, like every word of theirs that is logged) and, in a few words, what was missing. It is the list a
    company fills so that live help says true things more often. Updates are left out (the point was logged when it was
    new), and so is anything the brain did answer from a source."""
    out: list[dict] = []
    for point in points or []:
        if not isinstance(point, dict) or point.get("is_update") or point.get("answer") is not None:
            continue
        said = _clip(point.get("title"), UNANSWERED_SAID_MAX)
        if not said:
            continue
        out.append({
            "said": said, "missing": _clip(point.get("gap"), 80), "kind": point.get("kind"),
            "tag": point.get("tag_key") or None,
        })
        if len(out) >= UNANSWERED_MAX:
            break
    return [{k: v for k, v in item.items() if v is not None} for item in out] or None


def brain_row(
    *, kind: str, user_id: str, company_id: Optional[str], call_mode: str, sales_motion_key: Optional[str],
    call_id: Optional[str], latest_turn: str, result: Optional[dict], error: Optional[str], detail: dict,
) -> dict:
    """The row for one reading of the live call assistant: which producer, how long it took, who wrote it and what
    came out (counts and what the checks dropped; the points' words are in the call's own transcript)."""
    return {
        "kind": kind, "user_id": user_id, "company_id": company_id, "sales_motion_key": sales_motion_key or None,
        "call_mode": call_mode, "latest_turn": _clip(latest_turn), "provider": (result or {}).get("model"),
        "latency_ms": (result or {}).get("latency_ms"), "error": _clip(error, 200),
        "playbook_version_id": (result or {}).get("playbook_version_id"), "capture_id": _clip(call_id, 128),
        "prompt_version": detail.pop("prompt_version", None), "build": _build(), "detail": detail or None,
    }


def _ui_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if abs(value) <= 1e13 else None
    if isinstance(value, str):
        return _clip(value)
    return None


def ui_rows(
    *, user_id: str, company_id: Optional[str], call_id: str, call_mode: Optional[str], sales_motion_key: Optional[str], events: list[dict],
) -> list[dict]:
    """One row per UI event the island or the live view sent: kind 'ui', the event and its fields in `detail`. Unknown events
    are left out (one wrong event does not lose the batch); detail keeps only short scalar values (words clipped to 300)."""
    rows = []
    for event in events:
        name = event.get("kind")
        if name not in UI_EVENTS:
            continue
        detail: dict[str, Any] = {"event": name}
        for key in ("at", "point_id", "step_kind", "step_id"):
            if event.get(key) is not None:
                detail[key] = _ui_value(event[key])
        extra = event.get("detail") if isinstance(event.get("detail"), dict) else {}
        for key, value in list(extra.items())[:UI_DETAIL_KEYS]:
            if isinstance(key, str) and len(key) <= 40 and key not in detail and _ui_value(value) is not None:
                detail[key] = _ui_value(value)
        rows.append({
            "kind": "ui", "user_id": user_id, "company_id": company_id, "call_mode": call_mode,
            "sales_motion_key": sales_motion_key or None, "capture_id": _clip(call_id, 128), "build": _build(), "detail": detail,
        })
    return rows


def record_ui(supabase: Any, rows: list[dict]) -> None:
    """Writes a batch of UI events in one insert. Blocking (a background task). Never raises."""
    global _ui_paused_until
    if not rows or not settings.COPILOT_LOG_EVENTS:
        return
    now = time.monotonic()
    if now < _ui_paused_until:
        return
    try:
        supabase.table(TABLE).insert([{k: v for k, v in row.items() if v is not None} for row in rows]).execute()
    except Exception as exc:
        _ui_paused_until = now + PAUSE_AFTER_FAILURE_S
        logger.warning("live assist UI event log unavailable (is migration 086 applied?): %s", str(exc)[:160])


def record(supabase: Any, row: Optional[dict]) -> None:
    """Writes one row. Blocking (it runs as a background task, off the request). Never raises."""
    global _paused_until, _brain_paused_until, _last_purge, _no_client_until
    if row is None or not settings.COPILOT_LOG_EVENTS:
        return
    now = time.monotonic()
    if row.get("kind") in BRAIN_KINDS:
        if now < _brain_paused_until:
            return
        try:
            supabase.table(TABLE).insert({k: v for k, v in row.items() if v is not None}).execute()
        except Exception as exc:
            _brain_paused_until = now + PAUSE_AFTER_FAILURE_S
            logger.warning("live brain event log unavailable (is migration 082 applied?): %s", str(exc)[:160])
        return
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
