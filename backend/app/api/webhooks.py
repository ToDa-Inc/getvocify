"""
Webhook endpoints for external services (WhatsApp, Unipile, etc.).
No auth - verified via provider-specific mechanisms.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncio

from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from app.deps import get_supabase
from app.config import settings
from app.webhook_context import set_correlation_id
from app.logging_config import log_domain, DOMAIN_WEBHOOK
from app.metrics import inc_webhook_message
from app.services.hubspot.webhook_signature import verify_hubspot_webhook
from app.services.whatsapp.client import WhatsAppClient
from app.services.whatsapp.webhook_parser import parse_webhook
from app.services.whatsapp.webhook_signature import verify_meta_webhook_signature
from app.services.whatsapp.processor import process_whatsapp_message
from app.services.unipile import UnipileClient, parse_unipile_webhook
from app.services.unipile.webhook_parser import normalize_unipile_payload
from app.services.unipile.webhook_signature import verify_unipile_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """
    Meta webhook verification.
    Meta sends GET with hub.mode, hub.verify_token, hub.challenge.
    Return hub.challenge if verify_token matches.
    """
    if hub_mode != "subscribe":
        return PlainTextResponse("", status_code=400)
    verify_token = settings.WHATSAPP_VERIFY_TOKEN or ""
    if hub_verify_token != verify_token:
        return PlainTextResponse("Forbidden", status_code=403)
    return PlainTextResponse(hub_challenge)


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Meta WhatsApp webhook handler.
    Parses incoming messages and processes via WhatsApp processor.
    """
    cid = f"wa_{uuid4().hex[:8]}"
    set_correlation_id(cid)
    logger.info(
        "📤 Meta WhatsApp webhook received",
        extra=log_domain(DOMAIN_WEBHOOK, "whatsapp_received", correlation_id=cid),
    )

    raw_body = await request.body()

    import os
    skip_sig = os.environ.get("WHATSAPP_SKIP_SIG_CHECK", "").lower() in ("1", "true", "yes")
    app_secret = settings.WHATSAPP_APP_SECRET or ""
    if skip_sig:
        logger.warning(
            "WhatsApp webhook signature check SKIPPED (WHATSAPP_SKIP_SIG_CHECK=1, dev only)",
            extra=log_domain(DOMAIN_WEBHOOK, "whatsapp_sig_skipped"),
        )
    elif app_secret:
        sig = request.headers.get("x-hub-signature-256") or request.headers.get("x-hub-signature") or ""
        if not verify_meta_webhook_signature(raw_body, sig, app_secret):
            inc_webhook_message("whatsapp", "error")
            return PlainTextResponse("Forbidden", status_code=403)
    else:
        logger.warning(
            "WhatsApp webhook accepted without WHATSAPP_APP_SECRET (dev only)",
            extra=log_domain(DOMAIN_WEBHOOK, "whatsapp_no_secret"),
        )

    try:
        body = json.loads(raw_body.decode("utf-8") or "null")
    except Exception:
        inc_webhook_message("whatsapp", "error")
        return JSONResponse(
            content={"status": "error", "message": "Invalid JSON"},
            status_code=400,
        )

    if body.get("object") != "whatsapp_business_account":
        inc_webhook_message("whatsapp", "skipped")
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    supabase = get_supabase()
    wa_client = WhatsAppClient()

    if not wa_client.is_configured():
        logger.warning(
            "⚠️ WhatsApp not configured, acknowledging webhook",
            extra=log_domain(DOMAIN_WEBHOOK, "whatsapp_not_configured"),
        )
        inc_webhook_message("whatsapp", "skipped")
        return JSONResponse(content={"status": "ok"}, status_code=200)

    messages = parse_webhook(body)
    for msg in messages:
        try:
            await process_whatsapp_message(supabase, msg, wa_client)
            inc_webhook_message("whatsapp", "processed")
        except Exception as e:
            inc_webhook_message("whatsapp", "error")
            logger.exception(
                "❌ WhatsApp processing failed",
                extra=log_domain(DOMAIN_WEBHOOK, "whatsapp_process_failed", message_id=msg.message_id, error=str(e)),
            )

    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.post("/unipile")
