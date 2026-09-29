"""Ask web turns. Pending work answers 202. A replay returns the same turn.

Two ways to run a turn, one loop: POST .../turns (answer or 202, poll) and POST .../turns/stream (SSE).
A stream is only a view of the persisted turn: the run finishes even if the reader leaves, and a
reload recovers the answer with GET .../turns/{id}.
"""

from __future__ import annotations

import asyncio
import inspect
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.crm_copilot import suggestions, web_sessions as ask_sessions
from app.services.crm_copilot.web_sessions import (
    TurnConflict,
    UncertainOperation,
    accept_turn,
    attach_read,
    bind_ask_actor,
    cancel_operation,
    progress_end,
    progress_get,
    progress_start,
    confirm_operation,
    proposed_operation_from_turn,
    public_answer,
)

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])

_TURNS: dict[tuple[str, str, str], dict] = {}
_OPERATIONS: dict[tuple[str, str, str], dict] = {}
_TASKS: set[asyncio.Task] = set()
_store = None
_transcriber = None
_reader = None
_loop = None

HEARTBEAT_SECONDS = 15
TITLE_MAX = 80
_SERVER_ONLY = ("tool", "args")


def set_ask_loop(loop) -> None:
    global _loop
    _loop = loop


def set_ask_reader(reader) -> None:
    global _reader
    _reader = reader


def set_ask_transcriber(transcriber) -> None:
    global _transcriber
    _transcriber = transcriber


def set_ask_store(store) -> None:
    global _store
    _store = store


class TurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


class ConfirmRequest(BaseModel):
    revision: int
    contact_id: str = Field(min_length=1)


class TranscribeRequest(BaseModel):
    audio_base64: str = Field(min_length=1)


def remember_operation(user_id: str, conversation_id: str, operation: dict) -> None:
    _OPERATIONS[(user_id, conversation_id, operation["operation_id"])] = dict(operation)


def _stage_confirmation(turn: dict, user_id: str, conversation_id: str) -> None:
    confirmation = turn.get("confirmation") or None
    if not confirmation:
        return
    operation = {
        "operation_id": confirmation["operation_id"],
        "revision": confirmation["revision"],
        "contact_id": confirmation["contact_id"],
        "applied": False,
        "status": "proposed",
    }
    for key in _SERVER_ONLY:
        if key in confirmation:
            operation[key] = confirmation[key]
    remember_operation(user_id, conversation_id, operation)


def _public_confirmation(confirmation: dict | None) -> dict | None:
    """What the reader may see. The tool and its arguments stay on the server."""
    if not confirmation:
        return None
    return {k: v for k, v in confirmation.items() if k not in _SERVER_ONLY}


def _public(turn: dict) -> dict:
    body = {
        "conversation_id": turn["conversation_id"],
        "turn_id": turn["turn_id"],
        "status": turn["status"],
        "client_turn_id": turn["client_turn_id"],
        "text": turn["text"],
        "question": turn.get("question"),
        "coverage": turn.get("coverage"),
        "item_count": turn.get("item_count"),
        "confirmation": _public_confirmation(turn.get("confirmation")),
    }
    for key in ("choices", "evidence", "coverage_note", "call_targets", "steps"):
        if turn.get(key):
            body[key] = turn[key]
    return body


def _bind(membership: Membership, conversation_id: str, *, progress_key: tuple | None = None) -> None:
    """Who is asking, from the session. Visibility is the company's rule for members (SALES_ROLES_ENABLED)."""
    from app.deps import get_supabase
    from app.services.activity_scope import effective_visibility

    visibility = None
    if getattr(membership, "visibility", None) == "team":  # the only value that widens a member's view
        try:
            visibility = effective_visibility(get_supabase(), membership)
        except Exception:
            visibility = None  # unreadable means today's owner/admin-only behaviour, never a wider one
    bind_ask_actor(
        membership.user_id, membership.company_id, membership.role, conversation_id,
        progress_key=progress_key, visibility=visibility, sales_role=getattr(membership, "sales_role", None),
    )


def _accepts_events(fn) -> bool:
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "on_event" or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


