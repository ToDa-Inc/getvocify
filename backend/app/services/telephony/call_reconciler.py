"""Brings back Twilio calls whose callbacks never arrived.

A call's memo comes from two places at hang-up: the desktop's live transcript and Twilio's recording
callback. If the API is down, deploying or too slow at that moment, both can be lost and the call stays
`dialing` forever, with its recording sitting at Twilio. This asks Twilio about every call still
`dialing` once its callbacks should have come, and runs exactly what the lost callback would have run:
the recording webhook's processing, or the missed-call log.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services.telephony.twilio_client import TelephonyNotConfigured, twilio_rest
from app.services.ttl_cache import TtlCache

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 120
# Younger calls may still be live or still have Twilio's own callbacks (and retries) on the way.
SETTLE = timedelta(minutes=3)
LOOK_BACK = timedelta(hours=24)
# A recording Twilio has not finished this long after the call ended is not coming.
RECORDING_GRACE = timedelta(minutes=30)
BATCH = 25

LIVE_STATUSES = {"queued", "ringing", "in-progress"}
MISSED_STATUSES = {"busy", "no-answer", "failed", "canceled"}

# Calls checked with nothing left to do, so Twilio is asked about each of them once, not every sweep.
_settled: TtlCache[bool] = TtlCache(LOOK_BACK.total_seconds())


def _stuck_calls(supabase, now: datetime) -> list[dict]:
    found = (
        supabase.table("outbound_calls")
        .select("carrier_call_id,user_id,call_disposition,created_at")
        .eq("status", "dialing")
        .eq("carrier", "twilio")
        .is_("recording_path", "null")
        .lt("created_at", (now - SETTLE).isoformat())
        .gt("created_at", (now - LOOK_BACK).isoformat())
        .order("created_at", desc=True)
        .limit(BATCH)
        .execute()
    )
    return found.data or []


def _twilio_view(call_sid: str) -> dict:
    """What Twilio knows about a call: its finished recording, or how it ended."""
    client = twilio_rest()
    for recording in client.recordings.list(call_sid=call_sid, limit=5):
        if recording.status == "completed":
            return {"recording": recording}
    parent = client.calls(call_sid).fetch()
    legs = client.calls.list(parent_call_sid=call_sid, limit=5)
    return {
        "recording": None,
        "status": parent.status,
        "ended_at": parent.end_time,
        "dial_status": legs[0].status if legs else "no-answer",
    }


def _recording_url(uri: str) -> str:
    path = uri[: -len(".json")] if uri.endswith(".json") else uri
    return f"https://api.twilio.com{path}"


async def reconcile_calls(supabase, *, now: Optional[datetime] = None) -> int:
    """One sweep. Returns how many calls it started recovering."""
    from app.api.webhooks import start_recording_job
    from app.services.telephony.call_processor import log_missed_call_activity

    now = now or datetime.now(timezone.utc)
    rows = await asyncio.to_thread(_stuck_calls, supabase, now)
    recovered = 0
    for row in rows:
        call_sid = row["carrier_call_id"]
        if _settled.get(call_sid):
            continue
        try:
            view = await asyncio.to_thread(_twilio_view, call_sid)
        except TelephonyNotConfigured:
            return recovered
        except Exception:
            logger.warning("Call reconcile: Twilio lookup failed for %s", call_sid, exc_info=True)
            continue

        recording = view["recording"]
        if recording is not None:
            started = start_recording_job(
                supabase,
                call_sid,
                _recording_url(recording.uri),
                recording_sid=recording.sid,
                duration=float(recording.duration or 0) or 1.0,
                started_at=recording.start_time,
            )
            if started:
                recovered += 1
                logger.warning(
                    "Call reconcile: %s never got its recording callback; processing it now",
                    call_sid,
                    extra={"domain": "telephony", "phase": "reconcile_recording"},
                )
            continue

        if view["status"] in LIVE_STATUSES:
            continue  # still on the phone
        if view["dial_status"] in MISSED_STATUSES:
            if not row.get("call_disposition"):
                logger.warning(
                    "Call reconcile: %s never got its dial-status callback; logging the missed call now",
                    call_sid,
                    extra={"domain": "telephony", "phase": "reconcile_missed"},
                )
                await log_missed_call_activity(supabase, call_sid, view["dial_status"])
                recovered += 1
            _settled.put(call_sid, True)
            continue
        ended_at = view.get("ended_at")
        if ended_at is None or now - ended_at > RECORDING_GRACE:
            logger.warning(
                "Call reconcile: %s ended answered but Twilio has no finished recording",
                call_sid,
                extra={"domain": "telephony", "phase": "reconcile_no_recording"},
            )
            _settled.put(call_sid, True)
    return recovered
