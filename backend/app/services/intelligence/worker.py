"""Queue intelligence work after extraction, and recover a job that was never enqueued."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.services.intelligence.revisions import input_revision

logger = logging.getLogger(__name__)

REGISTERED_KINDS = frozenset({"intelligence"})
_worker_task: Optional[asyncio.Task] = None
_worker_stop = asyncio.Event()
_worker_tick = None


def set_worker_tick(tick) -> None:
    """One pass of the loop. Production and tests install claim/publish here."""
    global _worker_tick
    _worker_tick = tick


def revision_for_memo(memo: dict) -> str:
    extraction = memo.get("extraction") or {}
    if hasattr(extraction, "model_dump"):
        extraction = extraction.model_dump()
    return input_revision(
        schema="c04.v1",
        extraction_revision=json.dumps(extraction, sort_keys=True, default=str, ensure_ascii=False),
        notes_revision=memo.get("notes_revision"),
        identity=f"{memo.get('company_id') or ''}:{memo.get('user_id') or ''}",
        playbook_version_id=memo.get("playbook_version_id"),
    )


def enqueue_plan(memo: dict, existing: list[dict]) -> Optional[dict]:
    """One pending job for the current revision. Unknown kinds are not queued."""
    if not memo.get("extraction"):
        return None
    kind = "intelligence"
    if kind not in REGISTERED_KINDS:
        return None
    memo_id = str(memo["id"])
    revision = revision_for_memo(memo)
    same = [
        job for job in existing
        if str(job.get("memo_id")) == memo_id and job.get("kind") == kind
    ]
    if any(job.get("input_revision") == revision for job in same):
        return None
    seq = max((int(job.get("revision_seq") or 0) for job in same), default=0) + 1
    return {
        "memo_id": memo_id,
        "company_id": memo.get("company_id"),
        "kind": kind,
        "input_revision": revision,
        "revision_seq": seq,
        "status": "pending",
    }


def sweep_missing(memos: list[dict], jobs: list[dict]) -> list[dict]:
    """Create each missing job once. A second pass over the same rows adds nothing."""
    found: list[dict] = []
    current = list(jobs)
    for memo in memos:
        row = enqueue_plan(memo, current)
        if row:
            found.append(row)
            current.append(row)
    return found


def record_enqueue(supabase: Any, memo: dict) -> Optional[dict]:
    """Insert the job if it is missing. Never raises into the extraction path."""
    try:
        memo_id = str(memo["id"])
        result = (
            supabase.table("memo_jobs")
            .select("memo_id,kind,input_revision,revision_seq")
            .eq("memo_id", memo_id)
            .eq("kind", "intelligence")
            .execute()
        )
        existing = list(getattr(result, "data", None) or [])
        row = enqueue_plan(memo, existing)
        if not row:
            return None
        supabase.table("memo_jobs").insert(row).execute()
        logger.info(
            "intelligence job enqueued",
            extra={"kind": row["kind"], "input_revision": row["input_revision"], "memo_id": memo_id},
        )
        return row
    except Exception:
        logger.exception(
            "intelligence enqueue failed",
            extra={"kind": "intelligence", "memo_id": str(memo.get("id"))},
        )
        return None


async def _worker_loop() -> None:
    while not _worker_stop.is_set():
        tick = _worker_tick
        if tick is not None:
            try:
                outcome = tick()
                if asyncio.iscoroutine(outcome):
                    await outcome
            except Exception:
                logger.exception("intelligence tick failed")
        try:
            await asyncio.wait_for(_worker_stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            continue


def start_worker() -> bool:
    """Start one loop. A second call while it is running does nothing."""
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return False
    _worker_stop.clear()
    _worker_task = asyncio.get_running_loop().create_task(_worker_loop())
    return True


async def stop_worker() -> None:
    global _worker_task
    _worker_stop.set()
    task = _worker_task
    _worker_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
