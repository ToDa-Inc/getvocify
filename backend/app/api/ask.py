"""Ask web turns. Pending work answers 202. A replay returns the same turn."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.deps import get_membership
from app.services.company import Membership
from app.services.crm_copilot.web_sessions import (
    TurnConflict,
    UncertainOperation,
    accept_turn,
    attach_read,
    bind_ask_actor,
    confirm_operation,
)

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])

_TURNS: dict[tuple[str, str, str], dict] = {}
_OPERATIONS: dict[tuple[str, str, str], dict] = {}
_store = None
_transcriber = None
_reader = None
_loop = None


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
    remember_operation(
        user_id,
        conversation_id,
        {
            "operation_id": confirmation["operation_id"],
            "revision": confirmation["revision"],
            "contact_id": confirmation["contact_id"],
            "applied": False,
            "status": "proposed",
        },
    )


def _public(turn: dict) -> dict:
    return {
        "conversation_id": turn["conversation_id"],
        "turn_id": turn["turn_id"],
        "status": turn["status"],
        "client_turn_id": turn["client_turn_id"],
        "text": turn["text"],
        "coverage": turn.get("coverage"),
        "item_count": turn.get("item_count"),
        "confirmation": turn.get("confirmation"),
    }


@router.post("/conversations/{conversation_id}/turns")
async def post_turn(
    conversation_id: str,
    body: TurnRequest,
    membership: Membership = Depends(get_membership),
):
    bind_ask_actor(membership.user_id, membership.company_id)
    if _store is not None:
        turn = _store.save_turn(
            user_id=membership.user_id,
            company_id=membership.company_id,
            conversation_id=conversation_id,
            client_turn_id=body.client_turn_id,
            text=body.text,
        )
        if not turn.get("replayed"):
            turn = await _finish(turn, body.text)
            _stage_confirmation(turn, membership.user_id, conversation_id)
        code = status.HTTP_200_OK if turn["status"] == "completed" else status.HTTP_202_ACCEPTED
        return JSONResponse(status_code=code, content=_public(turn))
    scoped: dict = {
        key[1:]: value
        for key, value in _TURNS.items()
        if key[0] == membership.user_id and key[1] == conversation_id
    }
    turn = accept_turn(
        scoped,
        conversation_id=conversation_id,
        client_turn_id=body.client_turn_id,
        text=body.text,
    )
    if not turn.get("replayed"):
        turn = await _finish(turn, body.text)
        _stage_confirmation(turn, membership.user_id, conversation_id)
    _TURNS[(membership.user_id, conversation_id, body.client_turn_id)] = {
        **turn,
        "user_id": membership.user_id,
        "company_id": membership.company_id,
    }
    code = status.HTTP_200_OK if turn["status"] == "completed" else status.HTTP_202_ACCEPTED
    return JSONResponse(status_code=code, content=_public(turn))


async def _finish(turn: dict, text: str) -> dict:
    if _loop is not None:
        result = _loop(text)
        if asyncio.iscoroutine(result):
            result = await result
        if result is None:
            return turn
        confirmation = None
        if hasattr(result, "text"):
            answer = result.text
            envelope = getattr(result, "envelope", None)
        else:
            answer = result.get("text") or turn["text"]
            envelope = result.get("envelope")
            confirmation = result.get("confirmation")
        updated = {**turn, "status": "completed", "text": answer}
        if confirmation:
            updated["confirmation"] = confirmation
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


@router.post("/conversations/{conversation_id}/operations/{operation_id}/confirm")
async def confirm_ask_operation(
    conversation_id: str,
    operation_id: str,
    body: ConfirmRequest,
    membership: Membership = Depends(get_membership),
):
    key = (membership.user_id, conversation_id, operation_id)
    operation = _OPERATIONS.get(key)
    if not operation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operación no encontrada")
    try:
        result = confirm_operation(
            operation,
            operation_id=operation_id,
            revision=body.revision,
            contact_id=body.contact_id,
        )
    except TurnConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UncertainOperation as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _OPERATIONS[key] = result
    return result


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
