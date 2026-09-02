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
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from twilio.twiml.voice_response import VoiceResponse

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
from app.services.telephony.caller_id import (
    CallerIdNotVerified,
    mark_caller_id_failed,
    mark_caller_id_verified,
    resolve_caller_id,
)
from app.services.telephony.twiml import (
    DEFAULT_RECORDING_ANNOUNCEMENT_ES,
    InvalidPhoneNumber,
    build_outbound_twiml,
    build_whisper_twiml,
    normalize_e164,
)
from app.services.storage import StorageService
from app.services.telephony.call_processor import (
    download_twilio_recording,
    initiate_vocify_call_memo,
    process_vocify_call_background,
)
from app.services.telephony.webhook_signature import (
    identity_from_client_from,
    verify_twilio_signature,
)

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


def _twilio_public_url(request: Request) -> str:
    """The URL Twilio signed, rebuilt from config (proxies rewrite the host)."""
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}{request.url.path}"


async def _twilio_form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


def _twilio_authentic(request: Request, params: dict[str, str]) -> bool:
    import os

    skip_requested = os.environ.get("TWILIO_SKIP_SIG_CHECK", "").lower() in ("1", "true", "yes")
    if skip_requested:
        if settings.ENVIRONMENT == "production":
            logger.warning(
                "TWILIO_SKIP_SIG_CHECK set but refused in production; "
                "enforcing Twilio signature check"
            )
        else:
            logger.warning("Twilio webhook signature check skipped (dev only)")
            return True
    return verify_twilio_signature(
        _twilio_public_url(request),
        params,
        request.headers.get("X-Twilio-Signature", ""),
        settings.TWILIO_AUTH_TOKEN or "",
    )


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


def _reject_twiml(message: str) -> Response:
    response = VoiceResponse()
    response.say(message, language=settings.TWILIO_ANNOUNCEMENT_LANGUAGE)
    response.hangup()
    return _twiml(str(response))


@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    """TwiML App Voice URL. Authorizes the caller ID and dials the prospect.

    `CallerId` arrives from the browser as a *preference*; the authoritative
    check is against `user_caller_ids` for the signed Twilio identity.
    """
    supabase = get_supabase()
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)

    user_id = identity_from_client_from(params.get("From", ""))
    if not user_id:
        return _reject_twiml("Llamada no autorizada.")

    # A genuine Twilio Voice Request always carries a CallSid. Its absence
    # means the request isn't what it claims to be — and an empty string
    # would violate outbound_calls.twilio_call_sid's NOT NULL UNIQUE
    # constraint on the first request, then get silently swallowed as a
    # "duplicate key" on every one after.
    call_sid = params.get("CallSid") or ""
    if not call_sid:
        logger.warning("Twilio voice webhook missing CallSid; rejecting")
        return _reject_twiml("Llamada no autorizada.")

    try:
        to_number = normalize_e164(
            params.get("To", ""),
            default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE,
        )
        caller_id = resolve_caller_id(supabase, user_id, params.get("CallerId") or None)
    except (InvalidPhoneNumber, CallerIdNotVerified) as e:
        logger.warning("Twilio voice webhook rejected: %s", e)
        return _reject_twiml("Número no válido o identificador no verificado.")

    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")

    # Persisted now because the recording callback arrives minutes later with
    # nothing but this same parent-leg CallSid to correlate on.
    try:
        supabase.table("outbound_calls").insert(
            {
                "user_id": user_id,
                "twilio_call_sid": call_sid,
                "from_number": caller_id,
                "to_number": to_number,
                # Never taken from the request: a client-supplied hub id would
                # taint the recording webhook's externalAccountId comparison.
                # Task 6 populates this from the user's own crm_connections row.
                "hubspot_hub_id": None,
                "hubspot_contact_id": params.get("ContactId") or None,
                "hubspot_deal_id": params.get("DealId") or None,
                "status": "dialing",
            }
        ).execute()
    except Exception as e:
        if "duplicate key" not in str(e).lower() and "23505" not in str(e):
            raise

    return _twiml(
        build_outbound_twiml(
            to=to_number,
            caller_id=caller_id,
            recording_callback_url=f"{base}/webhooks/twilio/recording",
            whisper_url=(
                f"{base}/webhooks/twilio/whisper"
                if settings.CALLING_RECORDING_ANNOUNCEMENT_ENABLED
                else None
            ),
        )
    )