def _accept(membership: Membership, conversation_id: str, client_turn_id: str, text: str) -> dict:
    """Idempotent by (user, conversation, client turn). A replay returns the stored turn."""
    if _store is not None:
        turn = _store.save_turn(
            user_id=membership.user_id,
            company_id=membership.company_id,
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            text=text,
        )
        return turn if turn.get("replayed") else {**turn, "question": text}
    scoped = {
        key[1:]: value
        for key, value in _TURNS.items()
        if key[0] == membership.user_id and key[1] == conversation_id
    }
    return accept_turn(scoped, conversation_id=conversation_id, client_turn_id=client_turn_id, text=text)


def _remember_turn(membership: Membership, conversation_id: str, turn: dict) -> None:
    if _store is not None:
        if turn.get("status") in ("completed", "failed"):
            _store.persist_turn(
                user_id=membership.user_id,
                conversation_id=conversation_id,
                turn_id=turn["turn_id"],
                turn=turn,
            )
        return
    _TURNS[(membership.user_id, conversation_id, turn["client_turn_id"])] = {
        **turn,
        "user_id": membership.user_id,
        "company_id": membership.company_id,
    }


def _hydrate(membership: Membership, conversation_id: str) -> None:
    """After a restart the conversation still remembers who it was talking about."""
    loader = getattr(_store, "latest_memory", None)
    if loader is None:
        return
    key = (membership.user_id, conversation_id or "")
    if key in ask_sessions._sessions:
        return
    try:
        memory = loader(user_id=membership.user_id, conversation_id=conversation_id)
    except Exception:  # restoring memory is a courtesy: a failed read starts the turn clean, it never fails it
        import logging

        logging.getLogger(__name__).warning("ask memory restore failed", exc_info=True)
        return
    ask_sessions.seed_session(membership.user_id, conversation_id, memory)


async def _call_loop(text: str, on_event):
    if on_event is not None and _accepts_events(_loop):
        return _loop(text, on_event=on_event)
    return _loop(text)


async def _finish(turn: dict, text: str, on_event=None) -> dict:
    if _loop is not None:
        result = await _call_loop(text, on_event)
        if asyncio.iscoroutine(result):
            result = await result
        if result is None:
            # Failed: no answer text. The question stays in `question`, never in `text` -
            # the UI would otherwise show the user's own words back as if Vocify said them.
            return {**turn, "status": "failed", "text": "", "question": turn.get("question") or text}
        confirmation = None
        choices = None
        extras: dict = {}
        if hasattr(result, "text"):
            answer = public_answer(result.text)
            envelope = getattr(result, "envelope", None)
        else:
            answer = public_answer(result.get("text") or turn["text"])
            envelope = result.get("envelope")
            confirmation = result.get("confirmation")
            choices = result.get("choices")
            extras = {k: result[k] for k in ("evidence", "coverage_note", "memory", "call_targets", "steps") if result.get(k)}
        updated = {**turn, "status": "completed", "text": answer, "question": turn.get("question") or text, **extras}
        if confirmation:
            updated["confirmation"] = confirmation
        if choices:
            updated["choices"] = choices
        if envelope:
            updated = attach_read(updated, envelope)
        return updated
    if _reader is None:
        return turn
    envelope = _reader(text)
    if asyncio.iscoroutine(envelope):
        envelope = await envelope
    if not envelope:
        return turn
    return attach_read(turn, envelope)


@router.get("/conversations/{conversation_id}/progress")
async def get_turn_progress(
    conversation_id: str,
    client_turn_id: str,
    membership: Membership = Depends(get_membership),
):
    """What the turn still being answered has done so far (its tool steps), polled by the
    app while its POST is in flight. `running: false` once it finished or was never here."""
    found = progress_get((membership.user_id, conversation_id, client_turn_id))
    return {"running": found is not None, "steps": (found or {}).get("steps", [])}


