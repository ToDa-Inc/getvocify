"""Ask web turns. Pending work answers 202. A replay returns the same turn."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.deps import get_membership
from app.services.company import Membership
from app.services.crm_copilot.web_sessions import (
    TurnConflict,
    UncertainOperation,
    accept_turn,
    confirm_operation,
)

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])

_TURNS: dict[tuple[str, str, str], dict] = {}
_OPERATIONS: dict[tuple[str, str, str], dict] = {}
_store = None


def set_ask_store(store) -> None:
    global _store
    _store = store


class TurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


class ConfirmRequest(BaseModel):
    revision: int
    contact_id: str = Field(min_length=1)


def remember_operation(user_id: str, conversation_id: str, operation: dict) -> None:
    _OPERATIONS[(user_id, conversation_id, operation["operation_id"])] = dict(operation)


def _public(turn: dict) -> dict:
    return {
        "conversation_id": turn["conversation_id"],
        "turn_id": turn["turn_id"],
        "status": turn["status"],
        "client_turn_id": turn["client_turn_id"],
        "text": turn["text"],
    }


@router.post("/conversations/{conversation_id}/turns")
async def post_turn(
    conversation_id: str,
    body: TurnRequest,
    membership: Membership = Depends(get_membership),
):
    if _store is not None:
        turn = _store.save_turn(
            user_id=membership.user_id,
            company_id=membership.company_id,
            conversation_id=conversation_id,
            client_turn_id=body.client_turn_id,
            text=body.text,
        )
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
    _TURNS[(membership.user_id, conversation_id, body.client_turn_id)] = {
        **turn,
        "user_id": membership.user_id,
        "company_id": membership.company_id,
    }
    code = status.HTTP_200_OK if turn["status"] == "completed" else status.HTTP_202_ACCEPTED
    return JSONResponse(status_code=code, content=_public(turn))


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