@router.post("/twilio/whisper")
async def twilio_whisper(request: Request):
    """Recording disclosure, played to the prospect only (AEPD 1/2023)."""
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)
    return _twiml(
        build_whisper_twiml(
            announcement=(
                settings.TWILIO_RECORDING_ANNOUNCEMENT
                or DEFAULT_RECORDING_ANNOUNCEMENT_ES
            ),
            language=settings.TWILIO_ANNOUNCEMENT_LANGUAGE,
        )
    )


@router.post("/twilio/caller-id-status")
async def twilio_caller_id_status(request: Request):
    """Outcome of a caller ID verification call.

    Twilio's outgoing-caller-ID verification status callback carries
    `VerificationStatus` plus the standard TwiML Voice Request parameters,
    which include `CallSid` — the same value `validation_requests.create(...)`
    returned as `call_sid`, which is what's persisted into
    `user_caller_ids.twilio_validation_sid`. Matching on `To` (a bare phone
    number) instead of the SID would flip every row that shares that number
    across every user who ever registered it — a cross-tenant leak. So this
    matches by CallSid only; `mark_caller_id_verified`/`mark_caller_id_failed`
    already no-op (and log) when the SID is absent.
    """
    supabase = get_supabase()
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)

    validation_sid = params.get("CallSid") or None
    verified = (params.get("VerificationStatus") or "").lower() == "success"
    if verified:
        mark_caller_id_verified(supabase, validation_sid)
    else:
        mark_caller_id_failed(supabase, validation_sid)
    return Response(status_code=204)


@router.post("/twilio/recording")
async def twilio_recording(request: Request):
    """Recording is ready: persist the WAV, then transcribe and extract.

    `CallSid` here is the parent (browser) leg — the same SID the voice webhook
    stored — so it correlates the audio back to its CRM context.
    """
    supabase = get_supabase()
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)

    call_sid = (params.get("CallSid") or "").strip()
    recording_url = (params.get("RecordingUrl") or "").strip()
    if not call_sid or not recording_url:
        return Response(status_code=204)

    found = (
        supabase.table("outbound_calls")
        .select("*")
        .eq("twilio_call_sid", call_sid)
        .limit(1)
        .execute()
    )
    call_row = (found.data or [None])[0]
    if not call_row:
        logger.warning("Twilio recording for unknown call_sid=%s", call_sid)
        return Response(status_code=204)
    if call_row.get("memo_id"):
        return Response(status_code=204)  # redelivery

    duration = float(params.get("RecordingDuration") or 0) or 1.0
    audio_bytes = await download_twilio_recording(recording_url)
    path = await StorageService(supabase).upload_call_recording(
        audio_bytes, call_row["user_id"], call_sid
    )

    supabase.table("outbound_calls").update(
        {
            "recording_sid": params.get("RecordingSid"),
            "recording_path": path,
            "recording_duration": int(duration),
            "answered_at": (
                datetime.now(timezone.utc) - timedelta(seconds=int(duration))
            ).isoformat(),
            "status": "recorded",
        }
    ).eq("twilio_call_sid", call_sid).execute()
    call_row["recording_duration"] = int(duration)

    memo_id, created = await initiate_vocify_call_memo(supabase, call_row)
    if memo_id and created:
        asyncio.create_task(
            process_vocify_call_background(
                memo_id,
                call_row["user_id"],
                call_sid,
                audio_bytes,
                duration,
                supabase,
            )
        )
    return Response(status_code=204)

