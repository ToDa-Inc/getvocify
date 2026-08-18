"""
Process HubSpot call recordings into memos (Deepgram Nova-3 batch, pending_transcript).

Flow:
  1. initiate_hubspot_call_memo  — idempotent DB row, status=transcribing
  2. process_hubspot_call_background — download audio, transcribe (sync listen),
     sanitize, then pending_transcript. No Speechmatics webhook.
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
    """Download recording, transcribe with Deepgram, sanitize, pending_transcript."""
    t0 = time.perf_counter()
    stages: list = []
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
        dur = call_duration_seconds(props)
        if dur <= 0:
            dur = max(1.0, len(audio_bytes) / (32 * 1024))

        extra_terms = []
        try:
            _deals, contacts = await get_call_associations(client, str(call_id))
            extra_terms = await _contact_terms_for_call(client, contacts[0] if contacts else None)
        except Exception as e:
            logger.warning("HubSpot call vocab: associations failed: %s", e)

        with pipeline_run() as stages:
            transcript = await transcribe_bytes(
                audio_bytes,
                content_type=content_type or "audio/mpeg",
                user_id=user_id,
                extra_terms=extra_terms,
                diarization=True,
            )
            memo_row = (
                supabase.table("memos")
                .select("id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id")
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            memo_data = (memo_row.data or [None])[0] or {"id": memo_id, "user_id": user_id}
            cleaned = await sanitize_user_transcript(
                transcript, user_id, supabase, memo_data=memo_data
            )
        record_transcription_duration(time.perf_counter() - t0, "hubspot_call")

        supabase.table("memos").update(
            {
                "audio_duration": dur,
                "status": "pending_transcript",
                "transcript": cleaned,
                "transcript_confidence": 0.95,
                "processing_started_at": None,
                "error_message": None,
            }
        ).eq("id", memo_id).execute()
        persist_pipeline_meta(supabase, memo_id, stages)

        logger.info(
            "HubSpot call transcribed",
            extra=log_domain(
                DOMAIN_MEMO,
                "hubspot_call_transcribed",
                memo_id=memo_id,
                call_id=call_id,
                transcript_len=len(cleaned),
            ),
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
        persist_pipeline_meta(supabase, memo_id, stages)