@router.post("/conversations/{conversation_id}/turns")
async def post_turn(
    conversation_id: str,
    body: TurnRequest,
    membership: Membership = Depends(get_membership),
):
    progress_key = (membership.user_id, conversation_id, body.client_turn_id)
    _bind(membership, conversation_id, progress_key=progress_key)
    turn = _accept(membership, conversation_id, body.client_turn_id, body.text)
    if not turn.get("replayed"):
        progress_start(progress_key)
        try:
            _hydrate(membership, conversation_id)
            turn = await _finish(turn, body.text)
            _stage_confirmation(turn, membership.user_id, conversation_id)
            _remember_turn(membership, conversation_id, turn)
        finally:
            progress_end(progress_key)
    code = status.HTTP_200_OK if turn["status"] != "pending" else status.HTTP_202_ACCEPTED
    return JSONResponse(status_code=code, content=_public(turn))


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _closing_events(turn: dict) -> list[dict]:
    """The events that end a turn. Live runs and replays send the same ones."""
    events: list[dict] = []
    if turn["status"] == "failed":
        events.append({"type": "error", "code": "ask_failed", "retryable": True})
    elif turn["status"] == "completed":
        events.append(
            {
                "type": "final",
                "text": turn["text"],
                "evidence": turn.get("evidence") or [],
                "coverage_note": turn.get("coverage_note"),
                "coverage": turn.get("coverage"),
                **({"call_targets": turn["call_targets"]} if turn.get("call_targets") else {}),
            }
        )
        if turn.get("choices"):
            events.append({"type": "choices", "options": turn["choices"]})
        confirmation = _public_confirmation(turn.get("confirmation"))
        if confirmation and not confirmation.get("applied") and not confirmation.get("cancelled"):
            events.append({"type": "confirm", **confirmation, "summary": turn["text"]})
    events.append({"type": "done", "turn_id": turn["turn_id"], "status": turn["status"]})
    return events


def _start_turn(turn: dict, text: str, membership: Membership, conversation_id: str):
    """Run the turn in its own task so a reader leaving cannot cancel it."""
    _bind(membership, conversation_id)
    queue: asyncio.Queue = asyncio.Queue()

    async def run() -> None:
        try:
            _hydrate(membership, conversation_id)
            try:
                finished = await _finish(turn, text, on_event=queue.put)
            except Exception:
                import logging

                logging.getLogger(__name__).exception("ask turn failed")
                finished = {**turn, "status": "failed", "question": turn.get("question") or text}
            _stage_confirmation(finished, membership.user_id, conversation_id)
            _remember_turn(membership, conversation_id, finished)
            for event in _closing_events(finished):
                await queue.put(event)
        finally:
            await queue.put(None)

    task = asyncio.get_running_loop().create_task(run())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return queue, task


