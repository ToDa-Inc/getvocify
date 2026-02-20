"""
Webhook endpoints for external services (WhatsApp, Unipile, etc.).
No auth - verified via provider-specific mechanisms.
"""

import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from app.deps import get_supabase
from app.config import settings
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
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={"status": "error", "message": "Invalid JSON"},
            status_code=400,
        )

    if body.get("object") != "whatsapp_business_account":
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    supabase = get_supabase()
    wa_client = WhatsAppClient()

    if not wa_client.is_configured():
        logger.warning("WhatsApp not configured, acknowledging webhook")
        return JSONResponse(content={"status": "ok"}, status_code=200)

    messages = parse_webhook(body)
    for msg in messages:
        try:
            await process_whatsapp_message(supabase, msg, wa_client)
        except Exception as e:
            logger.exception("WhatsApp processing failed for %s: %s", msg.message_id, e)

    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.post("/unipile")
async def unipile_webhook(request: Request):
    """
    Unipile WhatsApp webhook handler.
    Accepts direct Unipile events or n8n-wrapped array format.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={"status": "error", "message": "Invalid JSON"},
            status_code=400,
        )

    events = normalize_unipile_payload(body)
    if not events:
        return JSONResponse(content={"status": "ok", "message": "No events"}, status_code=200)

    supabase = get_supabase()
    unipile_client = UnipileClient()

    if not unipile_client.is_configured():
        logger.warning("Unipile not configured, acknowledging webhook")
        return JSONResponse(content={"status": "ok"}, status_code=200)

    for ev in events:
        if ev.get("event") != "message_received":
            continue
        if ev.get("account_type") != "WHATSAPP":
            continue
        if ev.get("is_sender"):
            continue

        messages = parse_unipile_webhook(ev)
        for msg in messages:
            try:
                await process_whatsapp_message(supabase, msg, unipile_client)
            except Exception as e:
                logger.exception("Unipile processing failed for %s: %s", msg.message_id, e)

    return JSONResponse(content={"status": "ok"}, status_code=200)