async def unipile_webhook(request: Request):
    """
    Unipile WhatsApp webhook handler.
    Accepts direct Unipile events or n8n-wrapped array format.
    """
    cid = f"wh_{uuid4().hex[:8]}"
    set_correlation_id(cid)

    raw_body = await request.body()

    import os
    skip_sig = os.environ.get("UNIPILE_SKIP_SIG_CHECK", "").lower() in ("1", "true", "yes")
    unipile_secret = settings.UNIPILE_WEBHOOK_SECRET or ""
    if skip_sig:
        logger.warning(
            "Unipile webhook signature check SKIPPED (UNIPILE_SKIP_SIG_CHECK=1, dev only)",
            extra=log_domain(DOMAIN_WEBHOOK, "unipile_sig_skipped"),
        )
    elif unipile_secret:
        sig = request.headers.get("unipile-signature") or ""
        if not verify_unipile_webhook_signature(raw_body, sig, unipile_secret):
            inc_webhook_message("unipile", "error")
            return PlainTextResponse("Forbidden", status_code=403)
    else:
        logger.warning(
            "Unipile webhook accepted without UNIPILE_WEBHOOK_SECRET (dev only)",
            extra=log_domain(DOMAIN_WEBHOOK, "unipile_no_secret"),
        )

    try:
        body = json.loads(raw_body.decode("utf-8") or "null")
    except Exception as e:
        inc_webhook_message("unipile", "error")
        logger.error(
            "❌ Unipile webhook invalid JSON",
            extra=log_domain(DOMAIN_WEBHOOK, "unipile_invalid_json", error=str(e)),
        )
        return JSONResponse(
            content={"status": "error", "message": "Invalid JSON"},
            status_code=400,
        )

    body_keys = list(body.keys()) if isinstance(body, dict) else f"list[{len(body)}]" if isinstance(body, list) else type(body).__name__
    logger.info(
        "📤 Unipile webhook received",
        extra=log_domain(DOMAIN_WEBHOOK, "unipile_received", body_type=type(body).__name__, body_keys=body_keys),
    )

    events = normalize_unipile_payload(body)
    if not events:
        inc_webhook_message("unipile", "skipped")
        logger.info(
            "⚠️ Unipile webhook no events extracted",
            extra=log_domain(DOMAIN_WEBHOOK, "unipile_no_events", reason="normalize_returned_empty"),
        )
        return JSONResponse(content={"status": "ok", "message": "No events"}, status_code=200)

    logger.info(
        "✅ Unipile webhook events normalized",
        extra=log_domain(DOMAIN_WEBHOOK, "unipile_events_normalized", events_count=len(events)),
    )

    supabase = get_supabase()
    unipile_client = UnipileClient()

    if not unipile_client.is_configured():
        logger.warning(
            "⚠️ Unipile not configured, acknowledging without processing",
            extra=log_domain(DOMAIN_WEBHOOK, "unipile_not_configured"),
        )
        inc_webhook_message("unipile", "skipped")
        return JSONResponse(content={"status": "ok"}, status_code=200)

    processed = 0
    for i, ev in enumerate(events):
        event_type = ev.get("event")
        account_type = ev.get("account_type")
        is_sender = ev.get("is_sender")
        msg_id = ev.get("message_id")

        if event_type != "message_received":
            logger.info(
                "Unipile event skipped",
                extra=log_domain(DOMAIN_WEBHOOK, "unipile_event_skipped", event_index=i, reason="event_type_mismatch", event_type=event_type, message_id=msg_id),
            )
            continue
        if account_type != "WHATSAPP":
            logger.info(
                "Unipile event skipped",
                extra=log_domain(DOMAIN_WEBHOOK, "unipile_event_skipped", event_index=i, reason="account_type_mismatch", account_type=account_type, message_id=msg_id),
            )
            continue
        if is_sender:
            logger.info(
                "Unipile event skipped",
                extra=log_domain(DOMAIN_WEBHOOK, "unipile_event_skipped", event_index=i, reason="is_sender", message_id=msg_id),
            )
            continue

        messages = parse_unipile_webhook(ev)
        if not messages:
            attachments = ev.get("attachments") or []
            logger.info(
                "Unipile event produced no messages",
                extra=log_domain(
                    DOMAIN_WEBHOOK,
                    "unipile_parse_empty",
                    event_index=i,
                    reason="parse_returned_empty",
                    message_id=msg_id,
                    body_keys=list(ev.keys())[:15],
                    has_attachments=len(attachments) > 0,
                    event_type=ev.get("event"),
                ),
            )
            continue

        for msg in messages:
            logger.info(
                "💬 Unipile processing message",
                extra=log_domain(DOMAIN_WEBHOOK, "unipile_process_message", message_id=msg.message_id, from_phone=msg.from_phone, chat_id=getattr(msg, "chat_id", None), account_id=getattr(msg, "account_id", None)),
            )
            try:
                await process_whatsapp_message(supabase, msg, unipile_client)
                processed += 1
                inc_webhook_message("unipile", "processed")
            except Exception as e:
                inc_webhook_message("unipile", "error")
                logger.exception(
                    "❌ Unipile processing failed",
                    extra=log_domain(DOMAIN_WEBHOOK, "unipile_process_failed", message_id=msg.message_id, error=str(e)),
                )

    logger.info(
        "✅ Unipile webhook complete",
        extra=log_domain(DOMAIN_WEBHOOK, "unipile_complete", processed_count=processed, events_count=len(events)),
    )
    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.get("/hubspot")
