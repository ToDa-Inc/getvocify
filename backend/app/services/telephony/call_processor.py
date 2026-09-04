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
from urllib.parse import urlparse, urlunparse

import httpx
from supabase import Client

from app.config import settings
from app.logging_config import DOMAIN_MEMO, log_domain
from app.metrics import (
    record_download_duration,
    record_hubspot_log_duration,
    record_transcription_duration,
)
from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run, record_stage
from app.services.stt_batch import transcribe_bytes
from app.services.telephony.call_screening import classify_call_outcome
from app.services.transcript_sanitize import sanitize_user_transcript

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 60.0


def twilio_wav_url(recording_url: str) -> str:
    """Twilio serves WAV when the media extension is explicit.

    HubSpot only transcribes .WAV/.FLAC/.MP4, so MP3 is not an option.
    IE1 accounts reject media fetched from api.twilio.com (US1), so rewrite
    the default host when TWILIO_EDGE + TWILIO_REGION are set.
    """
    base = (recording_url or "").split("?", 1)[0].rstrip("/")
    if not base.endswith(".wav"):
        base = f"{base}.wav"
    edge = settings.TWILIO_EDGE
    region = settings.TWILIO_REGION
    if edge and region:
        parsed = urlparse(base)
        if parsed.netloc in ("api.twilio.com", "api.us1.twilio.com"):
            parsed = parsed._replace(netloc=f"api.{edge}.{region}.twilio.com")
            base = urlunparse(parsed)
    return base


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


async def attach_hubspot_contact_by_phone(
    supabase: Client,
    call_row: dict[str, Any],
) -> dict[str, Any]:
    """Fill hubspot_contact_id from a unique CRM phone match. Best-effort."""
    if call_row.get("hubspot_contact_id"):
        return call_row
    phone = (call_row.get("to_number") or "").strip()
    user_id = call_row.get("user_id")
    if not phone or not user_id:
        return call_row
    try:
        from app.api.crm import get_hubspot_client_from_connection
        from app.services.hubspot.search import (
            HubSpotSearchService,
            choose_dialed_contact,
        )

        client = get_hubspot_client_from_connection(user_id, supabase)
        hits = await HubSpotSearchService(client).find_contacts_by_phone(
            phone,
            limit=5,
            default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE,
        )
        chosen = choose_dialed_contact(hits, phone)
    except Exception as e:
        logger.warning(
            "HubSpot phone lookup skipped for %s: %s",
            call_row.get("twilio_call_sid"),
            e,
        )
        return call_row
    if not chosen:
        return call_row
    contact_id = str(chosen.id)
    supabase.table("outbound_calls").update(
        {"hubspot_contact_id": contact_id}
    ).eq("twilio_call_sid", call_row["twilio_call_sid"]).execute()
    call_row["hubspot_contact_id"] = contact_id
    return call_row


