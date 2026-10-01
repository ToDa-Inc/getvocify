"""Live call awareness API.

The Chrome extension reports the CRM record the rep has open. When the rep's
desktop app starts a call, the contact is the record they were on, and the
desktop capture memo is reserved with it so extraction, the review target and
live help all know who the call is with. Clients follow changes on a per-user
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
from pydantic import BaseModel, Field, model_validator
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.captures import reserve_capture
from app.services.company import Membership
from app.services.company_scope import get_crm_connection
from app.services.live_calls.hub import LiveCallHub, live_call_hub
from app.services.live_calls.state import (
    RecordPresence,
    attach_memo,
    end_call,
    pick_contact,
    start_call,
)
from app.services.playbooks.live import live_version_id

router = APIRouter(prefix="/api/v1/live-calls", tags=["live-calls"])

HEARTBEAT_SECONDS = 15.0
_RECORD_ID = r"^\d{1,32}$"
_ACCOUNT_KEY = {"hubspot": "portal_id", "pipedrive": "company_domain"}


class PresenceIn(BaseModel):
    provider: Literal["hubspot", "pipedrive"]
    # Both absent: the rep is in the CRM but not on a record.
    object_type: Optional[Literal["contact", "company", "deal"]] = None
    record_id: Optional[str] = Field(default=None, pattern=_RECORD_ID)
    account_id: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _record_is_whole(self) -> "PresenceIn":
        if (self.object_type is None) != (self.record_id is None):
            raise ValueError("object_type and record_id go together")
        return self


class StartCallIn(BaseModel):
    # When set, the desktop capture memo is reserved for this call with its contact.
    client_capture_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    started_at: Optional[datetime] = None


class PickContactIn(BaseModel):
    provider: Literal["hubspot", "pipedrive"]
    contact_id: str = Field(..., pattern=_RECORD_ID)


def _connected_account_id(supabase: Client, user_id: str, provider: str) -> Optional[str]:
    """The account (HubSpot portal, Pipedrive domain) the rep's company connected, if known."""
    try:
        connection = get_crm_connection(supabase, user_id, provider)
    except Exception:
        return None
    value = ((connection or {}).get("metadata") or {}).get(_ACCOUNT_KEY[provider])
    return str(value) if value else None


def _set_memo_contact(supabase: Client, user_id: str, memo_id: str, contact_id: str) -> None:
    supabase.table("memos").update({"hubspot_contact_id": contact_id}).eq("id", memo_id).eq(
        "user_id", user_id
    ).execute()


@router.put("/presence")
async def report_presence(body: PresenceIn, membership: Membership = Depends(get_membership)):
    """The extension: where the rep is in the CRM (a record, or a page that is not one)."""
    live_call_hub.set_presence(
        membership.user_id,
        RecordPresence(
            provider=body.provider,
            object_type=body.object_type,
            record_id=body.record_id,
            account_id=body.account_id,
            seen_at=time.time(),
        ),
    )
    return {"ok": True}


@router.get("/current")
async def current_live_state(membership: Membership = Depends(get_membership)):
    return live_call_hub.state(membership.user_id).to_dict()


@router.post("/start")
async def start_live_call(
    body: StartCallIn,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The desktop: a call started. Returns the call with the contact the rep had open.

    Idempotent while a call is live, so a retried start never opens a second call.
    """
    user_id = membership.user_id
    current = live_call_hub.state(user_id)
    if current.call and current.call.is_live:
        return current.to_dict()

    presence = current.presence
    account = _connected_account_id(supabase, user_id, presence.provider) if presence else None
    call = start_call(str(uuid.uuid4()), presence, time.time(), connected_account_id=account)

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

    live_call_hub.set_call(user_id, call)
    return live_call_hub.state(user_id).to_dict()


@router.patch("/current")
async def pick_live_call_contact(
    body: PickContactIn,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The rep corrected who the call is with (or picked one of a deal's contacts)."""
    user_id = membership.user_id
    call = live_call_hub.state(user_id).call
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No call")
    call = pick_contact(call, body.provider, body.contact_id)
    if call.memo_id and body.provider == "hubspot":
        _set_memo_contact(supabase, user_id, call.memo_id, body.contact_id)
    live_call_hub.set_call(user_id, call)
    return live_call_hub.state(user_id).to_dict()


@router.post("/current/end")
async def end_live_call(membership: Membership = Depends(get_membership)):
    """The desktop: the call is over. The capture itself completes via /captures."""
    user_id = membership.user_id
    call = live_call_hub.state(user_id).call
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No call")
    live_call_hub.set_call(user_id, end_call(call, time.time()))
    return live_call_hub.state(user_id).to_dict()


def _sse(kind: str, state: dict) -> str:
    return f"data: {json.dumps({'type': kind, **state}, ensure_ascii=False)}\n\n"


async def live_call_stream(
    hub: LiveCallHub,
    user_id: str,
    *,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Snapshot first, then every change. Subscribes before the snapshot so
    nothing published in between is lost."""
    async with hub.subscribe(user_id) as queue:
        yield _sse("snapshot", hub.state(user_id).to_dict())
        while True:
            try:
                state = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _sse("update", state.to_dict())


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
