"""
Process HubSpot call recordings into memos (Deepgram Nova-3 batch, auto-extract).

Flow:
  1. initiate_hubspot_call_memo  — idempotent DB row, status=transcribing
  2. process_hubspot_call_background — download audio, transcribe (sync listen),
     cheap name/speaker repair, start CRM extraction. LLM transcript polish runs
     in the background and does not block review.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from supabase import Client

from app.logging_config import log_domain, DOMAIN_MEMO
from app.metrics import record_transcription_duration
from app.services.hubspot.calls import (
    call_duration_seconds,
    download_recording,
    get_call_associations,
    get_call_engagement,
    parse_hubspot_timestamp_ms,
)
from app.services.hubspot.client import HubSpotClient
from app.services.session_entities import build_page_terms
from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run
from app.services.stt_batch import transcribe_bytes
from app.services.transcript_sanitize import sanitize_user_transcript

logger = logging.getLogger(__name__)


async def _contact_terms_for_call(client: HubSpotClient, contact_id: Optional[str]):
    if not contact_id:
        return []
    try:
        data = await client.get(
            f"/crm/v3/objects/contacts/{contact_id}",
            params={"properties": "firstname,lastname,company"},
        )
        props = (data or {}).get("properties") or {}
        return build_page_terms(
            first_name=props.get("firstname"),
            last_name=props.get("lastname"),
            company_name=props.get("company"),
        )
    except Exception as e:
        logger.warning("HubSpot call vocab: contact %s lookup failed: %s", contact_id, e)
        return []


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
        .eq("user_id", user_id)
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
                .eq("user_id", user_id)
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
    """Download recording, transcribe with Deepgram, sanitize, start extraction."""
    from app.services.pipeline_lease import (
        acquire_pipeline_run,
        release_pipeline_run,
        run_record,
        update_memo_row,
    )
    from app.services.pipeline_meta import record_stage
    from app.services.transcript_sanitize import raw_speaker_count

    t0 = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    stages: list = []
    run_id = acquire_pipeline_run(supabase, memo_id, "hubspot_process")
    if not run_id:
        logger.info(
            "HubSpot call skipped — lease held",
            extra=log_domain(DOMAIN_MEMO, "hubspot_call_lease_held", memo_id=memo_id, call_id=call_id),
        )
        return
    outcome = "ok"
    try:
        client = HubSpotClient(access_token)
        data = await get_call_engagement(client, str(call_id))
        if not data:
            raise RuntimeError("Call engagement not found")
        props = data.get("properties") or {}
        url = (props.get("hs_call_recording_url") or "").strip()
        if not url:
            raise RuntimeError("No recording URL on call")

        t_dl = time.perf_counter()
        audio_bytes, content_type = await download_recording(url, access_token)
        dur = call_duration_seconds(props)
        if dur <= 0:
            dur = max(1.0, len(audio_bytes) / (32 * 1024))
        ts_ms = parse_hubspot_timestamp_ms(props.get("hs_timestamp") or props.get("hs_createdate"))
        call_date = None
        if ts_ms:
            call_date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()

        extra_terms = []
        try:
            _deals, contacts = await get_call_associations(client, str(call_id))
            extra_terms = await _contact_terms_for_call(client, contacts[0] if contacts else None)
        except Exception as e:
            logger.warning("HubSpot call vocab: associations failed: %s", e)

        with pipeline_run(run_id=run_id, trigger="hubspot_process") as stages:
            record_stage("download", t_dl, bytes=len(audio_bytes))
            transcript = await transcribe_bytes(
                audio_bytes,
                content_type=content_type or "audio/mpeg",
                user_id=user_id,
                extra_terms=extra_terms,
                diarization=True,
            )
            memo_row = (
                supabase.table("memos")
                .select("id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id,source,source_type")
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            memo_data = (memo_row.data or [None])[0] or {
                "id": memo_id,
                "user_id": user_id,
                "source": "hubspot_call",
            }
            memo_data.setdefault("source", "hubspot_call")
            cleaned = await sanitize_user_transcript(
                transcript, user_id, supabase, memo_data=memo_data
            )
        record_transcription_duration(time.perf_counter() - t0, "hubspot_call")
        persist_pipeline_meta(supabase, memo_id, stages)

        from app.api.memos import start_extraction_from_transcript

        await start_extraction_from_transcript(
            memo_id,
            user_id,
            cleaned,
            supabase,
            source_type="hubspot_call",
            run_id=run_id,
            call_date=call_date,
            trigger="hubspot_process",
            extra_update={
                "audio_duration": dur,
                "error_message": None,
                "transcript_raw": transcript,
                "transcript_stt_meta": {
                    "provider": "deepgram",
                    "model": "nova-3",
                    "raw_speaker_count": raw_speaker_count(transcript),
                    "call_date": call_date,
                    "diarized": True,
                },
            },
        )

        persist_pipeline_meta(
            supabase,
            memo_id,
            [],
            run=run_record(run_id, "hubspot_process", started_at, t0, "ok"),
        )
        logger.info(
            "HubSpot call transcribed (extraction started)",
            extra=log_domain(
                DOMAIN_MEMO,
                "hubspot_call_transcribed",
                memo_id=memo_id,
                call_id=call_id,
                transcript_len=len(cleaned),
            ),
        )
    except Exception as e:
        outcome = "failed"
        logger.exception(
            "HubSpot call processing failed",
            extra=log_domain(DOMAIN_MEMO, "hubspot_call_failed", memo_id=memo_id, error=str(e)),
        )
        update_memo_row(
            supabase,
            memo_id,
            {
                "status": "failed",
                "error_message": str(e)[:2000],
                "processing_started_at": None,
            },
        )
        persist_pipeline_meta(
            supabase,
            memo_id,
            stages,
            run=run_record(run_id, "hubspot_process", started_at, t0, outcome),
        )
    finally:
        release_pipeline_run(supabase, memo_id, run_id)