async def process_vocify_call_background(
    memo_id: str,
    user_id: str,
    call_sid: str,
    audio_bytes: bytes,
    duration: float,
    supabase: Client,
    *,
    pre_stages: Optional[list] = None,
    pipeline_started_at: Optional[float] = None,
) -> None:
    """Transcribe the stored recording and hand off to CRM extraction."""
    t0 = time.perf_counter()
    stages: list = []  # rebound by `with pipeline_run() as stages` below;
    # kept here so the except block always has a list to persist even if
    # something fails before that line runs.
    screening_outcome = "connected"
    try:
        # Single pipeline_run() context for the whole call: record_stage()
        # writes to a contextvar buffer that only exists while this `with`
        # block is open, so hubspot_log/total_pipeline must be recorded
        # *inside* it too, not after it exits.
        with pipeline_run() as stages:
            stages.extend(pre_stages or [])
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

            screening_outcome = classify_call_outcome(cleaned, duration)
            supabase.table("outbound_calls").update(
                {"call_disposition": screening_outcome}
            ).eq("twilio_call_sid", call_sid).execute()

            from app.api.memos import start_extraction_from_transcript

            if screening_outcome == "connected":
                await start_extraction_from_transcript(
                    memo_id,
                    user_id,
                    cleaned,
                    supabase,
                    source_type="vocify_call",
                    extra_update={
                        "audio_duration": duration,
                        "error_message": None,
                        "screening_outcome": screening_outcome,
                    },
                )
            else:
                await finalize_screened_out_memo(
                    supabase,
                    memo_id,
                    cleaned,
                    duration,
                    screening_outcome,
                    call_sid,
                )

            t_hs = time.perf_counter()
            await log_call_engagement(
                supabase,
                call_sid,
                duration,
                screening_outcome=screening_outcome,
            )
            record_stage("hubspot_log", t_hs)
            if pipeline_started_at is not None:
                record_stage("total_pipeline", pipeline_started_at)

        persist_pipeline_meta(supabase, memo_id, stages)
        logger.info(
            "Vocify call transcribed",
            extra=log_domain(
                DOMAIN_MEMO,
                "vocify_call_transcribed",
                memo_id=memo_id,
                call_sid=call_sid,
                transcript_len=len(cleaned),
                screening_outcome=screening_outcome,
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
        if pipeline_started_at is not None:
            # The `with pipeline_run()` block above has already unwound its
            # contextvar by the time we get here (on any exit, including via
            # exception), so record_stage() would silently no-op. Open a
            # throwaway context just to build the dict in the same shape,
            # then append it to the `stages` list we already hold a
            # reference to (mutating the with-block's buffer directly).
            with pipeline_run() as scratch:
                record_stage("total_pipeline", pipeline_started_at, error=str(e)[:200])
            stages.extend(scratch)
        persist_pipeline_meta(supabase, memo_id, stages)


async def finalize_screened_out_memo(
    supabase: Client,
    memo_id: str,
    transcript: str,
    duration: float,
    outcome: str,
    call_sid: str,
) -> None:
    """Persist transcript without running LLM extraction."""
    summaries = {
        "voicemail": "Buzon de voz detectado; extraccion omitida.",
        "no_response": "Sin conversacion real detectada; extraccion omitida.",
    }
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("memos").update(
        {
            "status": "pending_review",
            "transcript": transcript,
            "screening_outcome": outcome,
            "audio_duration": duration,
            "extraction": {
                "summary": summaries.get(outcome, "Extraccion omitida."),
                "confidence": {"overall": 0.0, "fields": {}},
            },
            "processed_at": now,
            "processing_started_at": None,
            "error_message": None,
        }
    ).eq("id", memo_id).execute()
    supabase.table("outbound_calls").update(
        {"call_disposition": outcome}
    ).eq("twilio_call_sid", call_sid).execute()


async def log_missed_call_activity(
    supabase: Client,
    call_sid: str,
    dial_call_status: str,
) -> None:
    """Log busy/no-answer/failed/canceled calls to HubSpot without a memo."""
    from app.api.crm import get_hubspot_client_from_connection
    from app.services.hubspot.call_log import (
        build_call_properties,
        hubspot_call_body_for_disposition,
        hubspot_call_status_for_disposition,
        log_call_to_hubspot,
        normalize_twilio_dial_status,
    )

    disposition = normalize_twilio_dial_status(dial_call_status)
    t0 = time.perf_counter()
    try:
        found = (
            supabase.table("outbound_calls")
            .select("*")
            .eq("twilio_call_sid", call_sid)
            .limit(1)
            .execute()
        )
        row = (found.data or [None])[0]
        if not row:
            return
        if row.get("hubspot_engagement_id") or row.get("memo_id"):
            return
        if row.get("call_disposition") in (
            "busy",
            "no_answer",
            "failed",
            "canceled",
            "connected",
            "voicemail",
            "no_response",
        ):
            return

        row = await attach_hubspot_contact_by_phone(supabase, row)
        if not row.get("hubspot_contact_id"):
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
                "HubSpot missed-call logging skipped for %s: no portal_id",
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
            duration_ms=0,
            external_id=call_sid,
            external_account_id=hubspot_hub_id,
            app_id=str(settings.HUBSPOT_APP_ID or ""),
            owner_id=None,
            title="Llamada Vocify",
            body=hubspot_call_body_for_disposition(disposition),
            call_status=hubspot_call_status_for_disposition(disposition),
        )
        engagement_id = await log_call_to_hubspot(
            client,
            properties=properties,
            contact_id=row.get("hubspot_contact_id"),
            deal_id=row.get("hubspot_deal_id"),
        )
        supabase.table("outbound_calls").update(
            {
                "hubspot_engagement_id": engagement_id,
                "status": "logged",
                "call_disposition": disposition,
            }
        ).eq("twilio_call_sid", call_sid).execute()
    except Exception as e:
        logger.warning(
            "HubSpot missed-call logging failed for %s: %s", call_sid, e
        )
    finally:
        record_hubspot_log_duration(time.perf_counter() - t0)


async def log_call_engagement(
    supabase: Client,
    call_sid: str,
    duration: float,
    *,
    screening_outcome: str = "connected",
) -> None:
    """Create the HubSpot engagement and tell HubSpot the recording is ready.

    Best-effort: a HubSpot failure must not fail the memo, which is already
    reviewable in Vocify.
    """
    from app.api.crm import get_hubspot_client_from_connection
    from app.services.hubspot.call_log import (
        build_call_properties,
        hubspot_call_body_for_disposition,
        hubspot_call_status_for_disposition,
        log_call_to_hubspot,
        mark_recording_ready,
    )

    t0 = time.perf_counter()
    try:
        found = (
            supabase.table("outbound_calls")
            .select("*")
            .eq("twilio_call_sid", call_sid)
            .limit(1)
            .execute()
        )
        row = (found.data or [None])[0]
        if not row:
            return
        if row.get("hubspot_engagement_id"):
            return
        row = await attach_hubspot_contact_by_phone(supabase, row)
        if not row.get("hubspot_contact_id"):
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
            body=hubspot_call_body_for_disposition(screening_outcome),
            call_status=hubspot_call_status_for_disposition(screening_outcome),
        )
        engagement_id = await log_call_to_hubspot(
            client,
            properties=properties,
            contact_id=row.get("hubspot_contact_id"),
            deal_id=row.get("hubspot_deal_id"),
        )
        await mark_recording_ready(client, engagement_id)
        supabase.table("outbound_calls").update(
            {
                "hubspot_engagement_id": engagement_id,
                "status": "logged",
                "call_disposition": screening_outcome,
            }
        ).eq("twilio_call_sid", call_sid).execute()
    except Exception as e:
        logger.warning("HubSpot call logging failed for %s: %s", call_sid, e)
    finally:
        record_hubspot_log_duration(time.perf_counter() - t0)
