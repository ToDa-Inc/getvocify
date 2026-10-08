"""One HubSpot entry per call placed through Vocify.

The Call engagement (logged when Twilio's recording arrives, with HubSpot's own recording player)
carries the write-up the approve step would otherwise put in a separate Note: summary, what was
updated, transcript. The rep can approve before the call is logged; the write-up then waits in
its crm_updates row and `log_call_engagement` creates the Call with it.
"""

from __future__ import annotations

from typing import Any, Optional

from supabase import Client

from app.services.hubspot.call_log import CALLS_OBJECT_PATH

CALL_BODY_ACTION = "call_body"


def placed_call_for_memo(supabase: Client, memo_id: str) -> Optional[dict[str, Any]]:
    """The Vocify-placed call this memo is about, if it is one."""
    found = (
        supabase.table("outbound_calls")
        .select("carrier_call_id,hubspot_engagement_id")
        .eq("memo_id", str(memo_id))
        .limit(1)
        .execute()
    )
    return (found.data or [None])[0]


async def write_call_body(client: Any, engagement_id: str, body: str) -> None:
    await client.patch(f"{CALLS_OBJECT_PATH}/{engagement_id}", data={"properties": {"hs_call_body": body}})


def pending_call_body(supabase: Client, memo_id: Optional[str]) -> Optional[tuple[str, str]]:
    """(crm_updates id, body) of a write-up approved before its call was logged."""
    if not memo_id:
        return None
    found = (
        supabase.table("crm_updates")
        .select("id,data")
        .eq("memo_id", str(memo_id))
        .eq("action_type", CALL_BODY_ACTION)
        .eq("status", "success")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    row = (found.data or [None])[0] or {}
    data = row.get("data") or {}
    if data.get("pending") and data.get("body"):
        return str(row["id"]), str(data["body"])
    return None


def mark_call_body_written(supabase: Client, update_id: str, engagement_id: str) -> None:
    found = supabase.table("crm_updates").select("data").eq("id", update_id).limit(1).execute()
    data = dict(((found.data or [None])[0] or {}).get("data") or {})
    data.pop("body", None)
    data.update({"engagement_id": str(engagement_id), "pending": False})
    supabase.table("crm_updates").update({"data": data, "resource_id": str(engagement_id)}).eq("id", update_id).execute()


async def write_to_placed_call(
    *,
    supabase: Client,
    client: Any,
    crm_updates: Any,
    memo_id: str,
    user_id: str,
    connection_id: str,
    body: str,
    extra_data: Optional[dict[str, Any]] = None,
) -> bool:
    """Put the write-up on the memo's call. False when the memo is not a Vocify-placed call (it keeps its Note)."""
    call = placed_call_for_memo(supabase, memo_id)
    if not call:
        return False
    async with crm_updates.track(
        memo_id=str(memo_id),
        user_id=user_id,
        crm_connection_id=str(connection_id),
        action_type=CALL_BODY_ACTION,
        resource_type="call",
    ) as tracked:
        engagement_id = call.get("hubspot_engagement_id")
        if engagement_id:
            await write_call_body(client, str(engagement_id), body)
            tracked.data = {"engagement_id": str(engagement_id), "pending": False, **(extra_data or {})}
            tracked.resource_id = str(engagement_id)
        else:
            tracked.data = {"body": body, "pending": True, **(extra_data or {})}
    if not engagement_id:
        # The call may have been logged while this was being saved, after it had looked for the write-up.
        logged = (placed_call_for_memo(supabase, memo_id) or {}).get("hubspot_engagement_id")
        pending = pending_call_body(supabase, memo_id)
        if logged and pending:
            await write_call_body(client, str(logged), pending[1])
            mark_call_body_written(supabase, pending[0], str(logged))
    return True
