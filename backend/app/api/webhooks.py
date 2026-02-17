"""
Webhook endpoints for external services (WhatsApp, etc.).
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
