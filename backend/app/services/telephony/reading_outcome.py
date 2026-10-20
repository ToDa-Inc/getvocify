"""A call the transcript screening let through, which reading the call then showed nobody answered.

Screening is rules over the transcript; reading the call is the model's judgment, and it catches a
voicemail the rules missed. The reading wins: the memo becomes a voicemail / no-response one, the call
is a "No answer" in Vocify, and HubSpot's call is marked No answer, whether it was logged already or not yet.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from supabase import Client

from app.services.telephony.call_screening import looks_like_voicemail

logger = logging.getLogger(__name__)

_CALL_SOURCES = frozenset({"vocify_call", "hubspot_call"})
_REASON_VOICEMAIL = re.compile(r"buz[oó]n|voice ?mail|contestador|mailbox", re.IGNORECASE)


def unanswered_outcome(call_reading: Optional[dict], transcript: str) -> Optional[str]:
    """"voicemail" or "no_response" when the reading says nobody talked with the rep; None otherwise."""
    if not call_reading or call_reading.get("call_type") != "no_conversation":
        return None
    reason = str(call_reading.get("call_type_reason") or "")
    return "voicemail" if looks_like_voicemail(transcript) or _REASON_VOICEMAIL.search(reason) else "no_response"


async def apply_reading_outcome(supabase: Client, memo_id: str, call_reading: Optional[dict]) -> Optional[str]:
    """Record the reading's no-answer verdict. Returns the outcome applied, None when nothing changed. Never raises."""
    try:
        found = (
            supabase.table("memos")
            .select("user_id,source,interaction_kind,screening_outcome,transcript")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
        memo: dict[str, Any] = (found.data or [None])[0] or {}
        # A call, whoever placed it: Vocify's dialer, HubSpot's, or a phone the island recorded (a "web" memo of kind call).
        is_call = memo.get("source") in _CALL_SOURCES or memo.get("interaction_kind") == "call"
        if not is_call or memo.get("screening_outcome") not in (None, "", "connected"):
            return None
        outcome = unanswered_outcome(call_reading, str(memo.get("transcript") or ""))
        if not outcome:
            return None
        supabase.table("memos").update({"screening_outcome": outcome}).eq("id", memo_id).execute()
        calls = (
            supabase.table("outbound_calls")
            .update({"call_disposition": outcome})
            .eq("memo_id", memo_id)
            .execute()
        )
        for call in calls.data or []:
            if call.get("hubspot_engagement_id"):
                await _mark_hubspot_call(supabase, memo["user_id"], str(call["hubspot_engagement_id"]), outcome)
        return outcome
    except Exception:
        logger.exception("Could not apply the call reading's no-answer outcome to memo %s", memo_id)
        return None


async def _mark_hubspot_call(supabase: Client, user_id: str, engagement_id: str, outcome: str) -> None:
    """A call already logged as completed becomes No answer. One not logged yet reads the memo's outcome when it is."""
    from app.api.crm import get_hubspot_client_from_connection
    from app.services.hubspot.call_log import (
        CALLS_OBJECT_PATH,
        hubspot_call_disposition_guid,
        hubspot_call_status_for_disposition,
    )

    client = get_hubspot_client_from_connection(user_id, supabase)
    properties = {"hs_call_status": hubspot_call_status_for_disposition(outcome)}
    guid = hubspot_call_disposition_guid(outcome)
    if guid:
        properties["hs_call_disposition"] = guid
    await client.patch(f"{CALLS_OBJECT_PATH}/{engagement_id}", data={"properties": properties})
