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


def run_claimed(claim, load_memo, publish, classify, sources_for, store=None) -> Optional[dict]:
    """Claim, then publish only when the memo is loaded. An empty claim does not classify."""
    claimed = claim()
    if not claimed:
        return None
    memo = load_memo(claimed["memo_id"])
    if not memo:
        return {"outcome": "missing_memo", "published": False}
    from app.services.intelligence.interpret import interpret_memo

    intelligence, created = interpret_memo(memo, classify, sources_for(memo))
    dumped = intelligence.model_dump()
    if store is not None:
        store(memo, dumped)
    outcome = publish(claimed["job_id"], claimed["run_id"], dumped)
    return {
        "created": created,
        "outcome": outcome,
        "published": True,
        "input_revision": intelligence.input_revision,
    }


async def run_claimed_awaiting(claim, load_memo, publish, classify, sources_for, store=None) -> Optional[dict]:
    """Same as run_claimed, after awaiting an async classifier."""
    claimed = claim()
    if not claimed:
        return None
    memo = load_memo(claimed["memo_id"])
    if not memo:
        return {"outcome": "missing_memo", "published": False}
    result = classify(memo)
    if asyncio.iscoroutine(result):
        result = await result
    from app.services.intelligence.interpret import interpret_memo

    intelligence, created = interpret_memo(memo, lambda _memo: result, sources_for(memo))
    dumped = intelligence.model_dump()
    if store is not None:
        store(memo, dumped)
    outcome = publish(claimed["job_id"], claimed["run_id"], dumped)
    return {
        "created": created,
        "outcome": outcome,
        "published": True,
        "input_revision": intelligence.input_revision,
    }


def database_bindings(supabase, sources_for=None):
    """claim_memo_job, the memo row, and publish_memo_job for one pass."""

    def claim():
        result = supabase.rpc(
            "claim_memo_job",
            {"p_kind": "intelligence", "p_lease_seconds": 120},
        ).execute()
        rows = list(getattr(result, "data", None) or [])
        if not rows:
            return None
        row = rows[0]
        return {
            "job_id": row.get("job_id"),
            "run_id": row.get("claimed_run_id"),
            "memo_id": str(row.get("claimed_memo_id")),
            "input_revision": row.get("claimed_revision"),
        }

    def load_memo(memo_id: str):
        result = supabase.table("memos").select("*").eq("id", memo_id).limit(1).execute()
        rows = list(getattr(result, "data", None) or [])
        return rows[0] if rows else None

    def publish(job_id, run_id, payload):
        result = supabase.rpc(
            "publish_memo_job",
            {"p_job_id": job_id, "p_run_id": run_id, "p_result": payload},
        ).execute()
        return getattr(result, "data", None)

    def sources(memo):
        if sources_for is not None:
            return sources_for(memo)
        return {"transcript": memo.get("transcript") or ""}

    def store(memo, payload):
        from app.services.intelligence.interpret import extraction_with_intelligence

        extraction = extraction_with_intelligence(memo.get("extraction"), payload)
        (
            supabase.table("memos")
            .update({"extraction": extraction})
            .eq("id", str(memo.get("id")))
            .execute()
        )

    return claim, load_memo, publish, sources, store


def make_database_tick(supabase, classify, sources_for=None):
    """Build one pass over claim_memo_job. No row means no classify and no publish."""
    claim, load_memo, publish, sources, store = database_bindings(supabase, sources_for)

    def tick():
        return run_claimed(claim, load_memo, publish, classify, sources, store)

    return tick


def install_intelligence_tick(classify=None) -> None:
    """Claim from Postgres only when publishing is enabled. Without an API key, do not claim."""
    from app.config import settings

    if not settings.INTELLIGENCE_WORKER_PUBLISH:
        set_worker_tick(None)
        return

    from app.deps import get_supabase
    from app.services.intelligence.interpret import classify_memo
    from app.services.llm.jev import JevClient

    async def default_classify(memo):
        client = JevClient(api_key=settings.OPENROUTER_API_KEY or "")
        return await classify_memo(memo, client)

    chosen = classify or default_classify

    async def tick():
        if classify is None and not (settings.OPENROUTER_API_KEY or "").strip():
            return None
        claim, load_memo, publish, sources, store = database_bindings(get_supabase())
        return await run_claimed_awaiting(claim, load_memo, publish, chosen, sources, store)

    set_worker_tick(tick)


def revision_for_memo(memo: dict) -> str:
    extraction = memo.get("extraction") or {}
    if hasattr(extraction, "model_dump"):
        extraction = extraction.model_dump()
    extraction = {
        key: value for key, value in dict(extraction).items() if key != "intelligence"
    }
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