async def hubspot_webhook_info():
    """
    Dev helper: confirms the route is reachable (e.g. through ngrok) before HubSpot POSTs here.
    HubSpot does not call GET; use this with curl or a browser after `make ngrok`.
    """
    base = "https://YOUR_NGROK_HOST"
    example_event = {
        "subscriptionType": "engagement.propertyChange",
        "portalId": 12345678,
        "objectId": 99999999999,
        "propertyName": "hs_call_recording_url",
        "propertyValue": "https://example.com/recording.mp3",
    }
    return JSONResponse(
        {
            "ok": True,
            "service": "vocify-hubspot-call-webhook",
            "postPath": "/webhooks/hubspot",
            "signature": "Required when HUBSPOT_CLIENT_SECRET is set (X-HubSpot-Signature v1 or v3).",
            "ngrok": {
                "hint": "Terminal A: make backend  |  Terminal B: make ngrok  |  Then: make ngrok-url",
                "webhookUrlExample": f"{base}/webhooks/hubspot",
            },
            "hubspotApp": {
                "hint": "Register target URL via HubSpot developer UI (Webhooks) or "
                "backend/scripts/setup_hubspot_webhooks.py with HUBSPOT_WEBHOOK_TARGET_URL.",
            },
            "examplePostBody": [example_event],
            "curlDevNoSecret": (
                "curl -sS -X POST http://localhost:8000/webhooks/hubspot "
                '-H "Content-Type: application/json" '
                f"-d '{json.dumps([example_event])}'"
            ),
        }
    )


