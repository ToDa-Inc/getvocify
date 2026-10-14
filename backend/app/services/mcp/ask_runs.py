"""ask_vocify: the dashboard's Ask engine, read-only, one question at a time, for another agent.

Each question is its own Ask conversation (`mcp:<run_id>`), stored like any web Ask turn so a slow one can
be polled with get_ask_result from any server instance. The caller's agent keeps the conversation; this
side keeps no follow-up memory. It runs fewer rounds than the web Ask and is capped per user per day,
because every question is a paid model run.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import anyio

from app.config import settings
from app.services.mcp.access import AccessDenied, actor_visibility

logger = logging.getLogger(__name__)

CONVERSATION_PREFIX = "mcp:"
LOST_AFTER = timedelta(minutes=5)  # a run still pending after this died with its server instance
_RUNNING: set[asyncio.Task] = set()

FAILED = {
    "status": "failed",
    "error": (
        "Ask Vocify could not answer this one. Use list_interactions, get_interaction or get_coaching "
        "to read the data directly."
    ),
}


def is_mcp_conversation(conversation_id: Optional[str]) -> bool:
    return str(conversation_id or "").startswith(CONVERSATION_PREFIX)


def _conversation(run_id: str) -> str:
    return CONVERSATION_PREFIX + run_id


def _store(supabase: Any):
    from app.services.crm_copilot.web_sessions import SupabaseAskStore

    return SupabaseAskStore(supabase)


def asks_in_last_day(supabase: Any, user_id: str, *, cap: int) -> int:
    """How many ask_vocify questions this user asked in the last 24 hours (counted up to cap + 1)."""
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rows = (
        supabase.table("copilot_web_turns")
        .select("id")
        .eq("user_id", user_id)
        .like("conversation_id", CONVERSATION_PREFIX + "%")
        .gte("created_at", since)
        .limit(cap + 1)
        .execute()
        .data
        or []
    )
    return len(rows)


def _view(turn: dict) -> dict:
    """What the calling agent reads: the answer and the interactions it rests on."""
    status = turn.get("status")
    if status == "failed":
        return dict(FAILED)
    if status != "completed":
        return {"status": "running"}
    evidence = [
        {k: item[k] for k in ("id", "memo_id", "quote", "speaker", "at", "rep") if item.get(k)}
        for item in turn.get("evidence") or []
        if isinstance(item, dict)
    ]
    out: dict = {"status": "completed", "answer": turn.get("text") or ""}
    if evidence:
        out["evidence"] = evidence
    if turn.get("coverage_note"):
        out["coverage_note"] = turn["coverage_note"]
    return out


async def _run(membership, conversation_id: str, turn: dict, question: str, supabase: Any) -> dict:
    from app.services.crm_copilot import web_sessions
    from app.services.crm_copilot.web_sessions import live_ask_loop, public_answer

    try:
        body = await live_ask_loop(question, read_only=True, max_rounds=settings.MCP_ASK_MAX_ROUNDS)
    except Exception:  # noqa: BLE001
        logger.exception("mcp ask run failed")
        body = None
    finally:
        web_sessions._sessions.pop((membership.user_id, conversation_id), None)  # one-shot: no memory kept
    if body is None:
        finished = {**turn, "status": "failed", "text": "", "question": question}
    else:
        finished = {
            **turn,
            "status": "completed",
            "text": public_answer(body.get("text") or ""),
            "question": question,
            **{k: body[k] for k in ("evidence", "coverage_note") if body.get(k)},
        }
    try:
        await anyio.to_thread.run_sync(
            lambda: _store(supabase).persist_turn(
                user_id=membership.user_id, conversation_id=conversation_id, turn_id=turn["turn_id"], turn=finished,
            )
        )
    except Exception:  # noqa: BLE001 - the caller waiting in this process still gets the answer
        logger.exception("mcp ask run could not be stored")
    return _view(finished)


async def ask(membership, question: str, supabase: Any, *, wait_seconds: Optional[float] = None) -> dict:
    """The answer if it is ready within the wait, else {status: running, run_id}. Raises AccessDenied at the cap."""
    from app.services.crm_copilot.web_sessions import bind_ask_actor

    cap = settings.MCP_ASK_PER_DAY
    used = await anyio.to_thread.run_sync(lambda: asks_in_last_day(supabase, membership.user_id, cap=cap))
    if used >= cap:
        raise AccessDenied(
            f"The daily limit of {cap} ask_vocify questions is reached. list_interactions, get_interaction and "
            "get_coaching still work."
        )
    run_id = uuid.uuid4().hex
    conversation_id = _conversation(run_id)
    turn = await anyio.to_thread.run_sync(
        lambda: _store(supabase).save_turn(
            user_id=membership.user_id,
            company_id=membership.company_id,
            conversation_id=conversation_id,
            client_turn_id=run_id,
            text=question,
        )
    )
    visibility = await anyio.to_thread.run_sync(lambda: actor_visibility(supabase, membership))
    # Bound here, in this task's context, so the run created below copies the caller (not a thread's copy).
    bind_ask_actor(
        membership.user_id, membership.company_id, membership.role, conversation_id,
        visibility=visibility, sales_role=getattr(membership, "sales_role", None),
    )
    task = asyncio.get_running_loop().create_task(_run(membership, conversation_id, turn, question, supabase))
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)
    wait = settings.MCP_ASK_WAIT_SECONDS if wait_seconds is None else wait_seconds
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=wait)
    except asyncio.TimeoutError:
        return {
            "status": "running",
            "run_id": run_id,
            "note": "Still working. Call get_ask_result with this run_id in about 15 seconds.",
        }


def result(membership, run_id: str, supabase: Any) -> dict:
    """The stored state of a run. Only the user who asked can read it."""
    try:
        run_id = uuid.UUID(str(run_id).strip()).hex
    except ValueError:
        return {"status": "not_found", "error": "No ask_vocify run with that run_id."}
    turns = _store(supabase).list_turns(user_id=membership.user_id, conversation_id=_conversation(run_id))
    if not turns:
        return {"status": "not_found", "error": "No ask_vocify run with that run_id."}
    turn = turns[-1]
    if turn.get("status") in ("completed", "failed"):
        return _view(turn)
    created = turn.get("created_at")
    try:
        started = datetime.fromisoformat(str(created).replace("Z", "+00:00")) if created else None
    except ValueError:
        started = None
    if started and datetime.now(timezone.utc) - started > LOST_AFTER:
        return dict(FAILED)
    return {"status": "running", "run_id": run_id, "note": "Still working. Try again in about 15 seconds."}
