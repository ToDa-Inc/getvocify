"""
Webhook endpoints for external services (WhatsApp, Unipile, etc.).
No auth - verified via provider-specific mechanisms.
"""

import json
import logging
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
from app.services.hubspot.call_processor import (
    initiate_hubspot_call_memo,
    process_hubspot_call_background,
)
from app.services.hubspot.calls import get_call_engagement
from app.services.hubspot.client import HubSpotClient
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


async def _refresh_hubspot_token(supabase, row_id: str, refresh_token: str):
    """Exchange a refresh token for a new access token and persist it. Returns new access token or None."""
    from app.config import settings
    import httpx
    from datetime import timezone, timedelta

    client_id = settings.HUBSPOT_CLIENT_ID
    client_secret = settings.HUBSPOT_CLIENT_SECRET
    if not client_id or not client_secret or not refresh_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.hubapi.com/oauth/v1/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("HubSpot token refresh failed", extra=log_domain(DOMAIN_WEBHOOK, "hubspot_refresh_failed", error=str(e)))
        return None

    new_token = data.get("access_token")
    expires_in = int(data.get("expires_in", 1800))
    new_expires = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    try:
        supabase.table("crm_connections").update({
            "access_token": new_token,
            "token_expires_at": new_expires,
            "updated_at": now,
        }).eq("id", row_id).execute()
    except Exception as e:
        logger.warning("HubSpot token persist failed", extra=log_domain(DOMAIN_WEBHOOK, "hubspot_token_persist_failed", error=str(e)))

    logger.info("HubSpot token refreshed", extra=log_domain(DOMAIN_WEBHOOK, "hubspot_token_refreshed", row_id=row_id))
    return new_token


async def _hubspot_connection_for_portal(supabase, portal_id):
    """Most-recently-updated connected HubSpot row whose metadata.portal_id matches.
    Auto-refreshes the access token if it is expired or within 5 minutes of expiry."""
    from datetime import timezone
    r = (
        supabase.table("crm_connections")
        .select("id, user_id, access_token, refresh_token, token_expires_at, metadata")
        .eq("provider", "hubspot")
        .eq("status", "connected")
        .order("updated_at", desc=True)
        .execute()
    )
    want = str(portal_id)
    for row in r.data or []:
        meta = row.get("metadata") or {}
        if str(meta.get("portal_id")) != want:
            continue

        access_token = str(row["access_token"])

        # Refresh if expired or expiring within 5 minutes
        expires_at_str = row.get("token_expires_at")
        if expires_at_str:
            try:
                from dateutil.parser import parse as parse_dt
                expires_at = parse_dt(str(expires_at_str))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                buffer = timedelta(minutes=5)
                if datetime.now(timezone.utc) >= expires_at - buffer:
                    refresh_token = row.get("refresh_token") or ""
                    refreshed = await _refresh_hubspot_token(supabase, str(row["id"]), refresh_token)
                    if refreshed:
                        access_token = refreshed
            except Exception as e:
                logger.warning("Token expiry check failed", extra=log_domain(DOMAIN_WEBHOOK, "hubspot_expiry_check_failed", error=str(e)))

        return str(row["user_id"]), access_token
    return None


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
    HubSpot app webhooks: call engagements with recording URL.
    Verified via HUBSPOT_CLIENT_SECRET (v1 or v3 signature).
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

    supabase = get_supabase()
    processed = 0

    for ev in events:
        if not isinstance(ev, dict):
            continue
        sub = ev.get("subscriptionType") or ev.get("subscription_type")
        portal_id = ev.get("portalId") or ev.get("portal_id")
        object_id = ev.get("objectId") or ev.get("object_id")
        if portal_id is None or object_id is None:
            continue

        # Accept both legacy engagement.* and new generic object.* subscription types
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

        conn = await _hubspot_connection_for_portal(supabase, portal_id)
        if not conn:
            logger.info(
                "HubSpot webhook: no Vocify user for portal",
                extra=log_domain(DOMAIN_WEBHOOK, "hubspot_no_portal", portal_id=portal_id),
            )
            inc_webhook_message("hubspot", "skipped")
            continue

        user_id, access_token = conn
        call_id = str(object_id)
        hs = HubSpotClient(access_token)
        eng = await get_call_engagement(hs, call_id)
        if not eng:
            inc_webhook_message("hubspot", "skipped")
            continue
        props = eng.get("properties") or {}
        rec_url = (props.get("hs_call_recording_url") or "").strip()
        if not rec_url:
            inc_webhook_message("hubspot", "skipped")
            continue

        memo_id, created = await initiate_hubspot_call_memo(
            supabase, user_id, call_id, access_token
        )
        if memo_id and created:
            asyncio.create_task(
                process_hubspot_call_background(
                    memo_id,
                    user_id,
                    access_token,
                    call_id,
                    supabase,
                )
            )
            processed += 1
            inc_webhook_message("hubspot", "processed")
        elif memo_id:
            inc_webhook_message("hubspot", "skipped")
        else:
            inc_webhook_message("hubspot", "error")

    logger.info(
        "HubSpot webhook complete",
        extra=log_domain(DOMAIN_WEBHOOK, "hubspot_complete", processed=processed, events=len(events)),
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

    supabase = get_supabase()
    supabase.table("memos").update(
        {
            "status": "pending_transcript",
            "transcript": transcript,
            "transcript_confidence": 0.95,
            "processing_started_at": None,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", memo_id).execute()

    logger.info(
        "✅ Speechmatics webhook: memo updated to pending_transcript",
        extra=log_domain(DOMAIN_WEBHOOK, "speechmatics_complete",
                         job_id=job_id, memo_id=memo_id, transcript_len=len(transcript)),
    )
    inc_webhook_message("speechmatics", "processed")
    return JSONResponse(content={"status": "ok"}, status_code=200)

