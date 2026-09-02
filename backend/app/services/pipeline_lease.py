"""Single-flight lease so one memo never runs two extracts at once.

In-process lock stops the same-event burst (recovery + confirm + start_extraction).
A best-effort row update covers restarts. Missing columns degrade to in-process only.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

LEASE_SECONDS = 600

_guard = threading.Lock()
_LIVE: dict[str, tuple[str, float]] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lease_expired(started_monotonic: float, *, now: Optional[float] = None) -> bool:
    return ((now if now is not None else time.monotonic()) - started_monotonic) >= LEASE_SECONDS


def _db_cutoff_iso() -> str:
    return (_utc_now() - timedelta(seconds=LEASE_SECONDS)).isoformat()


def _row_has_run_id(result: Any, run_id: str) -> bool:
    rows = getattr(result, "data", None)
    if not isinstance(rows, list):
        return False
    return any(isinstance(row, dict) and row.get("pipeline_run_id") == run_id for row in rows)


def _db_row_has_run_id(supabase: Any, memo_id: str, run_id: str) -> bool:
    """PostgREST re-applies the PATCH filter to RETURNING.

    After a successful lease write, pipeline_run_id is no longer null and
    started_at is no longer older than the cutoff, so data=[] even though
    we own the row. Confirm by primary key.
    """
    try:
        row = (
            supabase.table("memos")
            .select("pipeline_run_id")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return False
    rows = getattr(row, "data", None) or []
    if not rows or not isinstance(rows[0], dict):
        return False
    return rows[0].get("pipeline_run_id") == run_id


def acquire_pipeline_run(
    supabase: Any,
    memo_id: str,
    trigger: str,
) -> Optional[str]:
    """Return a new run_id, or None if another run already holds the memo."""
    mid = str(memo_id or "").strip()
    if not mid:
        return None
    run_id = str(uuid.uuid4())
    now_m = time.monotonic()
    with _guard:
        held = _LIVE.get(mid)
        if held and not lease_expired(held[1], now=now_m):
            return None
        _LIVE[mid] = (run_id, now_m)

    started = _utc_now().isoformat()
    if supabase is not None:
        try:
            q = (
                supabase.table("memos")
                .update(
                    {
                        "pipeline_run_id": run_id,
                        "pipeline_run_started_at": started,
                    }
                )
                .eq("id", mid)
            )
            or_filter = f"pipeline_run_id.is.null,pipeline_run_started_at.lt.{_db_cutoff_iso()}"
            if hasattr(q, "or_"):
                q = q.or_(or_filter)
            result = q.execute()
            if not _row_has_run_id(result, run_id) and not _db_row_has_run_id(
                supabase, mid, run_id
            ):
                with _guard:
                    current = _LIVE.get(mid)
                    if current and current[0] == run_id:
                        _LIVE.pop(mid, None)
                return None
        except Exception as e:
            logger.info("Pipeline lease DB update skipped (%s): %s", trigger, e)
    return run_id


def release_pipeline_run(
    supabase: Any,
    memo_id: str,
    run_id: Optional[str],
) -> None:
    mid = str(memo_id or "").strip()
    if not mid or not run_id:
        return
    with _guard:
        current = _LIVE.get(mid)
        if current and current[0] == run_id:
            _LIVE.pop(mid, None)
    if supabase is None:
        return
    try:
        q = (
            supabase.table("memos")
            .update({"pipeline_run_id": None, "pipeline_run_started_at": None})
            .eq("id", mid)
        )
        if hasattr(q, "eq"):
            q = q.eq("pipeline_run_id", run_id)
        q.execute()
    except Exception as e:
        logger.info("Pipeline lease DB release skipped: %s", e)


_OPTIONAL_MEMO_COLS = frozenset({
    "transcript_raw",
    "transcript_stt_meta",
    "pipeline_run_id",
    "pipeline_run_started_at",
})


def update_memo_row(supabase: Any, memo_id: str, payload: dict[str, Any]) -> None:
    """Write memo fields; retry without Phase-0 columns if the migration is not applied."""
    try:
        supabase.table("memos").update(payload).eq("id", memo_id).execute()
        return
    except Exception as e:
        stripped = {k: v for k, v in payload.items() if k not in _OPTIONAL_MEMO_COLS}
        if stripped == payload:
            raise
        logger.info("Memo update retried without pipeline columns: %s", e)
        supabase.table("memos").update(stripped).eq("id", memo_id).execute()


def reap_expired_leases() -> int:
    """Drop in-process leases past LEASE_SECONDS. DB expiry is checked on acquire."""
    now_m = time.monotonic()
    with _guard:
        expired = [mid for mid, (_, started) in list(_LIVE.items()) if lease_expired(started, now=now_m)]
        for mid in expired:
            _LIVE.pop(mid, None)
    return len(expired)


def reset_pipeline_leases() -> None:
    """Test helper."""
    with _guard:
        _LIVE.clear()


def run_record(
    run_id: str,
    trigger: str,
    started_at: str,
    started_perf: float,
    outcome: str = "ok",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "trigger": trigger,
        "started_at": started_at,
        "ended_at": _utc_now().isoformat(),
        "wall_ms": max(0, int(round((time.perf_counter() - started_perf) * 1000))),
        "outcome": outcome,
    }
