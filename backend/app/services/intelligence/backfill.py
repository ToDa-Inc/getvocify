"""Analyse past conversations. Only what is missing or was read by an older prompt.

New conversations are analysed when they are extracted (INTELLIGENCE_EXTRACT_ENABLED). This is the
other half: an owner or admin asks for the history to be read, and Ask stops saying "3 of 14".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.intelligence.extract import ensure_intelligence, is_current

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 300
DEFAULT_CONCURRENCY = 3
_USABLE = ("pending_review", "approved")
_COLUMNS = "id,user_id,company_id,status,transcript,extraction,capture_started_at,created_at"

# One run per company per process. A second instance may also run; ensure_intelligence is
# idempotent per revision, so the cost is a repeated model call, never a wrong result.
_RUNS: dict[str, dict] = {}
_TASKS: set[asyncio.Task] = set()


def _readable(company_id: str, member_ids: list[str], supabase: Any) -> list[dict]:
    rows = (
        supabase.table("memos")
        .select(_COLUMNS)
        .in_("user_id", member_ids)
        .or_(f"company_id.eq.{company_id},company_id.is.null")
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
        .data
        or []
    )
    return [m for m in rows if m.get("status") in _USABLE and str(m.get("transcript") or "").strip()]


def coverage(supabase: Any, company_id: str, member_ids: list[str]) -> dict:
    memos = _readable(company_id, member_ids, supabase) if member_ids else []
    analysed = sum(1 for m in memos if is_current(m))
    return {"total": len(memos), "analysed": analysed, "pending": len(memos) - analysed}


async def run_backfill(
    supabase: Any,
    company_id: str,
    member_ids: list[str],
    *,
    limit: int = DEFAULT_LIMIT,
    concurrency: int = DEFAULT_CONCURRENCY,
    llm: Any = None,
    on_result: Optional[Any] = None,
) -> dict:
    pending = [m for m in _readable(company_id, member_ids, supabase) if not is_current(m)]
    pending.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
    batch = pending[:limit]
    gate = asyncio.Semaphore(max(1, concurrency))
    tally = {"analysed": 0, "failed": 0, "skipped": 0}

    async def one(memo: dict) -> None:
        async with gate:
            try:
                outcome = await ensure_intelligence(supabase, str(memo["id"]), llm=llm)
                key = "analysed" if outcome.get("status") == "stored" else "skipped"
            except Exception:
                logger.exception("intelligence backfill failed", extra={"memo_id": str(memo.get("id"))})
                key = "failed"
            tally[key] += 1
            if on_result:
                on_result(dict(tally))

    await asyncio.gather(*(one(m) for m in batch))
    return {**tally, "remaining": len(pending) - len(batch)}


def progress(company_id: str) -> dict:
    """The running job's tally. Keys are prefixed so they never collide with `coverage`."""
    run = _RUNS.get(company_id)
    if not run:
        return {"running": False}
    done = run["analysed"] + run["failed"] + run["skipped"]
    return {
        "running": run["running"],
        "run_analysed": run["analysed"],
        "run_failed": run["failed"],
        "run_skipped": run["skipped"],
        "run_done": done,
        "queued": run["queued"],
        "started_at": run["started_at"],
    }


def start_backfill(
    supabase: Any, company_id: str, member_ids: list[str], *, limit: int = DEFAULT_LIMIT, llm: Any = None
) -> dict:
    """Start in the background. Returns at once; poll `progress`."""
    if _RUNS.get(company_id, {}).get("running"):
        return {"started": False, "reason": "already_running", **progress(company_id)}
    pending = coverage(supabase, company_id, member_ids)["pending"]
    if not pending:
        return {"started": False, "reason": "nothing_pending", "pending": 0}
    run = {"running": True, "analysed": 0, "failed": 0, "skipped": 0, "queued": min(pending, limit), "started_at": datetime.now(timezone.utc).isoformat()}
    _RUNS[company_id] = run

    def note(tally: dict) -> None:
        run.update(tally)

    async def job() -> None:
        try:
            await run_backfill(supabase, company_id, member_ids, limit=limit, llm=llm, on_result=note)
        finally:
            run["running"] = False

    task = asyncio.get_running_loop().create_task(job())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return {"started": True, "pending": pending, "queued": run["queued"]}
