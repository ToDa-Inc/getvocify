"""
WhatsApp message processor: orchestrate pipeline and handle button replies.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from supabase import Client

from app.models.memo import MemoExtraction, ApproveMemoRequest
from app.services.conversation import ConversationService, IntentService
from app.services.conversation.intent import APPROVE_PATTERNS, ADD_PATTERNS, REJECT_PATTERNS, _normalize
from app.services.deal_lookup import DealLookupService
from app.services.extraction import ExtractionService
from app.services.glossary import GlossaryService
from app.services.memo_approval import approve_memo_core
from app.services.speechmatics_batch import SpeechmaticsBatchService
from app.services.storage import StorageService
from app.services.whatsapp.webhook_parser import IncomingMessage
from app.logging_config import log_domain, DOMAIN_WHATSAPP

# Any client with send_text(to, text, **kwargs), send_interactive_buttons(to, body, buttons, **kwargs)
from typing import Any, Protocol


class MessagingClient(Protocol):
    def is_configured(self) -> bool: ...

    async def send_text(self, to: str, text: str, **kwargs: Any) -> None: ...

    async def send_interactive_buttons(
        self, to: str, body: str, buttons: list[dict], **kwargs: Any
    ) -> None: ...

    async def download_media(self, msg: IncomingMessage) -> tuple[bytes, str]: ...
from app.services.crm_config import CRMConfigurationService
from app.services.hubspot import HubSpotClient, HubSpotSchemaService, HubSpotSearchService

logger = logging.getLogger(__name__)

UNKNOWN_USER_MSG = (
    "Your phone number is not registered. "
    "Please sign up at app.getvocify.com and add your phone in settings."
)


def _parse_deal_choice(text: str) -> Optional[int]:
    """Parse reply as deal choice number (1, 2, 3...). Returns int or None."""
    s = (text or "").strip()
    if not s or len(s) > 2:
        return None
    digits = "".join(c for c in s if c.isdigit())
    if digits:
        try:
            return int(digits)
        except ValueError:
            pass
    return None


def _normalize_phone(phone: str) -> str:
    """Normalize to E.164-ish: digits only, ensure leading + for lookup."""
    digits = re.sub(r"\D", "", phone)
    return digits if digits.startswith("1") else f"{digits}"


def _format_property_value_for_display(field_name: str, value: Any, extraction: MemoExtraction) -> str:
    """Format a property value for WhatsApp display (like frontend)."""
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value[:5])
    if isinstance(value, (int, float)):
        # Price-per-unit (e.g. price_per_fte_eur): 1.5€ not 2€
        if "price" in field_name.lower() or "per_fte" in field_name.lower():
            s = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{s}€"
        # Amount (total): integer, thousands separator for large numbers
        if field_name == "amount":
            return f"{value:,.0f}€".replace(",", ".")
        if "eur" in field_name.lower():
            s = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{s}€"
        return str(value)
    s = str(value)
    # Truncate long text (e.g. description)
    if len(s) > 80:
        return s[:77] + "..."
    return s


NOT_SET = "—"

def _get_proposed_updates_display(
    extraction: MemoExtraction,
    allowed_fields: list[str],
    field_specs: Optional[list[dict]] = None,
) -> list[tuple[str, str]]:
    """Return (label, display_value) for each allowed property. Shows full picture with '—' when not set."""
    allowed = list(allowed_fields or [])
    labels = {s["name"]: s["label"] for s in (field_specs or []) if s.get("name") and s.get("label")}

    def _label(name: str) -> str:
        return labels.get(name, name.replace("_", " ").title())

    def _value(name: str, val: Any) -> str:
        if val is None or val == "" or (isinstance(val, list) and len(val) == 0):
            return NOT_SET
        return _format_property_value_for_display(name, val, extraction)

    skip_raw = {
        "summary", "painPoints", "nextSteps", "objections", "decisionMakers",
        "confidence", "contactName", "companyName", "contactEmail",
        "deal_currency_code",
    }
    read_only = {
        "hs_closed_amount", "hs_notes_next_activity", "hs_next_step",
        "hs_lastmodifieddate", "hs_createdate", "hs_object_id",
    }

    # Build extraction → property value map (same sources as sync)
    raw = extraction.raw_extraction or {}
    values: dict[str, Any] = {}
    if "dealname" in allowed:
        values["dealname"] = raw.get("dealname") or (f"{extraction.companyName} Deal" if extraction.companyName else f"{extraction.contactName} Deal" if extraction.contactName else "New Deal")
    if "amount" in allowed:
        values["amount"] = extraction.dealAmount if extraction.dealAmount is not None else raw.get("amount")
    if "closedate" in allowed:
        values["closedate"] = extraction.closeDate or raw.get("closedate")
    if "description" in allowed:
        values["description"] = extraction.summary or raw.get("description")
    if "dealstage" in allowed:
        values["dealstage"] = extraction.dealStage or raw.get("dealstage")
    for k in allowed:
        if k not in values and k not in skip_raw and k not in read_only:
            values[k] = raw.get(k)

    # Show all allowed fields (ordered by allowed_fields), with value or "—"
    updates: list[tuple[str, str]] = []
    for name in allowed:
        if name in read_only:
            continue
        val = values.get(name)
        display = _value(name, val)
        updates.append((_label(name), display))

    return updates


def _format_extraction_summary(
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]] = None,
    field_specs: Optional[list[dict]] = None,
) -> str:
    """Format extracted fields for WhatsApp reply. Labels match frontend (MemoDetail)."""
    sections: list[str] = []

    # Deal Details: Company only (amount/stage/date in proposed updates below)
    if extraction.companyName:
        sections.append("DEAL DETAILS\nCompany: " + extraction.companyName)

    # Contact Person (frontend: Name, Role, Email)
    contact_parts: list[str] = []
    if extraction.contactName:
        contact_parts.append(f"Name: {extraction.contactName}")
    if extraction.contactRole:
        contact_parts.append(f"Role: {extraction.contactRole}")
    if extraction.contactEmail:
        contact_parts.append(f"Email: {extraction.contactEmail}")
    if extraction.contactPhone:
        contact_parts.append(f"Phone: {extraction.contactPhone}")
    if contact_parts:
        sections.append("CONTACT PERSON\n" + "\n".join(contact_parts))

    # Insights (frontend: Summary, Pain Points, Next Steps, Competitors)
    insight_parts: list[str] = []
    if extraction.summary:
        insight_parts.append(f"Summary: {extraction.summary[:300]}{'...' if len(extraction.summary) > 300 else ''}")
    if extraction.painPoints:
        insight_parts.append(f"Pain Points: {', '.join(extraction.painPoints[:3])}")
    if extraction.nextSteps:
        insight_parts.append(f"Next Steps: {', '.join(extraction.nextSteps[:3])}")
    if extraction.competitors:
        insight_parts.append(f"Competitors: {', '.join(extraction.competitors[:3])}")
    if extraction.objections:
        insight_parts.append(f"Objections: {', '.join(extraction.objections[:2])}")
    if insight_parts:
        sections.append("INSIGHTS\n" + "\n".join(insight_parts))

    if not sections:
        return "I couldn't extract structured CRM fields from this. You can still approve to save the transcript."

    body = "I extracted:\n\n" + "\n\n".join(sections)

    # Add proposed updates in clean "Label: value" format (like frontend)
    updates = _get_proposed_updates_display(
        extraction, allowed_fields or [], field_specs
    )
    if updates:
        lines = [f"{label}: {val}" for label, val in updates]
        body += "\n\n" + "\n".join(lines)

    return body + "\n\nShould I update your CRM?"


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


def _client_kwargs(msg: IncomingMessage) -> dict:
    """Extra kwargs for Unipile (chat_id, account_id). Ignored by WhatsApp."""
    kwargs: dict = {}
    if getattr(msg, "chat_id", None) and getattr(msg, "account_id", None):
        kwargs["chat_id"] = msg.chat_id
        kwargs["account_id"] = msg.account_id
    return kwargs


async def process_whatsapp_message(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
) -> None:
    """
    Process one incoming WhatsApp message.
    - text/audio: transcribe (if audio), extract, create memo, send summary + buttons
    - button: handle approve / add-fields
    """
    if not wa_client.is_configured():
        logger.warning(
            "⚠️ Messaging client not configured, skipping",
            extra=log_domain(DOMAIN_WHATSAPP, "client_not_configured", message_id=msg.message_id, from_phone=msg.from_phone),
        )
        return

    user_id = await lookup_user_by_phone(supabase, msg.from_phone)
    if not user_id:
        logger.info(
            "⚠️ User not found by phone, sending UNKNOWN_USER_MSG",
            extra=log_domain(DOMAIN_WHATSAPP, "lookup_user", message_id=msg.message_id, from_phone=msg.from_phone),
        )
        await wa_client.send_text(msg.from_phone, UNKNOWN_USER_MSG, **_client_kwargs(msg))
        return

    if msg.type == "button":
        logger.info(
            "📱 Processing button reply",
            extra=log_domain(DOMAIN_WHATSAPP, "button_handled", message_id=msg.message_id, from_phone=msg.from_phone, button_id=msg.button_id),
        )
        await _handle_button_reply(supabase, msg, wa_client, user_id)
        return

    # Text message: check conversation context for intent (approve/add) vs new extraction
    chat_id = getattr(msg, "chat_id", None)
    account_id = getattr(msg, "account_id", None)
    conv_svc = ConversationService(supabase)
    intent_svc = IntentService()

    if msg.type == "text" and chat_id and account_id:
        conv = conv_svc.get_or_create_conversation(chat_id, account_id, user_id)
        if conv:
            conv_svc.add_message(conv.id, "inbound", msg.text or "", "text", {"unipile_message_id": msg.message_id})
            state = conv_svc.get_state(conv.id)
            if state and conv_svc.is_state_expired(state):
                state = None
            # Deal choice: parse 1/2/3 before intent resolution
            if state and state.state == "waiting_deal_choice" and state.pending_memo_id and state.pending_artifact_ids:
                choice = _parse_deal_choice(msg.text or "")
                if choice is not None:
                    opts = state.pending_artifact_ids.get("deal_options") or []
                    new_idx = state.pending_artifact_ids.get("new_deal_index", len(opts) + 1)
                    lookup_svc = DealLookupService(supabase)
                    deal_id, is_new_deal = lookup_svc.resolve_choice(choice, opts, new_idx)
                    payload = ApproveMemoRequest(deal_id=deal_id, is_new_deal=is_new_deal)
                    try:
                        result = await approve_memo_core(supabase, str(state.pending_memo_id), user_id, payload)
                        done_msg = "Done! Your CRM has been updated."
                        if getattr(result, "deal_url", None):
                            done_msg += f"\n\n{result.deal_url}"
                        conv_svc.set_state(conv.id, "idle")
                        conv_svc.add_message(conv.id, "outbound", done_msg, "text")
                        await wa_client.send_text(msg.from_phone, done_msg, **_client_kwargs(msg))
                    except ValueError as e:
                        await wa_client.send_text(msg.from_phone, f"Could not update CRM: {e}", **_client_kwargs(msg))
                    return
                await wa_client.send_text(
                    msg.from_phone,
                    "Reply with a number to choose (e.g. 1 or 2).",
                    **_client_kwargs(msg),
                )
                return
            if state and state.state == "waiting_approval" and state.pending_memo_id:
                # Resolve intent and handle
                resolved = await intent_svc.resolve(
                    text=(msg.text or "").strip(),
                    state=state.state,
                    pending_memo_id=str(state.pending_memo_id),
                    messages=conv_svc.get_last_messages(conv.id, 10),
                )
                if resolved.intent in ("approve", "add_fields", "reject") and resolved.memo_id:
                    await _handle_intent_reply(supabase, msg, wa_client, user_id, conv_svc, conv.id, resolved)
                    return
                if resolved.intent == "crm_update":
                    await wa_client.send_text(
                        msg.from_phone,
                        "I'll add that to your CRM. Full support coming soon—for now, reply 1 to approve with current extraction.",
                        **_client_kwargs(msg),
                    )
                    return
                if resolved.intent == "unclear":
                    await wa_client.send_text(
                        msg.from_phone,
                        "Sorry, I didn't understand. Reply 1 to approve, 2 to add fields.",
                        **_client_kwargs(msg),
                    )
                    return
            # State is idle or no pending memo - user may have said "approve" etc.
            norm = _normalize(msg.text or "")
            if norm in APPROVE_PATTERNS or norm in ADD_PATTERNS or norm in REJECT_PATTERNS:
                await wa_client.send_text(
                    msg.from_phone,
                    "No pending extraction. Send a voice memo to get started.",
                    **_client_kwargs(msg),
                )
                return

    audio_url: Optional[str] = None
    if msg.type == "text":
        transcript = msg.text or ""
        logger.info(
            "📱 Processing text message",
            extra=log_domain(DOMAIN_WHATSAPP, "text_message", message_id=msg.message_id, from_phone=msg.from_phone, user_id=user_id, text_len=len(transcript)),
        )
    elif msg.type == "audio" and msg.audio_id:
        logger.info(
            "🎙️ Processing audio message",
            extra=log_domain(DOMAIN_WHATSAPP, "transcribe_started", message_id=msg.message_id, from_phone=msg.from_phone, user_id=user_id),
        )
        transcript, audio_url = await _transcribe_audio(
            supabase, wa_client, msg, user_id
        )
        if not transcript:
            logger.warning(
                "❌ Audio transcription failed",
                extra=log_domain(DOMAIN_WHATSAPP, "transcribe_failed", message_id=msg.message_id, from_phone=msg.from_phone),
            )
            await wa_client.send_text(
                msg.from_phone,
                "Sorry, I couldn't transcribe the audio. Please try again or send a text message.",
                **_client_kwargs(msg),
            )
            return
    else:
        logger.info(
            "⚠️ Unsupported message type",
            extra=log_domain(DOMAIN_WHATSAPP, "unsupported_type", message_id=msg.message_id, from_phone=msg.from_phone, msg_type=msg.type),
        )
        await wa_client.send_text(
            msg.from_phone,
            "I only process voice notes and text. Please send one of those.",
            **_client_kwargs(msg),
        )
        return

    if len(transcript.strip()) < 10:
        logger.info(
            "⚠️ Transcript too short",
            extra=log_domain(DOMAIN_WHATSAPP, "transcript_too_short", message_id=msg.message_id, from_phone=msg.from_phone, transcript_len=len(transcript)),
        )
        await wa_client.send_text(
            msg.from_phone,
            "The message was too short to extract CRM data. Please send a longer voice note or text.",
            **_client_kwargs(msg),
        )
        return

    conversation_id: Optional[str] = None
    chat_id = getattr(msg, "chat_id", None)
    account_id = getattr(msg, "account_id", None)
    if chat_id and account_id:
        conv_svc_for_create = ConversationService(supabase)
        conv = conv_svc_for_create.get_or_create_conversation(chat_id, account_id, user_id)
        if conv:
            conversation_id = str(conv.id)

    memo_id, extraction = await _extract_and_create_memo(
        supabase, user_id, transcript, msg.message_id, audio_url, conversation_id
    )
    if not memo_id:
        logger.warning(
            "❌ Memo creation failed",
            extra=log_domain(DOMAIN_WHATSAPP, "memo_creation_failed", message_id=msg.message_id, from_phone=msg.from_phone),
        )
        await wa_client.send_text(
            msg.from_phone,
            "Something went wrong processing your message. Please try again.",
            **_client_kwargs(msg),
        )
        return

    logger.info(
        "✅ Memo created, sending extraction summary",
        extra=log_domain(DOMAIN_WHATSAPP, "buttons_sent", message_id=msg.message_id, from_phone=msg.from_phone, memo_id=memo_id),
    )

    # Deal lookup (Option C): branch on matches
    lookup_svc = DealLookupService(supabase)
    lookup_result = await lookup_svc.run_lookup(extraction, user_id)

    # Fetch config and field specs for proposed updates section
    allowed_fields: Optional[list[str]] = None
    field_specs: Optional[list[dict]] = None
    try:
        config_svc = CRMConfigurationService(supabase)
        config = await config_svc.get_configuration(user_id)
        allowed_fields = (
            config.allowed_deal_fields
            if config
            else ["dealname", "amount", "description", "closedate"]
        )
        field_specs = await get_field_specs(supabase, user_id)
    except Exception:
        allowed_fields = ["dealname", "amount", "description", "closedate"]

    summary = _format_extraction_summary(extraction, allowed_fields, field_specs)

    if lookup_result.action == "create_new":
        # No disambiguation: summary + approve/add buttons
        if conversation_id and chat_id and account_id:
            conv_svc_for_send = ConversationService(supabase)
            conv = conv_svc_for_send.get_conversation_by_chat_id(chat_id)
            if conv:
                conv_svc_for_send.add_message(
                    conv.id, "outbound", summary,
                    "extraction_summary", {"memo_id": memo_id},
                )
                conv_svc_for_send.set_state(conv.id, "waiting_approval", pending_memo_id=memo_id)
        buttons = [
            {"id": "1", "title": "Approve"},
            {"id": "2", "title": "Add fields"},
        ]
        await wa_client.send_interactive_buttons(
            msg.from_phone, summary, buttons, **_client_kwargs(msg)
        )
    else:
        # confirm_one or disambiguate: summary + deal choice message
        full_msg = summary + "\n\n" + (lookup_result.message or "")
        if conversation_id and chat_id and account_id:
            conv_svc_for_send = ConversationService(supabase)
            conv = conv_svc_for_send.get_conversation_by_chat_id(chat_id)
            if conv:
                conv_svc_for_send.add_message(
                    conv.id, "outbound", full_msg,
                    "extraction_summary", {"memo_id": memo_id},
                )
                conv_svc_for_send.set_state(
                    conv.id,
                    "waiting_deal_choice",
                    pending_memo_id=memo_id,
                    pending_artifact_ids={
                        "deal_options": lookup_result.deal_options,
                        "new_deal_index": lookup_result.new_deal_index,
                    },
                )
        await wa_client.send_text(msg.from_phone, full_msg, **_client_kwargs(msg))


async def _transcribe_audio(
    supabase: Client,
    wa_client: MessagingClient,
    msg: IncomingMessage,
    user_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Download audio, transcribe via Speechmatics (bytes), upload to storage for memo. Return (transcript, audio_url)."""
    try:
        audio_bytes, content_type = await wa_client.download_media(msg)
        batch = SpeechmaticsBatchService()
        transcript = await batch.transcribe(
            audio_bytes=audio_bytes,
            content_type=content_type,
            language="es",
            user_id=user_id,
        )
        logger.info(
            "✅ Transcription complete",
            extra=log_domain(DOMAIN_WHATSAPP, "transcribe_complete", message_id=msg.message_id, transcript_len=len(transcript or "")),
        )
        ext = "ogg" if "ogg" in (content_type or "") or "opus" in (content_type or "") else "webm"
        storage = StorageService(supabase)
        audio_url = await storage.upload_audio(
            audio_bytes, user_id, content_type or "audio/ogg", file_extension=ext
        )
        return transcript, audio_url
    except Exception as e:
        logger.exception(
            "❌ Speechmatics batch transcription failed: %s",
            e,
            extra=log_domain(DOMAIN_WHATSAPP, "transcribe_failed", message_id=msg.message_id, error=str(e)),
        )
        return None, None