@router.post("/hubspot")
async def hubspot_webhook(request: Request):
    """
    HubSpot app webhooks (recording URL, call create).

    Acknowledged only. Transcription starts when the user presses Transcribe
    in the extension (POST /crm/hubspot/calls/{id}/process). Auto-STT on every
    recording would bill Deepgram for calls nobody reviews.
    """
    cid = f"hs_{uuid4().hex[:8]}"
    set_correlation_id(cid)
    body = await request.body()

    import os
    skip_sig = os.environ.get("HUBSPOT_SKIP_SIG_CHECK", "").lower() in ("1", "true", "yes")
    secret = settings.HUBSPOT_CLIENT_SECRET or ""
    if skip_sig:
        logger.warning(
            "HubSpot webhook signature check SKIPPED (HUBSPOT_SKIP_SIG_CHECK=1, dev only)",
            extra=log_domain(DOMAIN_WEBHOOK, "hubspot_sig_skipped"),
        )
    elif secret:
        if not verify_hubspot_webhook(request, body, secret):
            inc_webhook_message("hubspot", "error")
            return PlainTextResponse("Forbidden", status_code=403)
    else:
        logger.warning(
            "HubSpot webhook accepted without HUBSPOT_CLIENT_SECRET (dev only)",
            extra=log_domain(DOMAIN_WEBHOOK, "hubspot_no_secret"),
        )

    try:
        payload = json.loads(body.decode("utf-8") or "null")
    except Exception:
        inc_webhook_message("hubspot", "error")
        return JSONResponse(content={"status": "error", "message": "Invalid JSON"}, status_code=400)

    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        events = payload.get("events") or [payload]
    else:
        events = []

    skipped = 0

    for ev in events:
        if not isinstance(ev, dict):
            continue
        sub = ev.get("subscriptionType") or ev.get("subscription_type")
        if sub in ("engagement.propertyChange", "object.propertyChange"):
            if ev.get("propertyName") != "hs_call_recording_url":
                continue
            val = (ev.get("propertyValue") or ev.get("property_value") or "").strip()
            if not val:
                continue
        elif sub in ("engagement.creation", "object.creation"):
            pass
        else:
            continue

        skipped += 1
        inc_webhook_message("hubspot", "skipped")

    logger.info(
        "HubSpot webhook complete (STT is Transcribe-only)",
        extra=log_domain(DOMAIN_WEBHOOK, "hubspot_complete", processed=0, skipped=skipped, events=len(events)),
    )
    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.post("/speechmatics")