@router.post("/conversations/{conversation_id}/turns/stream")
async def post_turn_stream(
    conversation_id: str,
    body: TurnRequest,
    membership: Membership = Depends(get_membership),
):
    _bind(membership, conversation_id)
    turn = _accept(membership, conversation_id, body.client_turn_id, body.text)
    replayed = bool(turn.get("replayed"))
    if replayed:
        events = [{"type": "turn", "turn_id": turn["turn_id"], "replayed": True}]
        if turn["status"] in ("completed", "failed"):
            events += _closing_events(turn)
        else:
            events += [{"type": "pending", "turn_id": turn["turn_id"]}, {"type": "done", "turn_id": turn["turn_id"], "status": "pending"}]

        async def replay():
            for event in events:
                yield _sse(event)

        stream = replay()
    else:
        queue, _task = _start_turn(turn, body.text, membership, conversation_id)

        async def live():
            yield _sse({"type": "turn", "turn_id": turn["turn_id"], "replayed": False})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event is None:
                    return
                yield _sse(event)

        stream = live()
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/conversations/{conversation_id}/turns/{turn_id}")
async def get_turn(
    conversation_id: str,
    turn_id: str,
    membership: Membership = Depends(get_membership),
):
    if _store is not None:
        turn = _store.get_turn(
            user_id=membership.user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
        if not turn:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")
        return _public(turn)
    for (user_id, conv, _client), turn in _TURNS.items():
        if user_id == membership.user_id and conv == conversation_id and turn["turn_id"] == turn_id:
            return _public(turn)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")


def _user_turns(user_id: str, conversation_id: str | None = None) -> list[dict]:
    if _store is not None:
        return _store.list_turns(user_id=user_id, conversation_id=conversation_id)
    return [
        turn
        for (uid, conv, _client), turn in _TURNS.items()
        if uid == user_id and (conversation_id is None or conv == conversation_id)
    ]


@router.get("/conversations")
async def list_conversations(membership: Membership = Depends(get_membership)):
    """One row per conversation, newest first. The title is the first question."""
    grouped: dict[str, list[dict]] = {}
    for turn in _user_turns(membership.user_id):
        grouped.setdefault(turn["conversation_id"], []).append(turn)
    rows = []
    for cid, turns in grouped.items():
        first = next((t.get("question") for t in turns if t.get("question")), None) or ""
        rows.append(
            {
                "id": cid,
                "title": first[:TITLE_MAX],
                "turns": len(turns),
                "updated_at": turns[-1].get("created_at"),
                "_order": len(rows),
            }
        )
    rows.sort(key=lambda r: (r["updated_at"] or "", r["_order"]), reverse=True)
    for row in rows:
        row.pop("_order")
    return {"conversations": rows}


@router.delete("/conversations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_conversations(membership: Membership = Depends(get_membership)):
    """Start clean: every conversation of the caller, on every device."""
    if _store is not None:
        _store.delete_all(user_id=membership.user_id)
    else:
        for key in [k for k in _TURNS if k[0] == membership.user_id]:
            del _TURNS[key]
    for key in [k for k in _OPERATIONS if k[0] == membership.user_id]:
        del _OPERATIONS[key]
    for key in [k for k in ask_sessions._sessions if k[0] == membership.user_id]:
        del ask_sessions._sessions[key]
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _member_ids(supabase, membership: Membership) -> list[str]:
    if membership.role not in ("owner", "admin"):
        return [membership.user_id]
    from app.services.company import CompanyService

    return [
        str(m["user_id"])
        for m in CompanyService(supabase).list_members(membership.company_id)
        if m.get("user_id") and (m.get("status") or "active") == "active"
    ]


def _has_hubspot(supabase, user_id: str) -> bool:
    from app.services.crm_providers import resolve_sync_connection_prefer_hubspot

    conn = resolve_sync_connection_prefer_hubspot(supabase, user_id)
    return bool(conn) and (conn.get("provider") or "").lower() == "hubspot"


@router.get("/suggestions")
async def get_suggestions(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    """Questions this account can actually answer. A new account gets none, not a fixed list."""
    try:
        ids = suggestions.compute(
            supabase,
            company_id=membership.company_id,
            user_id=membership.user_id,
            role=membership.role,
            member_ids=_member_ids(supabase, membership),
            has_crm=_has_hubspot(supabase, membership.user_id),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception("ask suggestions failed")
        ids = []
    return {"suggestions": ids}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, membership: Membership = Depends(get_membership)):
    turns = _user_turns(membership.user_id, conversation_id)
    if not turns:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
    return {"id": conversation_id, "turns": [_public(turn) for turn in turns]}


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, membership: Membership = Depends(get_membership)):
    if not _user_turns(membership.user_id, conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
    if _store is not None:
        _store.delete_conversation(user_id=membership.user_id, conversation_id=conversation_id)
    else:
        for key in [k for k in _TURNS if k[0] == membership.user_id and k[1] == conversation_id]:
            del _TURNS[key]
    for key in [k for k in _OPERATIONS if k[0] == membership.user_id and k[1] == conversation_id]:
        del _OPERATIONS[key]
    ask_sessions._sessions.pop((membership.user_id, conversation_id), None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _load_operation(user_id: str, conversation_id: str, operation_id: str) -> dict | None:
    key = (user_id, conversation_id, operation_id)
    operation = _OPERATIONS.get(key)
    if not operation and _store is not None:
        turn = _store.get_turn_by_operation(
            user_id=user_id,
            conversation_id=conversation_id,
            operation_id=operation_id,
        )
        if turn:
            operation = proposed_operation_from_turn(turn, operation_id)
    return operation


def _persist_confirmation(
    user_id: str, conversation_id: str, operation_id: str, *, text: str | None = None, **changes
) -> None:
    if _store is None:
        for key, turn in _TURNS.items():
            confirmation = turn.get("confirmation") or {}
            if key[0] == user_id and key[1] == conversation_id and confirmation.get("operation_id") == operation_id:
                _TURNS[key] = {**turn, **({"text": text} if text else {}), "confirmation": {**confirmation, **changes}}
        return
    stored = _store.get_turn_by_operation(user_id=user_id, conversation_id=conversation_id, operation_id=operation_id)
    if stored and stored.get("confirmation"):
        updated = {**stored, "status": "completed", "confirmation": {**stored["confirmation"], **changes}}
        if text:
            updated["text"] = text
        _store.persist_turn(user_id=user_id, conversation_id=conversation_id, turn_id=stored["turn_id"], turn=updated)


@router.post("/conversations/{conversation_id}/operations/{operation_id}/cancel")
async def cancel_ask_operation(
    conversation_id: str,
    operation_id: str,
    membership: Membership = Depends(get_membership),
):
    operation = _load_operation(membership.user_id, conversation_id, operation_id)
    if not operation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operación no encontrada")
    try:
        result = cancel_operation(operation, operation_id=operation_id)
    except TurnConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result.get("status") == "cancelled" and not result.get("replayed"):
        _persist_confirmation(membership.user_id, conversation_id, operation_id, cancelled=True)
        artifacts = ask_sessions.session_for(membership.user_id, conversation_id)
        ask_sessions._close_pending(artifacts, operation_id, {"ok": False, "error": "user declined"})
    _OPERATIONS[(membership.user_id, conversation_id, operation_id)] = result
    return _public_confirmation(result)


@router.post("/conversations/{conversation_id}/operations/{operation_id}/confirm")
async def confirm_ask_operation(
    conversation_id: str,
    operation_id: str,
    body: ConfirmRequest,
    membership: Membership = Depends(get_membership),
):
    key = (membership.user_id, conversation_id, operation_id)
    operation = _load_operation(membership.user_id, conversation_id, operation_id)
    if not operation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operación no encontrada")
    try:
        result = confirm_operation(
            operation,
            operation_id=operation_id,
            revision=body.revision,
            contact_id=body.contact_id,
        )
    except (TurnConflict, UncertainOperation) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result.get("replayed"):
        _OPERATIONS[key] = result
        return _public_confirmation(result)
    if operation.get("tool"):
        # The operation is the payload the reader was shown. Run it, then report what happened.
        _bind(membership, conversation_id)
        outcome = await ask_sessions.execute_stored_operation(operation)
        result = {**operation, **outcome, "replayed": False}
        _persist_confirmation(
            membership.user_id,
            conversation_id,
            operation_id,
            applied=bool(outcome.get("applied")),
            state=outcome["status"],
            **({"url": outcome["url"]} if outcome.get("url") else {}),
        )
    elif _loop is not None:
        _bind(membership, conversation_id)
        follow = _loop("", confirm=True)
        if asyncio.iscoroutine(follow):
            follow = await follow
        follow_text = follow.get("text") if isinstance(follow, dict) else None
        if follow_text:
            result = {**result, "text": follow_text}
        _persist_confirmation(membership.user_id, conversation_id, operation_id, text=follow_text, applied=True)
    else:
        _persist_confirmation(membership.user_id, conversation_id, operation_id, applied=True)
    _OPERATIONS[key] = result
    return _public_confirmation(result)


@router.post("/transcribe")
async def transcribe_question(
    body: TranscribeRequest,
    membership: Membership = Depends(get_membership),
):
    del membership
    import base64

    raw = base64.b64decode(body.audio_base64)
    if _transcriber is not None:
        spoken = _transcriber(raw, source="ask_voice")
        if asyncio.iscoroutine(spoken):
            spoken = await spoken
    else:
        from app.services.stt_batch import transcribe_bytes

        spoken = await transcribe_bytes(raw, source="ask_voice")
    return {"text": str(spoken or "").strip(), "memo_id": None}