async def _extract_and_create_memo(
    supabase: Client,
    user_id: str,
    transcript: str,
    whatsapp_message_id: str,
    audio_url: Optional[str],
    conversation_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[MemoExtraction]]:
    """Extract, create memo, return (memo_id, extraction)."""
    try:
        logger.info(
            "📝 Extract and create memo started",
            extra=log_domain(DOMAIN_WHATSAPP, "extract_started", whatsapp_message_id=whatsapp_message_id, transcript_len=len(transcript)),
        )
        idempotent = (
            supabase.table("memos")
            .select("id", "extraction")
            .eq("whatsapp_message_id", whatsapp_message_id)
            .limit(1)
            .execute()
        )
        if idempotent.data:
            logger.info(
                "📋 Memo idempotent hit",
                extra=log_domain(DOMAIN_WHATSAPP, "memo_idempotent", memo_id=idempotent.data[0]["id"], whatsapp_message_id=whatsapp_message_id),
            )
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
        if conversation_id:
            insert["conversation_id"] = conversation_id
        r = supabase.table("memos").insert(insert).execute()
        if not r.data:
            return None, None
        memo_id = r.data[0]["id"]
        logger.info(
            "✅ Memo created",
            extra=log_domain(DOMAIN_WHATSAPP, "memo_created", memo_id=memo_id, whatsapp_message_id=whatsapp_message_id),
        )
        return memo_id, extraction
    except Exception as e:
        logger.exception(
            "❌ Extract and create memo failed: %s",
            e,
            extra=log_domain(DOMAIN_WHATSAPP, "extract_failed", whatsapp_message_id=whatsapp_message_id, error=str(e)),
        )
        return None, None


