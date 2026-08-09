"""
Process HubSpot call recordings into memos (transcribe via Speechmatics, pending_transcript).

Flow:
  1. initiate_hubspot_call_memo  — idempotent DB row, status=transcribing
  2. process_hubspot_call_background — download audio, submit to Speechmatics
     with a notification_url callback + speaker diarization enabled.
  3. /webhooks/speechmatics — receives the completed transcript, updates memo
     to pending_transcript. No polling loop needed.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from supabase import Client

from app.config import settings
from app.logging_config import log_domain, DOMAIN_MEMO
from app.metrics import record_transcription_duration
from app.services.hubspot.calls import download_recording, get_call_engagement
from app.services.hubspot.client import HubSpotClient
from app.services.speechmatics_batch import SpeechmaticsBatchService

from .calls import get_call_associations

logger = logging.getLogger(__name__)


def _duration_seconds(props: dict) -> float:
    raw = props.get("hs_call_duration")
    if raw is None or raw == "":
        return 0.0
    try:
        ms = float(str(raw).strip())
    except ValueError:
        return 0.0
    if ms > 10_000:
        return round(ms / 1000.0, 2)
    return float(ms)


async def initiate_hubspot_call_memo(
    supabase: Client,
    user_id: str,
    call_id: str,
    access_token: str,
) -> Tuple[Optional[str], bool]:
    """
    Idempotent memo row for a HubSpot call. Returns (memo_id, created_new).
    """
    cid = str(call_id)
    existing = (
        supabase.table("memos")
        .select("id")
        .eq("hubspot_engagement_id", cid)
        .limit(1)
        .execute()
    )
    if existing.data:
        return str(existing.data[0]["id"]), False

    client = HubSpotClient(access_token)
    deals, contacts = await get_call_associations(client, cid)
    d = deals[0] if deals else None
    ct = contacts[0] if contacts else None

    logger.info(
        "HubSpot call associations resolved",
        extra=log_domain(DOMAIN_MEMO, "hubspot_call_associations",
                         call_id=cid, deal_id=str(d), contact_id=str(ct)),
    )

    row = {
        "user_id": user_id,
        "audio_url": "",
        "audio_duration": 0.0,
        "status": "transcribing",
        "source": "hubspot_call",
        "hubspot_engagement_id": cid,
        "hubspot_deal_id": str(d) if d else None,
        "hubspot_contact_id": str(ct) if ct else None,
        "processing_started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ins = supabase.table("memos").insert(row).execute()
    except Exception as insert_exc:
        # Lost a race against a redelivered HubSpot webhook for the same
        # call_id (unique index from migration 009) - the other request
        # already created the memo, return it instead of failing.
        if "duplicate key" in str(insert_exc).lower() or "23505" in str(insert_exc):
            retry = (
                supabase.table("memos")
                .select("id")
                .eq("hubspot_engagement_id", cid)
                .limit(1)
                .execute()
            )
            if retry.data:
                return str(retry.data[0]["id"]), False
        raise
    if not ins.data:
        return None, False
    return str(ins.data[0]["id"]), True


async def process_hubspot_call_background(
    memo_id: str,
    user_id: str,
    access_token: str,
    call_id: str,
    supabase: Client,
) -> None:
    """
    Download recording and submit to Speechmatics with:
    - Speaker diarization (S1/S2 labels for rep vs prospect)
    - Push notification callback — no polling loop

    The memo stays in 'transcribing' status until /webhooks/speechmatics fires.
    """
    t0 = time.perf_counter()
    try:
        client = HubSpotClient(access_token)
        data = await get_call_engagement(client, str(call_id))
        if not data:
            raise RuntimeError("Call engagement not found")
        props = data.get("properties") or {}
        url = (props.get("hs_call_recording_url") or "").strip()
        if not url:
            raise RuntimeError("No recording URL on call")

        audio_bytes, content_type = await download_recording(url, access_token)
        dur = _duration_seconds(props)
        if dur <= 0:
            dur = max(1.0, len(audio_bytes) / (32 * 1024))

        supabase.table("memos").update({"audio_duration": dur}).eq("id", memo_id).execute()

        # Build the callback URL Speechmatics will POST the transcript to.
        # Speechmatics appends ?id=<job_id>&status=success|error automatically.
        notification_url = (
            f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/webhooks/speechmatics"
            f"?memo_id={memo_id}"
        )

        batch = SpeechmaticsBatchService()
        job_id = await batch.submit(
            audio_bytes=audio_bytes,
            content_type=content_type or "audio/mpeg",
            language="es",
            user_id=user_id,
            diarization=True,
            notification_url=notification_url,
        )
        record_transcription_duration(time.perf_counter() - t0, "hubspot_call_submit")

        # Persist job_id for traceability (requires migration 011)
        try:
            supabase.table("memos").update(
                {"speechmatics_job_id": job_id}
            ).eq("id", memo_id).execute()
        except Exception:
            pass  # Column may not exist yet; non-fatal

        logger.info(
            "HubSpot call submitted to Speechmatics",
            extra=log_domain(DOMAIN_MEMO, "hubspot_call_submitted",
                             memo_id=memo_id, call_id=call_id, job_id=job_id),
        )
    except Exception as e:
        logger.exception(
            "HubSpot call processing failed",
            extra=log_domain(DOMAIN_MEMO, "hubspot_call_failed", memo_id=memo_id, error=str(e)),
        )
        supabase.table("memos").update(
            {
                "status": "failed",
                "error_message": str(e)[:2000],
                "processing_started_at": None,
            }
        ).eq("id", memo_id).execute()
