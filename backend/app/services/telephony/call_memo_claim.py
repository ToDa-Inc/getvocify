"""One memo per Vocify call.

A call placed from the desktop app has two ways to its memo: the live transcript the app
uploads at hang-up (seconds), and Twilio's recording (tens of seconds later). Whichever
memo is written first claims the call; the other is removed and the caller uses the winner.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from supabase import Client

# How long the recording waits for the live transcript's memo when the rep was transcribing live.
LIVE_MEMO_GRACE_S = 15.0
LIVE_MEMO_POLL_S = 0.5


def find_user_call(supabase: Client, user_id: str, call_sid: str) -> Optional[dict[str, Any]]:
    """The rep's own outbound call by its Twilio CallSid, or None."""
    found = (
        supabase.table("outbound_calls")
        .select("*")
        .eq("carrier_call_id", call_sid)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return (found.data or [None])[0]


def claim_call_memo(supabase: Client, call_sid: str, memo_id: str) -> Optional[str]:
    """Links `memo_id` to the call unless another memo got there first.

    Returns the call's memo: `memo_id` when it won, else the one that did (and `memo_id`
    is deleted, so the call never has two memos).
    """
    won = (
        supabase.table("outbound_calls")
        .update({"memo_id": memo_id})
        .eq("carrier_call_id", call_sid)
        .is_("memo_id", "null")
        .execute()
    )
    if won.data:
        return memo_id
    current = (
        supabase.table("outbound_calls")
        .select("memo_id")
        .eq("carrier_call_id", call_sid)
        .limit(1)
        .execute()
    )
    winner = ((current.data or [None])[0] or {}).get("memo_id")
    if winner and str(winner) != str(memo_id):
        supabase.table("memos").delete().eq("id", memo_id).execute()
    return str(winner) if winner else None


async def wait_for_live_memo(
    supabase: Client,
    call_sid: str,
    *,
    grace_s: float = LIVE_MEMO_GRACE_S,
    poll_s: float = LIVE_MEMO_POLL_S,
) -> Optional[str]:
    """The call's memo once the desktop's live transcript makes it, or None if it doesn't within `grace_s`.

    The recording is the fallback for a call with no live transcript; when there is one, transcribing
    the audio again would only repeat it.
    """
    deadline = time.monotonic() + grace_s
    while True:
        found = await asyncio.to_thread(
            lambda: supabase.table("outbound_calls")
            .select("memo_id")
            .eq("carrier_call_id", call_sid)
            .limit(1)
            .execute()
        )
        memo_id = ((found.data or [None])[0] or {}).get("memo_id")
        if memo_id:
            return str(memo_id)
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(poll_s)