async def _handle_intent_reply(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
    user_id: str,
    conv_svc: ConversationService,
    conversation_id,
    resolved,
) -> None:
    """Execute resolved intent (approve, add_fields, reject) and update state."""
    kw = _client_kwargs(msg)
    memo_id = resolved.memo_id

    if resolved.intent == "approve":
        try:
            result = await approve_memo_core(supabase, memo_id, user_id)
            done_msg = "Done! Your CRM has been updated."
            if getattr(result, "deal_url", None):
                done_msg += f"\n\n{result.deal_url}"
            conv_svc.set_state(conversation_id, "idle")
            conv_svc.add_message(conversation_id, "outbound", done_msg, "text")
            await wa_client.send_text(msg.from_phone, done_msg, **kw)
        except ValueError as e:
            await wa_client.send_text(msg.from_phone, f"Could not update CRM: {e}", **kw)

    elif resolved.intent == "add_fields":
        conv_svc.set_state(conversation_id, "waiting_add_fields", pending_memo_id=memo_id)
        conv_svc.add_message(
            conversation_id, "outbound",
            "Reply with the fields to add, one per line.\nExample:\ndealname: Acme Corp\namount: 50000",
            "text",
        )
        await wa_client.send_text(
            msg.from_phone,
            "Reply with the fields to add, one per line.\nExample:\ndealname: Acme Corp\namount: 50000",
            **kw,
        )

    elif resolved.intent == "reject":
        try:
            supabase.table("memos").update({"status": "rejected"}).eq("id", memo_id).eq("user_id", user_id).execute()
            conv_svc.set_state(conversation_id, "idle")
            conv_svc.add_message(conversation_id, "outbound", "Extraction rejected.", "text")
            await wa_client.send_text(msg.from_phone, "Extraction rejected. Send a new voice memo when ready.", **kw)
        except Exception:
            await wa_client.send_text(msg.from_phone, "Could not reject. Please try again.", **kw)


