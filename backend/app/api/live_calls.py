"""Live call awareness API.

The Chrome extension POSTs dialer events it sees on the CRM page. The rep's
desktop app (or any other client) reads the current call and follows changes
on a per-user event stream.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.live_calls.hub import LiveCallHub, live_call_hub
from app.services.live_calls.resolve import hubspot_contact_by_phone
from app.services.live_calls.state import LiveCallEvent, apply_event, with_contact

router = APIRouter(prefix="/api/v1/live-calls", tags=["live-calls"])

HEARTBEAT_SECONDS = 15.0


class LiveCallEventIn(BaseModel):
    provider: Literal["hubspot"] = "hubspot"
    source: Literal["hubspot_calling_sdk"] = "hubspot_calling_sdk"
    event: Literal["started", "answered", "ended", "completed"]
    external_call_id: str = Field(..., min_length=1, max_length=200)
    direction: Literal["outbound", "inbound"] = "outbound"
    to_number: Optional[str] = Field(default=None, max_length=40)
    from_number: Optional[str] = Field(default=None, max_length=40)
    end_status: Optional[str] = Field(default=None, max_length=40)
    engagement_id: Optional[str] = Field(default=None, max_length=64)
    page_object_type: Optional[Literal["contact", "company", "deal"]] = None
    page_record_id: Optional[str] = Field(default=None, pattern=r"^\d{1,32}$")


async def resolve_contact_by_phone(
    hub: LiveCallHub,
    supabase: Client,
    user_id: str,
    external_call_id: str,
    phone: str,
) -> None:
    """Attach the phone-matched contact if the call is still unassigned."""
    found = await hubspot_contact_by_phone(supabase, user_id, phone)
    if found is None:
        return
    latest = hub.current(user_id)
    if latest is None or latest.external_call_id != external_call_id or latest.contact_id:
        return
    hub.publish(
        user_id,
        with_contact(latest, found.contact_id, source="phone", name=found.name, now=time.time()),
    )


@router.post("/events")
async def report_live_call_event(
    body: LiveCallEventIn,
    background: BackgroundTasks,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """Fold a dialer event into the rep's live call and notify their clients."""
    user_id = membership.user_id
    previous = live_call_hub.current(user_id)
    call = apply_event(
        previous,
        LiveCallEvent(**body.model_dump(), occurred_at=time.time()),
    )
    live_call_hub.publish(user_id, call)

    same_call = previous is not None and previous.external_call_id == call.external_call_id
    number_just_known = call.remote_number and not (same_call and previous.remote_number)
    if number_just_known and call.contact_id is None:
        background.add_task(
            resolve_contact_by_phone,
            live_call_hub,
            supabase,
            user_id,
            call.external_call_id,
            call.remote_number,
        )
    return {"call": call.to_dict()}


@router.get("/current")
async def current_live_call(membership: Membership = Depends(get_membership)):
    call = live_call_hub.current(membership.user_id)
    return {"call": call.to_dict() if call else None}


def _sse(kind: str, call: Optional[dict]) -> str:
    return f"data: {json.dumps({'type': kind, 'call': call}, ensure_ascii=False)}\n\n"


async def live_call_stream(
    hub: LiveCallHub,
    user_id: str,
    *,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Snapshot first, then every change. Subscribes before the snapshot so
    nothing published in between is lost."""
    async with hub.subscribe(user_id) as queue:
        current = hub.current(user_id)
        yield _sse("snapshot", current.to_dict() if current else None)
        while True:
            try:
                call = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _sse("call", call.to_dict())


@router.get("/stream")
async def stream_live_calls(membership: Membership = Depends(get_membership)):
    return StreamingResponse(
        live_call_stream(live_call_hub, membership.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
