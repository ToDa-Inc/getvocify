"""Live call awareness API.

The rep's Mac app reads the CRM pages open in the rep's browsers (front window
first) and decides call vs meeting. /preview names the contact for the notch
island before anything records; /start opens the live call with that contact.
The recorder then puts the contact on the memo it uploads at hang-up. Clients
follow the call on a per-user event stream.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict
from typing import AsyncIterator, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.api.crm import get_contact_context_for_extension
from app.api.crm_pipedrive import get_pipedrive_person_context
from app.services.company import Membership
from app.services.company_scope import get_crm_connection
from app.services.crm_providers.calling import NO_CONTEXT, RecordContext
from app.services.crm_providers.calling_registry import calling_adapter
from app.services.live_calls.crm_url import CrmRecord, record_on_screen
from app.services.live_calls.hub import LiveCallHub, live_call_hub
from app.services.live_calls.state import InteractionKind, LiveCall, end_call, pick_contact, start_call

router = APIRouter(prefix="/api/v1/live-calls", tags=["live-calls"])

HEARTBEAT_SECONDS = 15.0
_ACCOUNT_KEY = {"hubspot": "portal_id", "pipedrive": "company_domain"}


class PagesIn(BaseModel):
    # Active tab URL of each browser window showing the CRM, front-most first.
    page_urls: list[str] = Field(default_factory=list, max_length=20)


class StartCallIn(PagesIn):
    kind: InteractionKind = "call"


class PickContactIn(BaseModel):
    provider: Literal["hubspot", "pipedrive"]
    contact_id: str = Field(..., pattern=r"^\d{1,32}$")


def _connected_account_id(supabase: Client, user_id: str, provider: str) -> Optional[str]:
    """The account (HubSpot portal, Pipedrive domain) the rep's company connected, if known."""
    try:
        connection = get_crm_connection(supabase, user_id, provider)
    except Exception:
        return None
    value = ((connection or {}).get("metadata") or {}).get(_ACCOUNT_KEY[provider])
    return str(value) if value else None


async def _contact_name(supabase: Client, user_id: str, provider: str, contact_id: str) -> Optional[str]:
    """Same name the extension shows for the record (cached CRM context reads)."""
    try:
        if provider == "hubspot":
            context = await get_contact_context_for_extension(contact_id, supabase=supabase, user_id=user_id)
        else:
            context = await get_pipedrive_person_context(contact_id, supabase=supabase, user_id=user_id)
    except Exception:
        return None
    return (context or {}).get("contactName") or None


async def _record_context(supabase: Client, user_id: str, record: Optional[CrmRecord]) -> RecordContext:
    """Who the record on screen can be called at, for the CRMs Vocify can call."""
    adapter = calling_adapter(record.provider) if record else None
    if not adapter:
        return NO_CONTEXT
    return await adapter.record_context(record, supabase=supabase, user_id=user_id)


def _state(call: Optional[LiveCall]) -> dict:
    return {"call": call.to_dict() if call else None}


@router.get("/current")
async def current_live_call(membership: Membership = Depends(get_membership)):
    return _state(live_call_hub.current(membership.user_id))


@router.post("/preview")
async def preview_live_call(
    body: PagesIn,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """Who a call would be with, for the notch island. Starts nothing."""
    user_id = membership.user_id
    record = record_on_screen(url[:2048] for url in body.page_urls)
    account = _connected_account_id(supabase, user_id, record.provider) if record else None
    call = start_call("preview", record, time.time(), connected_account_id=account)
    name = await _contact_name(supabase, user_id, call.provider, call.contact_id) if call.contact_id else None
    # call.record is None for another account's page, so that page is never read.
    context = await _record_context(supabase, user_id, call.record)
    return {
        "provider": call.provider,
        "contact_id": call.contact_id,
        "contact_name": name,
        "record": call.to_dict()["record"],
        "needs_contact": call.contact_id is None,
        "callee": asdict(context.callee) if context.callee else None,
        "contacts_count": context.contacts_count,
    }


@router.post("/start")
async def start_live_call(
    body: StartCallIn,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The desktop: a call or meeting started. Returns it with the contact on screen.

    Idempotent while a call is live, so a retried start never opens a second call.
    """
    user_id = membership.user_id
    current = live_call_hub.current(user_id)
    if current and current.is_live:
        return _state(current)

    record = record_on_screen(url[:2048] for url in body.page_urls)
    account = _connected_account_id(supabase, user_id, record.provider) if record else None
    call = start_call(str(uuid.uuid4()), record, time.time(), kind=body.kind, connected_account_id=account)
    live_call_hub.publish(user_id, call)
    return _state(call)


@router.patch("/current")
async def pick_live_call_contact(body: PickContactIn, membership: Membership = Depends(get_membership)):
    """The rep corrected who the call is with (or picked one of a deal's contacts)."""
    user_id = membership.user_id
    call = live_call_hub.current(user_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No call")
    call = pick_contact(call, body.provider, body.contact_id)
    live_call_hub.publish(user_id, call)
    return _state(call)


@router.post("/current/end")
async def end_live_call(membership: Membership = Depends(get_membership)):
    """The desktop: the call is over. The capture itself completes via /captures."""
    user_id = membership.user_id
    call = live_call_hub.current(user_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No call")
    call = end_call(call, time.time())
    live_call_hub.publish(user_id, call)
    return _state(call)


def _sse(kind: str, call: Optional[LiveCall]) -> str:
    return f"data: {json.dumps({'type': kind, **_state(call)}, ensure_ascii=False)}\n\n"


async def live_call_stream(
    hub: LiveCallHub,
    user_id: str,
    *,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Snapshot first, then every change. Subscribes before the snapshot so
    nothing published in between is lost."""
    async with hub.subscribe(user_id) as queue:
        yield _sse("snapshot", hub.current(user_id))
        while True:
            try:
                call = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _sse("update", call)


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