async def speechmatics_webhook(request: Request):
    """
    Speechmatics batch job completion callback.

    Speechmatics POSTs multipart/form-data with:
      - Query params: ?id=<job_id>&status=success|error&memo_id=<memo_id>
      - Body part named 'transcript': plain-text transcript

    We match the memo by memo_id (passed in the notification URL we registered),
    update it to pending_transcript, and return 200 immediately.
    """
    job_id = request.query_params.get("id")
    status = request.query_params.get("status")
    memo_id = request.query_params.get("memo_id")

    cid = f"sm_{uuid4().hex[:8]}"
    set_correlation_id(cid)
    logger.info(
        "Speechmatics webhook received",
        extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_received",
                         job_id=job_id, status=status, memo_id=memo_id, correlation_id=cid),
    )

    if not memo_id:
        logger.warning("Speechmatics webhook: missing memo_id", extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_no_memo_id"))
        return JSONResponse(content={"status": "error", "message": "memo_id required"}, status_code=400)

    if status == "error":
        logger.error(
            "Speechmatics job failed",
            extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_job_error", job_id=job_id, memo_id=memo_id),
        )
        supabase = get_supabase()
        supabase.table("memos").update(
            {"status": "failed", "error_message": f"Speechmatics job failed: {job_id}", "processing_started_at": None}
        ).eq("id", memo_id).execute()
        inc_webhook_message("speechmatics", "error")
        return JSONResponse(content={"status": "ok"}, status_code=200)

    # Parse transcript from multipart body
    transcript = ""
    try:
        form = await request.form()
        transcript_file = form.get("transcript")
        if transcript_file is not None:
            if hasattr(transcript_file, "read"):
                raw = await transcript_file.read()
                transcript = raw.decode("utf-8", errors="replace").strip()
            else:
                transcript = str(transcript_file).strip()
    except Exception as e:
        logger.warning("Speechmatics webhook: could not parse form body: %s", e,
                       extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_parse_error", error=str(e)))

    if not transcript:
        # Fall back to fetching transcript directly from Speechmatics API
        if job_id:
            try:
                from app.services.speechmatics_batch import SpeechmaticsBatchService
                transcript = await SpeechmaticsBatchService().get_transcript(job_id)
            except Exception as e:
                logger.error("Speechmatics webhook: fallback fetch failed: %s", e,
                             extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_fallback_failed", job_id=job_id, error=str(e)))

    if not transcript:
        logger.error("Speechmatics webhook: empty transcript",
                     extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_empty_transcript", job_id=job_id, memo_id=memo_id))
        supabase = get_supabase()
        supabase.table("memos").update(
            {"status": "failed", "error_message": "Empty transcript from Speechmatics", "processing_started_at": None}
        ).eq("id", memo_id).execute()
        inc_webhook_message("speechmatics", "error")
        return JSONResponse(content={"status": "ok"}, status_code=200)

    asyncio.create_task(_finalize_speechmatics_transcript(memo_id, transcript, job_id))
    logger.info(
        "Speechmatics webhook: sanitizing transcript in background",
        extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_sanitize_queued",
                         job_id=job_id, memo_id=memo_id, transcript_len=len(transcript)),
    )
    inc_webhook_message("speechmatics", "processed")
    return JSONResponse(content={"status": "ok"}, status_code=200)


async def _finalize_speechmatics_transcript(memo_id: str, transcript: str, job_id) -> None:
    """Glossary repair + speaker canonicalize, then start CRM field extraction."""
    supabase = get_supabase()
    cleaned = transcript
    sanitize_s = 0.0
    total_s = None
    try:
        row = (
            supabase.table("memos")
            .select("id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id,status,processing_started_at")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
        memo = (row.data or [None])[0] or {}
        user_id = memo.get("user_id")
        started = memo.get("processing_started_at")
        t0 = time.perf_counter()
        if user_id:
            from app.services.transcript_sanitize import sanitize_user_transcript

            cleaned = await sanitize_user_transcript(
                transcript, user_id, supabase, memo_data=memo
            )
        sanitize_s = time.perf_counter() - t0
        if started:
            try:
                raw = str(started).replace("Z", "+00:00")
                start_dt = datetime.fromisoformat(raw)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                total_s = (datetime.now(timezone.utc) - start_dt).total_seconds()
            except Exception:
                total_s = None
    except Exception:
        logger.exception(
            "Speechmatics webhook: sanitize failed, storing raw transcript",
            extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_sanitize_failed", memo_id=memo_id, job_id=job_id),
        )
        cleaned = transcript

    now = datetime.now(timezone.utc).isoformat()
    if not user_id:
        supabase.table("memos").update(
            {
                "status": "failed",
                "transcript": cleaned,
                "transcript_confidence": 0.95,
                "processed_at": now,
                "error_message": "User missing for extraction",
            }
        ).eq("id", memo_id).execute()
        return

    from app.api.memos import start_extraction_from_transcript
    from app.services.transcript_sanitize import raw_speaker_count

    await start_extraction_from_transcript(
        memo_id,
        user_id,
        cleaned,
        supabase,
        source_type="voice_memo",
        extra_update={
            "processed_at": now,
            "transcript_raw": transcript,
            "transcript_stt_meta": {
                "provider": "speechmatics",
                "raw_speaker_count": raw_speaker_count(transcript),
            },
        },
    )
    logger.info(
        "✅ Speechmatics webhook: memo updated to extracting",
        extra=log_domain(
            DOMAIN_WEBHOOK,
            "speechmatics_complete",
            job_id=job_id,
            memo_id=memo_id,
            transcript_len=len(cleaned or ""),
            sanitize_s=round(sanitize_s, 1),
            total_s=round(total_s, 1) if total_s is not None else None,
        ),
    )

