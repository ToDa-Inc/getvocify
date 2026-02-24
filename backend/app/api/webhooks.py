"""
Webhook endpoints for external services (WhatsApp, Unipile, etc.).
No auth - verified via provider-specific mechanisms.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from app.deps import get_supabase
from app.config import settings
from app.webhook_context import set_correlation_id
from app.logging_config import log_domain, DOMAIN_WEBHOOK
from app.metrics import inc_webhook_message
from app.services.whatsapp.client import WhatsAppClient
from app.services.whatsapp.webhook_parser import parse_webhook
from app.services.whatsapp.processor import process_whatsapp_message
from app.services.unipile import UnipileClient, parse_unipile_webhook
from app.services.unipile.webhook_parser import normalize_unipile_payload

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

    try:
        body = await request.json()
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

    try:
        body = await request.json()
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
