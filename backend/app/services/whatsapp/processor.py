"""
WhatsApp message processor: orchestrate pipeline and handle button replies.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from supabase import Client

from app.models.memo import MemoExtraction
from app.services.extraction import ExtractionService
from app.services.glossary import GlossaryService
from app.services.memo_approval import approve_memo_core
from app.services.speechmatics_batch import SpeechmaticsBatchService
from app.services.storage import StorageService
from app.services.whatsapp.client import WhatsAppClient
from app.services.whatsapp.webhook_parser import IncomingMessage
from app.services.crm_config import CRMConfigurationService
from app.services.hubspot import HubSpotClient, HubSpotSchemaService, HubSpotSearchService

logger = logging.getLogger(__name__)

UNKNOWN_USER_MSG = (
    "Your phone number is not registered. "
    "Please sign up at app.getvocify.com and add your phone in settings."
)


def _normalize_phone(phone: str) -> str:
    """Normalize to E.164-ish: digits only, ensure leading + for lookup."""
    digits = re.sub(r"\D", "", phone)
    return digits if digits.startswith("1") else f"{digits}"


def _format_extraction_summary(extraction: MemoExtraction) -> str:
    """Format extracted fields for WhatsApp reply."""
    parts = []
    if extraction.companyName:
        parts.append(f"• Company: {extraction.companyName}")
    if extraction.dealAmount is not None:
        parts.append(f"• Amount: {extraction.dealCurrency} {extraction.dealAmount:,.0f}")
    if extraction.contactName:
        parts.append(f"• Contact: {extraction.contactName}")
    if extraction.contactEmail:
        parts.append(f"• Email: {extraction.contactEmail}")
    if extraction.summary:
        parts.append(f"• Summary: {extraction.summary[:200]}{'...' if len(extraction.summary) > 200 else ''}")
    if extraction.nextSteps:
        steps = ", ".join(extraction.nextSteps[:3])
        parts.append(f"• Next steps: {steps}")
    if not parts:
        return "I couldn't extract structured CRM fields from this. You can still approve to save the transcript."
    return "I extracted:\n\n" + "\n".join(parts) + "\n\nShould I update your CRM?"


async def lookup_user_by_phone(supabase: Client, phone: str) -> Optional[str]:
    """Return user_id if phone is registered, else None."""
    normalized = _normalize_phone(phone)
    for variant in (normalized, f"+{normalized}", normalized.lstrip("+")):
        r = (
            supabase.table("user_profiles")
            .select("id")
            .eq("phone", variant)
            .limit(1)
            .execute()
        )
        if r.data and len(r.data) > 0:
            return str(r.data[0]["id"])
    return None


async def get_field_specs(supabase: Client, user_id: str) -> Optional[list[dict]]:
    """Get curated field specs for extraction."""
    try:
        from app.api.memos import get_hubspot_client_from_connection
        client, connection_id = get_hubspot_client_from_connection(user_id, supabase)
        from app.services.crm_config import CRMConfigurationService
        config_svc = CRMConfigurationService(supabase)
        config = await config_svc.get_configuration(user_id)
        allowed = config.allowed_deal_fields if config else None
        if not allowed:
            return None
        schema_service = HubSpotSchemaService(client, supabase, connection_id)
        return await schema_service.get_curated_field_specs("deals", allowed)
    except Exception:
        return None


async def process_whatsapp_message(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: WhatsAppClient,
) -> None:
    """
    Process one incoming WhatsApp message.
    - text/audio: transcribe (if audio), extract, create memo, send summary + buttons
    - button: handle approve / add-fields
    """
    if not wa_client.is_configured():
        logger.warning("WhatsApp client not configured, skipping")
        return

    user_id = await lookup_user_by_phone(supabase, msg.from_phone)
    if not user_id:
        await wa_client.send_text(msg.from_phone, UNKNOWN_USER_MSG)
        return

    if msg.type == "button":
        await _handle_button_reply(supabase, msg, wa_client, user_id)
        return

    audio_url: Optional[str] = None
    if msg.type == "text":
        transcript = msg.text or ""
    elif msg.type == "audio" and msg.audio_id:
        transcript, audio_url = await _transcribe_audio(
            supabase, wa_client, msg, user_id
        )
        if not transcript:
            await wa_client.send_text(
                msg.from_phone,
                "Sorry, I couldn't transcribe the audio. Please try again or send a text message.",
            )
            return
    else:
        await wa_client.send_text(
            msg.from_phone,
            "I only process voice notes and text. Please send one of those.",
        )
        return

    if len(transcript.strip()) < 10:
        await wa_client.send_text(
            msg.from_phone,
            "The message was too short to extract CRM data. Please send a longer voice note or text.",
        )
        return

    memo_id, extraction = await _extract_and_create_memo(
        supabase, user_id, transcript, msg.message_id, audio_url
    )
    if not memo_id:
        await wa_client.send_text(
            msg.from_phone,
            "Something went wrong processing your message. Please try again.",
        )
        return

    summary = _format_extraction_summary(extraction)
    buttons = [
        {"id": f"approve:{memo_id}", "title": "Approve"},
        {"id": f"add:{memo_id}", "title": "Add fields"},
    ]
    await wa_client.send_interactive_buttons(msg.from_phone, summary, buttons)


async def _transcribe_audio(
    supabase: Client,
    wa_client: WhatsAppClient,
    msg: IncomingMessage,
    user_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Download audio, upload to storage, run Speechmatics batch. Return (transcript, audio_url)."""
    try:
        audio_bytes, content_type = await wa_client.download_media(msg.audio_id)
        ext = "ogg" if "ogg" in (content_type or "") or "opus" in (content_type or "") else "webm"
        storage = StorageService(supabase)
        audio_url = await storage.upload_audio(
            audio_bytes, user_id, content_type or "audio/ogg", file_extension=ext
        )
        batch = SpeechmaticsBatchService()
        transcript = await batch.transcribe(audio_url, language="es")
        return transcript, audio_url
    except Exception as e:
        logger.exception("Speechmatics batch transcription failed: %s", e)
        return None, None


