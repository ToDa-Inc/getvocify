"""Ask web turns. Pending work answers 202. A replay returns the same turn."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.deps import get_membership
from app.services.company import Membership
from app.services.crm_copilot.web_sessions import accept_turn

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])

_TURNS: dict[tuple[str, str, str], dict] = {}


class TurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


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
    for (user_id, conv, _client), turn in _TURNS.items():
        if user_id == membership.user_id and conv == conversation_id and turn["turn_id"] == turn_id:
            return _public(turn)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")
