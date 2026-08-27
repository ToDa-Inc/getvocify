"""Turn a finished Twilio call into a Vocify memo.

Mirrors `app/services/hubspot/call_processor.py` deliberately: same statuses,
same STT entry point, same extraction handoff. The difference is provenance —
here Vocify placed the call and owns the audio, so the recording is persisted
(HubSpot will ask us for it later) instead of being discarded after STT.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import httpx
from supabase import Client

from app.config import settings
from app.logging_config import DOMAIN_MEMO, log_domain
from app.metrics import record_transcription_duration
from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run
from app.services.stt_batch import transcribe_bytes
from app.services.transcript_sanitize import sanitize_user_transcript

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 60.0


def twilio_wav_url(recording_url: str) -> str:
    """Twilio serves WAV when the media extension is explicit.

    HubSpot only transcribes .WAV/.FLAC/.MP4, so MP3 is not an option.
    """
    base = (recording_url or "").split("?", 1)[0].rstrip("/")
    if base.endswith(".wav"):
        return base
    return f"{base}.wav"


async def download_twilio_recording(recording_url: str) -> bytes:
    """Twilio recording media requires HTTP basic auth."""
    auth = (
        settings.TWILIO_API_KEY_SID or "",
        settings.TWILIO_API_KEY_SECRET or "",
    )
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, auth=auth) as client:
        response = await client.get(twilio_wav_url(recording_url))
        response.raise_for_status()
        return response.content


async def initiate_vocify_call_memo(
    supabase: Client,
    call_row: dict[str, Any],
) -> Tuple[Optional[str], bool]:
    """Idempotent memo row for a Vocify-placed call. Returns (memo_id, created)."""
    existing_memo_id = call_row.get("memo_id")
    if existing_memo_id:
        return str(existing_memo_id), False

    row = {
        "user_id": call_row["user_id"],
        "audio_url": "",
        "audio_duration": float(call_row.get("recording_duration") or 0.0),
        "status": "transcribing",
        "source": "vocify_call",
        "hubspot_contact_id": call_row.get("hubspot_contact_id"),
        "hubspot_deal_id": call_row.get("hubspot_deal_id"),
        "processing_started_at": datetime.now(timezone.utc).isoformat(),
    }
    ins = supabase.table("memos").insert(row).execute()
    if not ins.data:
        return None, False

    memo_id = str(ins.data[0]["id"])
    supabase.table("outbound_calls").update(
        {"memo_id": memo_id, "status": "recorded"}
    ).eq("twilio_call_sid", call_row["twilio_call_sid"]).execute()
    return memo_id, True


async def process_vocify_call_background(
    memo_id: str,
    user_id: str,
    call_sid: str,
    audio_bytes: bytes,
    duration: float,
    supabase: Client,
) -> None:
    """Transcribe the stored recording and hand off to CRM extraction."""
    t0 = time.perf_counter()
    stages: list = []
    try:
        with pipeline_run() as stages:
            transcript = await transcribe_bytes(
                audio_bytes,
                content_type="audio/wav",
                user_id=user_id,
                diarization=True,
            )
            memo_row = (
                supabase.table("memos")
                .select("id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id")
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            memo_data = (memo_row.data or [None])[0] or {
                "id": memo_id,
                "user_id": user_id,
            }
            cleaned = await sanitize_user_transcript(
                transcript, user_id, supabase, memo_data=memo_data
            )
        record_transcription_duration(time.perf_counter() - t0, "vocify_call")
        persist_pipeline_meta(supabase, memo_id, stages)

        from app.api.memos import start_extraction_from_transcript

        await start_extraction_from_transcript(
            memo_id,
            user_id,
            cleaned,
            supabase,
            source_type="vocify_call",
            extra_update={"audio_duration": duration, "error_message": None},
        )
        await log_call_engagement(supabase, call_sid, duration)
        logger.info(
            "Vocify call transcribed (extraction started)",
            extra=log_domain(
                DOMAIN_MEMO,
                "vocify_call_transcribed",
                memo_id=memo_id,
                call_sid=call_sid,
                transcript_len=len(cleaned),
            ),
        )
    except Exception as e:
        logger.exception(
            "Vocify call processing failed",
            extra=log_domain(
                DOMAIN_MEMO, "vocify_call_failed", memo_id=memo_id, error=str(e)
            ),
        )
        supabase.table("memos").update(
            {
                "status": "failed",
                "error_message": str(e)[:2000],
                "processing_started_at": None,
            }
        ).eq("id", memo_id).execute()
        supabase.table("outbound_calls").update(
            {"status": "failed", "error_message": str(e)[:2000]}
        ).eq("twilio_call_sid", call_sid).execute()
        persist_pipeline_meta(supabase, memo_id, stages)


async def log_call_engagement(
    supabase: Client,
    call_sid: str,
    duration: float,
) -> None:
    """Create the HubSpot engagement and tell HubSpot the recording is ready.

    Best-effort: a HubSpot failure must not fail the memo, which is already
    reviewable in Vocify.
    """
    from app.api.crm import get_hubspot_client_from_connection
    from app.services.hubspot.call_log import (
        build_call_properties,
        log_call_to_hubspot,
        mark_recording_ready,
    )

    try:
        found = (
            supabase.table("outbound_calls")
            .select("*")
            .eq("twilio_call_sid", call_sid)
            .limit(1)
            .execute()
        )
        row = (found.data or [None])[0]
        if not row or not row.get("hubspot_contact_id"):
            return

        conn = (
            supabase.table("crm_connections")
            .select("metadata")
            .eq("user_id", row["user_id"])
            .eq("provider", "hubspot")
            .limit(1)
            .execute()
        )
        conn_row = (conn.data or [None])[0]
        metadata = (conn_row or {}).get("metadata") or {}
        portal_id = metadata.get("portal_id")
        if not portal_id:
            logger.warning(
                "HubSpot call logging skipped for %s: no portal_id in connection metadata",
                call_sid,
            )
            return

        hubspot_hub_id = str(portal_id)
        supabase.table("outbound_calls").update(
            {"hubspot_hub_id": hubspot_hub_id}
        ).eq("twilio_call_sid", call_sid).execute()

        client = get_hubspot_client_from_connection(row["user_id"], supabase)
        properties = build_call_properties(
            occurred_at=datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            to_number=row["to_number"],
            from_number=row["from_number"],
            duration_ms=int(duration * 1000),
            external_id=call_sid,
            external_account_id=hubspot_hub_id,
            app_id=str(settings.HUBSPOT_APP_ID or ""),
            owner_id=None,
            title="Llamada Vocify",
            body="Transcripcion y extraccion disponibles en Vocify.",
        )
        engagement_id = await log_call_to_hubspot(
            client,
            properties=properties,
            contact_id=row.get("hubspot_contact_id"),
            deal_id=row.get("hubspot_deal_id"),
        )
        await mark_recording_ready(client, engagement_id)
        supabase.table("outbound_calls").update(
            {"hubspot_engagement_id": engagement_id, "status": "logged"}
        ).eq("twilio_call_sid", call_sid).execute()
    except Exception as e:
        logger.warning("HubSpot call logging failed for %s: %s", call_sid, e)