async def _extract_and_create_memo(
    supabase: Client,
    user_id: str,
    transcript: str,
    whatsapp_message_id: str,
    audio_url: Optional[str],
) -> tuple[Optional[str], Optional[MemoExtraction]]:
    """Extract, create memo, return (memo_id, extraction)."""
    try:
        idempotent = (
            supabase.table("memos")
            .select("id", "extraction")
            .eq("whatsapp_message_id", whatsapp_message_id)
            .limit(1)
            .execute()
        )
        if idempotent.data:
            return idempotent.data[0]["id"], MemoExtraction(**idempotent.data[0]["extraction"])

        field_specs = await get_field_specs(supabase, user_id)
        glossary_svc = GlossaryService(supabase)
        glossary = await glossary_svc.get_user_glossary(user_id)
        glossary_text = glossary_svc.format_for_llm(glossary)

        extraction_svc = ExtractionService()
        extraction = await extraction_svc.extract(
            transcript, field_specs, glossary_text=glossary_text
        )

        insert = {
            "user_id": user_id,
            "audio_url": audio_url,
            "audio_duration": 0.0,
            "status": "pending_review",
            "transcript": transcript,
            "transcript_confidence": 0.9,
            "extraction": extraction.model_dump(),
            "processed_at": datetime.utcnow().isoformat(),
            "source": "whatsapp",
            "whatsapp_message_id": whatsapp_message_id,
        }
        r = supabase.table("memos").insert(insert).execute()
        if not r.data:
            return None, None
        return r.data[0]["id"], extraction
    except Exception as e:
        logger.exception("Extract and create memo failed: %s", e)
        return None, None


async def _handle_button_reply(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: WhatsAppClient,
    user_id: str,
) -> None:
    """Handle Approve or Add fields button."""
    bid = (msg.button_id or "").strip()
    if bid.startswith("approve:"):
        memo_id = bid[8:].strip()
        if not memo_id:
            await wa_client.send_text(msg.from_phone, "Invalid request. Please try again.")
            return
        try:
            await approve_memo_core(supabase, memo_id, user_id)
            await wa_client.send_text(msg.from_phone, "Done! Your CRM has been updated.")
        except ValueError as e:
            await wa_client.send_text(msg.from_phone, f"Could not update CRM: {e}")
    elif bid.startswith("add:"):
        memo_id = bid[4:].strip()
        if not memo_id:
            await wa_client.send_text(msg.from_phone, "Invalid request. Please try again.")
            return
        await wa_client.send_text(
            msg.from_phone,
            f"Reply with the fields to add, one per line.\nExample:\ndealname: Acme Corp\namount: 50000",
        )
    else:
        await wa_client.send_text(msg.from_phone, "Unknown action. Please try again.")
