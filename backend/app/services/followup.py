"""Draft the follow-up email as soon as a memo's extraction is ready.

Runs in the background, once per memo, and never blocks or fails the memo pipeline.
Single-flight mirrors pipeline_lease.py: an in-process guard for same-instant bursts
plus a DB lease (followup_run_started_at) that survives restarts.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.services.followup_logic import (
    PROMPT_VERSION,
    build_messages,
    is_eligible,
    parse_draft,
    should_generate,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.md"
LEASE = timedelta(minutes=2)
LLM_TIMEOUT_S = 25.0
MEMO_COLUMNS = "id,user_id,transcript,extraction,screening_outcome,followup"

_guard = threading.Lock()
_live: set[str] = set()
_tasks: set[asyncio.Task] = set()  # hold references so fire-and-forget tasks are not garbage-collected


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _first(result: Any) -> Optional[dict]:
    rows = getattr(result, "data", None) or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def _acquire(supabase: Any, memo_id: str, run_id: str, now: datetime) -> bool:
    started = now.isoformat()
    cutoff = (now - LEASE).isoformat()
    q = (
        supabase.table("memos")
        .update({
            "followup": {"status": "generating", "started_at": started, "run_id": run_id,
                         "prompt_version": PROMPT_VERSION},
            "followup_run_started_at": started,
        })
        .eq("id", memo_id)
    )
    if hasattr(q, "or_"):  # same guard as pipeline_lease.py; without it: in-process single-flight only
        q = q.or_(f"followup.is.null,followup_run_started_at.lt.{cutoff}")
    q.execute()
    # PostgREST re-applies the PATCH filter to RETURNING (see pipeline_lease.py), so an
    # empty result does not mean we lost. Confirm ownership by primary key.
    row = _first(supabase.table("memos").select("followup").eq("id", memo_id).limit(1).execute())
    return bool(row) and (row.get("followup") or {}).get("run_id") == run_id


def _finish(supabase: Any, memo_id: str, run_id: str, followup: dict) -> None:
    (
        supabase.table("memos")
        .update({"followup": followup, "followup_run_started_at": None})
        .eq("id", memo_id)
        .eq("followup->>run_id", run_id)  # a reclaimed lease is not ours to overwrite
        .execute()
    )


async def _draft(supabase: Any, memo: dict, llm: Any) -> Optional[dict]:
    profile = _first(
        supabase.table("user_profiles").select("full_name,writing_samples")
        .eq("id", memo["user_id"]).limit(1).execute()
    ) or {}
    extraction = memo.get("extraction") or {}
    messages = build_messages(
        system_prompt=PROMPT_PATH.read_text(encoding="utf-8"),
        transcript=memo.get("transcript") or "",
        summary=extraction.get("summary") or "",
        next_steps=list(extraction.get("nextSteps") or []),
        contact_name=extraction.get("contactName"),
        rep_name=profile.get("full_name"),
        voice_samples=list(profile.get("writing_samples") or []),
    )
    payload = await llm.chat_json(messages, model=settings.FOLLOWUP_MODEL, temperature=0.4, timeout=LLM_TIMEOUT_S)
    return parse_draft(payload)


async def ensure_followup(supabase: Any, memo_id: str, *, llm: Any = None) -> None:
    """Idempotent. Safe to call from every path that completes an extraction."""
    if not settings.FOLLOWUP_ENABLED:
        return
    memo_id = str(memo_id)
    with _guard:
        if memo_id in _live:
            return
        _live.add(memo_id)
    run_id = str(uuid.uuid4())
    acquired = False
    try:
        memo = _first(supabase.table("memos").select(MEMO_COLUMNS).eq("id", memo_id).limit(1).execute())
        now = _utc_now()
        if not memo or not is_eligible(memo) or not should_generate(memo.get("followup"), now):
            return
        acquired = _acquire(supabase, memo_id, run_id, now)
        if not acquired:
            return
        if llm is None:
            from app.services.llm import LLMClient

            llm = LLMClient()
        draft = await _draft(supabase, memo, llm)
        base = {"run_id": run_id, "prompt_version": PROMPT_VERSION, "started_at": now.isoformat()}
        if draft:
            _finish(supabase, memo_id, run_id, {**base, "status": "ready", "ready_at": _utc_now().isoformat(), **draft})
        else:
            _finish(supabase, memo_id, run_id, {**base, "status": "unavailable", "reason": "empty_draft"})
    except Exception:
        logger.exception("followup: generation failed for memo %s", memo_id)
        if acquired:
            try:
                _finish(supabase, memo_id, run_id, {"run_id": run_id, "prompt_version": PROMPT_VERSION,
                                                     "status": "unavailable", "reason": "error"})
            except Exception:
                logger.exception("followup: could not mark memo %s unavailable", memo_id)
    finally:
        with _guard:
            _live.discard(memo_id)


def schedule_followup(supabase: Any, memo_id: str, *, llm: Any = None) -> bool:
    """Fire-and-forget from any path that just completed an extraction. Same pattern as
    schedule_transcript_polish.

    Returns whether a run was started: never with the kill switch off, and never outside
    an event loop (GET /memos/{id}/followup is then the safety net).
    """
    if not settings.FOLLOWUP_ENABLED:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    task = loop.create_task(ensure_followup(supabase, str(memo_id), llm=llm))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True
