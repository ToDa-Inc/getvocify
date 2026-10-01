"""Live call awareness API.

When the rep's desktop app starts a call it sends the CRM pages open in the
rep's browsers (front window first). The record on screen is the contact, and
the desktop capture memo is reserved with it, so extraction, the review target
and live help know who the call is with. Clients follow the call on a per-user
event stream.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.captures import reserve_capture
from app.services.company import Membership
from app.services.company_scope import get_crm_connection
from app.services.live_calls.crm_url import record_on_screen
from app.services.live_calls.hub import LiveCallHub, live_call_hub
from app.services.live_calls.state import LiveCall, attach_memo, end_call, pick_contact, start_call
from app.services.playbooks.live import live_version_id

router = APIRouter(prefix="/api/v1/live-calls", tags=["live-calls"])

HEARTBEAT_SECONDS = 15.0
_ACCOUNT_KEY = {"hubspot": "portal_id", "pipedrive": "company_domain"}


class StartCallIn(BaseModel):
    # Active tab URL of each browser window showing the CRM, front-most first.
    page_urls: list[str] = Field(default_factory=list, max_length=20)
    # When set, the desktop capture memo is reserved for this call with its contact.
    client_capture_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    started_at: Optional[datetime] = None


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


def _state(call: Optional[LiveCall]) -> dict:
    return {"call": call.to_dict() if call else None}


@router.get("/current")
async def current_live_call(membership: Membership = Depends(get_membership)):
    return _state(live_call_hub.current(membership.user_id))


@router.post("/start")
async def start_live_call(
    body: StartCallIn,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The desktop: a call started. Returns the call with the contact on screen.

    Idempotent while a call is live, so a retried start never opens a second call.
    """
    user_id = membership.user_id
    current = live_call_hub.current(user_id)
    if current and current.is_live:
        return _state(current)

    record = record_on_screen(url[:2048] for url in body.page_urls)
    account = _connected_account_id(supabase, user_id, record.provider) if record else None
    call = start_call(str(uuid.uuid4()), record, time.time(), connected_account_id=account)

    if body.client_capture_id:
        identity = reserve_capture(
            supabase,
            user_id=user_id,
            company_id=membership.company_id,
            client_capture_id=body.client_capture_id,
            started_at=body.started_at or datetime.now(timezone.utc),
            interaction_kind="call",
            resolved_version_id=live_version_id(supabase, membership.company_id, None),
            sales_role=membership.sales_role,
            hubspot_contact_id=call.contact_id if call.provider == "hubspot" else None,
        )
        call = attach_memo(call, identity.memo_id)

    live_call_hub.publish(user_id, call)
    return _state(call)


@router.patch("/current")
async def pick_live_call_contact(
    body: PickContactIn,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The rep corrected who the call is with (or picked one of a deal's contacts)."""
    user_id = membership.user_id
    call = live_call_hub.current(user_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No call")
    call = pick_contact(call, body.provider, body.contact_id)
    if call.memo_id and body.provider == "hubspot":
        supabase.table("memos").update({"hubspot_contact_id": body.contact_id}).eq(
            "id", call.memo_id
        ).eq("user_id", user_id).execute()
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