async def _handle_button_reply(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
    user_id: str,
) -> None:
    """Handle native button replies (Meta WhatsApp) or legacy approve:uuid/add:uuid."""
    kw = _client_kwargs(msg)
    bid = (msg.button_id or "").strip()
    if bid.startswith("approve:"):
        memo_id = bid[8:].strip()
        if not memo_id:
            await wa_client.send_text(msg.from_phone, "Invalid request. Please try again.", **kw)
            return
        try:
            result = await approve_memo_core(supabase, memo_id, user_id)
            done_msg = "Done! Your CRM has been updated."
            if getattr(result, "deal_url", None):
                done_msg += f"\n\n{result.deal_url}"
            await wa_client.send_text(msg.from_phone, done_msg, **kw)
        except ValueError as e:
            await wa_client.send_text(msg.from_phone, f"Could not update CRM: {e}", **kw)
    elif bid.startswith("add:"):
        memo_id = bid[4:].strip()
        if not memo_id:
            await wa_client.send_text(msg.from_phone, "Invalid request. Please try again.", **kw)
            return
        await wa_client.send_text(
            msg.from_phone,
            "Reply with the fields to add, one per line.\nExample:\ndealname: Acme Corp\namount: 50000",
            **kw,
        )
    else:
        await wa_client.send_text(msg.from_phone, "Unknown action. Please try again.", **kw)
