"""
WhatsApp message processor: orchestrate pipeline and handle button replies.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from supabase import Client

from app.models.approval import ApprovalPreview, DealMatch
from app.models.memo import MemoExtraction, ApproveMemoRequest
from app.services.conversation import ConversationService, IntentService
from app.services.conversation.intent import APPROVE_PATTERNS, ADD_PATTERNS, REJECT_PATTERNS, _normalize
from app.services.crm_providers import AmbiguousPrimaryCRMError, build_crm_provider, resolve_sync_connection
from app.services.extraction import ExtractionService
from app.services.glossary import GlossaryService
from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh
from app.services.memo_approval import approve_memo_core
from app.services.stt_batch import transcribe_bytes
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

logger = logging.getLogger(__name__)

UNKNOWN_USER_MSG = (
    "This WhatsApp number is not linked to a Vocify account. "
    "Ask your admin to add it in Vocify, or sign in at app.getvocify.com and add your phone in Profile."
)


@dataclass
class WhatsAppAccount:
    user_id: str
    profile: dict
    crm_connection: Optional[dict]
    readiness_error: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        return self.readiness_error is None


def _parse_deal_choice(text: str) -> Optional[int]:
    """Parse reply as deal choice number (1, 2, 3...). Returns int or None."""
    s = (text or "").strip()
    if not s:
        return None
    if len(s) > 2:
        m = re.search(r"\b(?:option|opción|deal|use|usar|elige|elije)?\s*(\d{1,2})\b", s, flags=re.I)
        if m:
            return int(m.group(1))
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


def _normalize_phone_e164(phone: Optional[str]) -> Optional[str]:
    """Canonical phone for DB lookup/display safety."""
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    return f"+{digits}"


def _message_provider(msg: IncomingMessage) -> str:
    """Return provider name for transport-specific behavior."""
    provider = (getattr(msg, "provider", None) or "").strip().lower()
    if provider:
        return provider
    return "unipile" if getattr(msg, "chat_id", None) and getattr(msg, "account_id", None) else "meta"


def _session_ids(msg: IncomingMessage) -> tuple[str, str]:
    """
    Stable conversation identity across Meta and Unipile.

    Unipile gives chat/account IDs. Meta does not, so the normalized phone becomes
    the session thread key. This lets text replies/buttons work on both providers.
    """
    provider = _message_provider(msg)
    phone = _normalize_phone(msg.from_phone)
    chat_id = getattr(msg, "chat_id", None) or f"phone:{phone}"
    account_id = getattr(msg, "account_id", None) or provider
    return chat_id, account_id


def _get_or_create_session(
    conv_svc: ConversationService,
    msg: IncomingMessage,
    user_id: str,
):
    chat_id, account_id = _session_ids(msg)
    return conv_svc.get_or_create_conversation(
        chat_id=chat_id,
        account_id=account_id,
        user_id=user_id,
        channel="whatsapp",
    )


def _metadata_for_message(msg: IncomingMessage) -> dict:
    return {
        "provider": _message_provider(msg),
        "provider_message_id": msg.message_id,
        "chat_id": getattr(msg, "chat_id", None),
        "account_id": getattr(msg, "account_id", None),
    }


def _default_deal_fields(provider: str) -> list[str]:
    if provider == "salesforce":
        return ["Name", "Amount", "CloseDate", "StageName", "Description"]
    return ["dealname", "amount", "description", "closedate"]


def _default_contact_fields(provider: str) -> list[str]:
    if provider == "salesforce":
        return ["FirstName", "LastName", "Email", "Phone"]
    return ["firstname", "lastname", "email", "phone", "jobtitle"]


def _default_company_fields(provider: str) -> list[str]:
    if provider == "salesforce":
        return ["Name"]
    return ["name", "domain"]


def _default_line_item_fields(provider: str) -> list[str]:
    if provider == "salesforce":
        return []
    return ["name", "quantity", "price"]


_OBJECT_PREVIEW_ORDER = ("deals", "contacts", "companies", "line_items", "task")
_OBJECT_PREVIEW_LABELS = {
    "deals": "Deal",
    "contacts": "Contact",
    "companies": "Company",
    "line_items": "Line items",
    "task": "Tasks",
}


def _crm_display_name(provider: Optional[str]) -> str:
    p = (provider or "").lower()
    if p == "salesforce":
        return "Salesforce"
    if p == "hubspot":
        return "HubSpot"
    return "CRM"


def _format_amount(amount: Any) -> str:
    if amount is None or amount == "":
        return "no amount"
    try:
        val = float(str(amount).replace(",", "").replace("€", "").strip())
        return f"€{val:,.0f}".replace(",", ".")
    except Exception:
        return str(amount)


def _shorten(value: Any, limit: int = 90) -> str:
    s = "" if value is None else str(value).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 3].rstrip() + "..."


def _format_property_value_for_display(field_name: str, value: Any, extraction: MemoExtraction) -> str:
    """Format a property value for WhatsApp display (like frontend)."""
    if value is None or value == "" or (isinstance(value, str) and not value.strip()):
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

# One emoji per section — scan-friendly on mobile, easy to swap per channel later.
_SECTION_DEAL = "📋"
_SECTION_CONTACT = "👤"
_SECTION_INSIGHTS = "💡"
_SECTION_CRM = "📝"


def _is_value_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    if isinstance(val, list) and len(val) == 0:
        return True
    return False


def _format_whatsapp_section(emoji: str, title: str, bullet_lines: list[str]) -> str:
    if not bullet_lines:
        return ""
    bullets = "\n".join(f"• {line}" for line in bullet_lines)
    return f"{emoji} {title}\n{bullets}"


def _get_proposed_updates_display(
    extraction: MemoExtraction,
    allowed_fields: list[str],
    field_specs: Optional[list[dict]] = None,
    *,
    omit_empty: bool = True,
    allowed_contact_fields: Optional[list[str]] = None,
    allowed_company_fields: Optional[list[str]] = None,
    allowed_line_item_fields: Optional[list[str]] = None,
) -> list[tuple[str, str, str]]:
    """Return (object_type, label, display_value) for allowlisted extracted properties."""
    from app.services.hubspot.object_properties import (
        company_properties_from_extraction,
        contact_properties_from_extraction,
        line_items_from_extraction,
    )

    allowed = list(allowed_fields or [])
    labels = {
        (s.get("object_type") or "deals", s["name"]): s["label"]
        for s in (field_specs or [])
        if s.get("name") and s.get("label")
    }

    def _label(object_type: str, name: str) -> str:
        return labels.get((object_type, name), name.replace("_", " ").title())

    def _value(name: str, val: Any) -> str:
        if _is_value_empty(val):
            return NOT_SET
        return _format_property_value_for_display(name, val, extraction)

    skip_raw = {
        "summary", "painPoints", "nextSteps", "objections", "decisionMakers",
        "confidence", "contactName", "companyName", "contactEmail", "contactPhone",
        "contactRole", "contact_properties", "company_properties", "line_items",
        "deal_currency_code",
    }
    read_only = {
        "hs_closed_amount", "hs_notes_next_activity", "hs_next_step",
        "hs_lastmodifieddate", "hs_createdate", "hs_object_id",
    }

    raw = extraction.raw_extraction or {}
    values: dict[str, Any] = {}
    if "dealname" in allowed:
        values["dealname"] = raw.get("dealname") or (
            f"{extraction.companyName} Deal" if extraction.companyName
            else f"{extraction.contactName} Deal" if extraction.contactName
            else "New Deal"
        )
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

    updates: list[tuple[str, str, str]] = []
    for name in allowed:
        if name in read_only:
            continue
        val = values.get(name)
        display = _value(name, val)
        if omit_empty and display == NOT_SET:
            continue
        updates.append(("deals", _label("deals", name), display))

    contact_allow = allowed_contact_fields if allowed_contact_fields is not None else []
    if contact_allow:
        contact_props = contact_properties_from_extraction(
            extraction, allowed_fields=contact_allow
        )
        for name, val in contact_props.items():
            display = _value(name, val)
            if omit_empty and display == NOT_SET:
                continue
            updates.append(("contacts", _label("contacts", name), display))

    company_allow = allowed_company_fields if allowed_company_fields is not None else []
    if company_allow:
        company_props = company_properties_from_extraction(
            extraction, allowed_fields=company_allow
        )
        for name, val in company_props.items():
            if name == "name":
                continue
            display = _value(name, val)
            if omit_empty and display == NOT_SET:
                continue
            updates.append(("companies", _label("companies", name), display))

    line_allow = allowed_line_item_fields if allowed_line_item_fields is not None else []
    for i, item in enumerate(line_items_from_extraction(extraction, allowed_fields=line_allow)):
        name = item.get("name") or f"Line item {i + 1}"
        qty = item.get("quantity", "")
        price = item.get("price", "")
        summary = f"{name}"
        if qty != "" or price != "":
            summary = f"{name} · qty {qty} · {price}"
        updates.append(("line_items", name, summary))

    return updates


def _format_extraction_summary(
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]] = None,
    field_specs: Optional[list[dict]] = None,
    *,
    allowed_contact_fields: Optional[list[str]] = None,
    allowed_company_fields: Optional[list[str]] = None,
    allowed_line_item_fields: Optional[list[str]] = None,
) -> str:
    """Format extracted fields for WhatsApp: section headers, bullets, no empty CRM rows."""
    sections: list[str] = []

    deal_lines: list[str] = []
    if extraction.companyName:
        deal_lines.append(f"Company: {extraction.companyName}")
    s = _format_whatsapp_section(_SECTION_DEAL, "Deal", deal_lines)
    if s:
        sections.append(s)

    contact_lines: list[str] = []
    if extraction.contactName:
        contact_lines.append(f"Name: {extraction.contactName}")
    if extraction.contactRole:
        contact_lines.append(f"Role: {extraction.contactRole}")
    if extraction.contactEmail:
        contact_lines.append(f"Email: {extraction.contactEmail}")
    if extraction.contactPhone:
        contact_lines.append(f"Phone: {extraction.contactPhone}")
    s = _format_whatsapp_section(_SECTION_CONTACT, "Contact", contact_lines)
    if s:
        sections.append(s)

    insight_lines: list[str] = []
    if extraction.summary:
        sm = extraction.summary[:300] + ("..." if len(extraction.summary) > 300 else "")
        insight_lines.append(f"Summary: {sm}")
    if extraction.painPoints:
        insight_lines.append(f"Pain points: {', '.join(extraction.painPoints[:3])}")
    if extraction.nextSteps:
        insight_lines.append(f"Next steps: {', '.join(extraction.nextSteps[:3])}")
    if extraction.competitors:
        insight_lines.append(f"Competitors: {', '.join(extraction.competitors[:3])}")
    if extraction.objections:
        insight_lines.append(f"Objections: {', '.join(extraction.objections[:2])}")
    s = _format_whatsapp_section(_SECTION_INSIGHTS, "Insights", insight_lines)
    if s:
        sections.append(s)

    # Infer object allowlists from field_specs when callers only pass specs
    if field_specs and allowed_contact_fields is None:
        allowed_contact_fields = [
            s["name"] for s in field_specs if s.get("object_type") == "contacts" and s.get("name")
        ]
    if field_specs and allowed_company_fields is None:
        allowed_company_fields = [
            s["name"] for s in field_specs if s.get("object_type") == "companies" and s.get("name")
        ]
    if field_specs and allowed_line_item_fields is None:
        allowed_line_item_fields = [
            s["name"] for s in field_specs if s.get("object_type") == "line_items" and s.get("name")
        ]
    if field_specs and not allowed_fields:
        allowed_fields = [
            s["name"] for s in field_specs
            if (s.get("object_type") or "deals") == "deals" and s.get("name")
        ]

    updates = _get_proposed_updates_display(
        extraction,
        allowed_fields or [],
        field_specs,
        omit_empty=True,
        allowed_contact_fields=allowed_contact_fields,
        allowed_company_fields=allowed_company_fields,
        allowed_line_item_fields=allowed_line_item_fields,
    )
    if updates:
        by_object: dict[str, list[str]] = {}
        for object_type, label, val in updates:
            by_object.setdefault(object_type, []).append(f"{label}: {val}")
        for object_type in _OBJECT_PREVIEW_ORDER:
            lines = by_object.get(object_type)
            if not lines:
                continue
            title = _OBJECT_PREVIEW_LABELS.get(object_type, object_type)
            block = _format_whatsapp_section(_SECTION_CRM, f"{title} fields", lines)
            if block:
                sections.append(block)

    if not sections:
        return "I couldn't extract structured CRM fields from this. You can still approve to save the transcript."

    body = "Here's what I captured:\n\n" + "\n\n".join(sections)
    return body + "\n\nShould I update your CRM?"


def _format_match_line(match: DealMatch, idx: int) -> str:
    details = []
    if match.company_name:
        details.append(match.company_name)
    if match.stage:
        details.append(str(match.stage).replace("_", " "))
    if match.amount:
        details.append(_format_amount(match.amount))
    if match.last_updated:
        details.append(f"updated {_shorten(match.last_updated, 16)}")
    meta = " · ".join(details) if details else "no extra details"
    return f"*{idx}.* {match.deal_name}\n   {meta}\n   Match: {_shorten(match.match_reason, 80)}"


def _format_deal_choices(matches: list[DealMatch], extraction: MemoExtraction) -> str:
    subject = extraction.companyName or extraction.contactName or "this note"
    lines = [
        f"I found several possible CRM records for *{subject}*.",
        "Choose where this update should go:",
        "",
    ]
    lines.extend(_format_match_line(m, i + 1) for i, m in enumerate(matches))
    lines.append(f"*{len(matches) + 1}.* Create a new deal")
    lines.append("")
    lines.append(f"Reply with *1-{len(matches) + 1}*.")
    return "\n".join(lines)


def _format_preview_message(
    preview: ApprovalPreview,
    crm_name: str,
    *,
    selected_by_ai: bool = False,
) -> str:
    target = "a new deal"
    target_detail = ""
    if preview.selected_deal:
        target = preview.selected_deal.deal_name
        parts = []
        if preview.selected_deal.stage:
            parts.append(str(preview.selected_deal.stage).replace("_", " "))
        if preview.selected_deal.amount:
            parts.append(_format_amount(preview.selected_deal.amount))
        if preview.selected_deal.match_reason:
            parts.append(_shorten(preview.selected_deal.match_reason, 60))
        target_detail = " · ".join(parts)

    lines = ["*Captured update*"]
    if selected_by_ai and preview.selected_deal:
        lines.append(f"I think this belongs to *{target}*.")
    else:
        lines.append(f"Target: *{target}*")
    if target_detail:
        lines.append(target_detail)

    updates = [
        u for u in (preview.proposed_updates or [])
        if u.new_value and str(u.new_value).strip()
    ]
    if updates:
        lines.append("")
        lines.append("*I will update:*")
        by_object: dict[str, list] = {}
        for update in updates:
            obj = update.object_type or "deals"
            by_object.setdefault(obj, []).append(update)
        shown = 0
        max_items = 8
        for object_type in _OBJECT_PREVIEW_ORDER:
            group = by_object.get(object_type) or []
            if not group:
                continue
            lines.append(f"_{_OBJECT_PREVIEW_LABELS.get(object_type, object_type)}_")
            for update in group:
                if shown >= max_items:
                    break
                label = update.field_label or update.field_name
                # Strip redundant "Contact · " / "Company · " prefixes if present
                for prefix in ("Contact · ", "Company · ", "Line item · "):
                    if label.startswith(prefix):
                        label = label[len(prefix):]
                        break
                lines.append(f"• *{label}:* {_shorten(update.new_value, 100)}")
                shown += 1
            if shown >= max_items:
                break
        remaining = len(updates) - shown
        if remaining > 0:
            lines.append(f"• +{remaining} more fields")
    else:
        lines.append("")
        lines.append("I did not find confident field updates. I can still save the transcript as a CRM note.")

    lines.append("")
    lines.append(f"Reply *1* to update {crm_name}, *2* to choose another deal, or *3* to edit fields.")
    return "\n".join(lines)


def _format_done_message(result: Any, crm_name: str) -> str:
    deal_url = getattr(result, "deal_url", None)
    deal_name = getattr(result, "deal_name", None)
    if deal_url:
        title = f"Done. Updated *{deal_name or 'the deal'}* in {crm_name}."
        return f"{title}\n\n{deal_url}"
    if getattr(result, "status", None) == "approved":
        return "Done. I saved this memo, but no connected CRM was available to update."
    return f"Done. {crm_name} has been updated."


def _parse_field_edits(text: str) -> dict[str, str]:
    """
    Parse lightweight natural corrections.

    Supports:
    - amount: 50000
    - close date: 2026-06-15
    - change amount to 50k
    - next step send proposal Friday
    """
    edits: dict[str, str] = {}
    cleaned = (text or "").strip()
    if not cleaned:
        return edits

    for raw_line in cleaned.splitlines():
        line = raw_line.strip(" -•\t")
        if not line:
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            if key.strip() and value.strip():
                edits[key.strip().lower()] = value.strip()

    lower = cleaned.lower()
    amount = re.search(r"(?:amount|importe|valor|deal amount)\s+(?:is|to|=|de)?\s*([€$]?\s?\d[\d.,]*(?:\s?k)?)", lower)
    if amount and "amount" not in edits:
        edits["amount"] = amount.group(1).strip()
    close = re.search(r"(?:close date|closedate|fecha de cierre)\s+(?:is|to|=|de)?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", lower)
    if close and "close date" not in edits:
        edits["close date"] = close.group(1).strip()
    next_step = re.search(r"(?:next step|next action|siguiente paso)\s*(?:is|:|=|to)?\s+(.+)", cleaned, flags=re.I)
    if next_step and "next step" not in edits:
        edits["next step"] = next_step.group(1).strip()
    return edits


def _field_edits_from_params(params: Optional[dict]) -> dict[str, str]:
    """Normalize LLM intent params into the same edit map as text parsing."""
    if not isinstance(params, dict):
        return {}
    if "property" in params and "value" in params:
        return {str(params["property"]).strip().lower(): str(params["value"]).strip()}
    edits: dict[str, str] = {}
    for key, value in params.items():
        if value is None or isinstance(value, (dict, list)):
            continue
        edits[str(key).strip().lower()] = str(value).strip()
    return {k: v for k, v in edits.items() if k and v}


def _parse_amount_value(value: str) -> Optional[float]:
    if not value:
        return None
    raw = value.strip().lower().replace("€", "").replace("$", "").replace(" ", "")
    multiplier = 1
    if raw.endswith("k"):
        multiplier = 1000
        raw = raw[:-1]
    if "." in raw and "," not in raw and len(raw.rsplit(".", 1)[-1]) == 3:
        raw = raw.replace(".", "")
    elif "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def _apply_field_edits(
    extraction_data: dict,
    edits: dict[str, str],
    field_specs: Optional[list[dict]] = None,
) -> dict:
    """Merge user text corrections into the stored extraction without writing CRM."""
    updated = dict(extraction_data or {})
    raw = dict(updated.get("raw_extraction") or {})
    specs = field_specs or []
    label_to_name = {
        str(s.get("label") or "").strip().lower(): s.get("name")
        for s in specs
        if s.get("name") and s.get("label")
    }
    name_set = {str(s.get("name")) for s in specs if s.get("name")}

    for key, value in edits.items():
        k = key.strip().lower()
        if not k or value is None:
            continue
        if k in ("amount", "importe", "valor", "deal amount", "opportunity amount"):
            parsed = _parse_amount_value(value)
            if parsed is not None:
                updated["dealAmount"] = parsed
                raw["amount"] = parsed
                raw["Amount"] = parsed
            continue
        if k in ("close date", "closedate", "fecha de cierre"):
            updated["closeDate"] = value
            raw["closedate"] = value
            raw["CloseDate"] = value
            continue
        if k in ("company", "company name", "deal", "deal name", "opportunity", "name"):
            updated["companyName"] = value
            raw["dealname"] = value
            raw["Name"] = value
            continue
        if k in ("stage", "deal stage", "pipeline stage", "fase"):
            updated["dealStage"] = value
            raw["dealstage"] = value
            raw["StageName"] = value
            continue
        if k in ("summary", "description", "nota", "note"):
            updated["summary"] = value
            raw["description"] = value
            raw["Description"] = value
            continue
        if k in ("next step", "next action", "siguiente paso", "task"):
            updated["nextSteps"] = [value]
            raw["hs_next_step"] = value
            continue

        field_name = label_to_name.get(k) or (key if key in name_set else None)
        if field_name:
            raw[field_name] = value

    updated["raw_extraction"] = raw
    return updated


async def lookup_profile_by_phone(supabase: Client, phone: str) -> Optional[dict]:
    """Return user profile if sender phone matches canonical user_profiles.phone."""
    canonical = _normalize_phone_e164(phone)
    if not canonical:
        return None
    r = (
        supabase.table("user_profiles")
        .select("*")
        .eq("phone", canonical)
        .limit(1)
        .execute()
    )
    if r.data and len(r.data) > 0:
        return r.data[0]
    return None


async def lookup_user_by_phone(supabase: Client, phone: str) -> Optional[str]:
    """Return user_id if phone is registered, else None."""
    profile = await lookup_profile_by_phone(supabase, phone)
    return str(profile["id"]) if profile and profile.get("id") else None


def _format_account_readiness_error(profile: dict, reason: str) -> str:
    name = (profile.get("full_name") or "").strip()
    prefix = f"Hi {name.split()[0]}, " if name else ""
    if reason == "missing_company":
        return (
            f"{prefix}I found your Vocify account, but your company name is missing. "
            "Add it in Profile before using WhatsApp updates."
        )
    if reason == "no_crm":
        return (
            f"{prefix}I found your Vocify account, but no CRM is connected yet. "
            "Connect HubSpot or Salesforce in Integrations first."
        )
    if reason == "ambiguous_crm":
        return (
            f"{prefix}you have multiple CRMs connected. Choose a primary CRM in Integrations "
            "before sending WhatsApp updates."
        )
    if reason == "crm_not_connected":
        return (
            f"{prefix}your primary CRM is not connected anymore. Reconnect it in Integrations "
            "before using WhatsApp updates."
        )
    return f"{prefix}your Vocify account is not ready for WhatsApp updates yet. Please check Profile and Integrations."


async def resolve_whatsapp_account(supabase: Client, phone: str) -> Optional[WhatsAppAccount]:
    """
    Authorize a WhatsApp sender against user_profiles and verify account readiness.

    This prevents random numbers from triggering extraction/CRM work and gives
    registered users a precise setup message when their account is incomplete.
    """
    profile = await lookup_profile_by_phone(supabase, phone)
    if not profile:
        return None

    user_id = str(profile["id"])
    if not (profile.get("company_name") or "").strip():
        return WhatsAppAccount(
            user_id=user_id,
            profile=profile,
            crm_connection=None,
            readiness_error=_format_account_readiness_error(profile, "missing_company"),
        )

    try:
        conn = resolve_sync_connection(supabase, user_id)
    except AmbiguousPrimaryCRMError:
        return WhatsAppAccount(
            user_id=user_id,
            profile=profile,
            crm_connection=None,
            readiness_error=_format_account_readiness_error(profile, "ambiguous_crm"),
        )

    if not conn:
        return WhatsAppAccount(
            user_id=user_id,
            profile=profile,
            crm_connection=None,
            readiness_error=_format_account_readiness_error(profile, "no_crm"),
        )
    if conn.get("status") != "connected":
        return WhatsAppAccount(
            user_id=user_id,
            profile=profile,
            crm_connection=conn,
            readiness_error=_format_account_readiness_error(profile, "crm_not_connected"),
        )

    return WhatsAppAccount(user_id=user_id, profile=profile, crm_connection=conn)


async def get_field_specs(supabase: Client, user_id: str) -> Optional[list[dict]]:
    """Get curated field specs for extraction."""
    try:
        conn = resolve_sync_connection(supabase, user_id)
        if not conn:
            return None
        if conn.get("provider") == "hubspot":
            conn = await ensure_hubspot_connection_tokens_fresh(supabase, conn)
        config_svc = CRMConfigurationService(supabase)
        config = await config_svc.get_configuration(user_id, connection_id=str(conn["id"]))
        allowed = config.allowed_deal_fields if config else None
        if not allowed:
            return None
        provider = build_crm_provider(supabase, conn)
        get_specs = getattr(provider, "get_extraction_field_specs", None)
        if callable(get_specs):
            return await get_specs(
                allowed_deal_fields=config.allowed_deal_fields,
                allowed_contact_fields=config.allowed_contact_fields,
                allowed_company_fields=config.allowed_company_fields,
                allowed_line_item_fields=getattr(config, "allowed_line_item_fields", None),
            )
        return await provider.get_curated_field_specs(allowed)
    except Exception:
        return None


def _client_kwargs(msg: IncomingMessage) -> dict:
    """Extra kwargs for Unipile (chat_id, account_id). Ignored by WhatsApp."""
    kwargs: dict = {}
    if getattr(msg, "chat_id", None) and getattr(msg, "account_id", None):
        kwargs["chat_id"] = msg.chat_id
        kwargs["account_id"] = msg.account_id
    return kwargs


async def _load_memo_extraction(supabase: Client, memo_id: str, user_id: str) -> tuple[dict, str]:
    r = (
        supabase.table("memos")
        .select("extraction,transcript")
        .eq("id", memo_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not r.data or not r.data.get("extraction"):
        raise ValueError("Memo extraction not available")
    return r.data["extraction"], r.data.get("transcript") or ""


async def _crm_context(supabase: Client, user_id: str):
    conn = resolve_sync_connection(supabase, user_id)
    if not conn:
        return None, None, None, [], [], [], [], None
    if conn.get("provider") == "hubspot":
        # Deal matching/preview here hit the HubSpot API directly (unlike the final
        # approve step, which refreshes on its own) - a WhatsApp conversation can
        # easily outlive the ~30min OAuth token lifetime, so refresh proactively
        # instead of surfacing an auth error mid-conversation.
        try:
            conn = await ensure_hubspot_connection_tokens_fresh(supabase, conn)
        except ValueError:
            logger.warning("HubSpot token refresh failed in WhatsApp flow for user %s", user_id)
    provider = build_crm_provider(supabase, conn)
    provider_name = (conn.get("provider") or "").lower()
    config = await CRMConfigurationService(supabase).get_configuration(
        user_id,
        connection_id=str(conn["id"]),
    )
    allowed_fields = (
        list(config.allowed_deal_fields)
        if config and config.allowed_deal_fields
        else _default_deal_fields(provider_name)
    )
    if provider_name == "hubspot":
        from app.services.hubspot.deal_field_names import normalize_hubspot_allowed_deal_fields
        allowed_fields = normalize_hubspot_allowed_deal_fields(allowed_fields)

    allowed_contact_fields = (
        list(config.allowed_contact_fields)
        if config and config.allowed_contact_fields is not None
        else _default_contact_fields(provider_name)
    )
    allowed_company_fields = (
        list(config.allowed_company_fields)
        if config and config.allowed_company_fields is not None
        else _default_company_fields(provider_name)
    )
    allowed_line_item_fields = (
        list(getattr(config, "allowed_line_item_fields", None) or [])
        if config
        else _default_line_item_fields(provider_name)
    )
    pipeline_id = config.default_pipeline_id if config else None
    return (
        provider,
        conn,
        config,
        allowed_fields,
        allowed_contact_fields,
        allowed_company_fields,
        allowed_line_item_fields,
        pipeline_id,
    )


async def _find_candidate_deals(
    supabase: Client,
    user_id: str,
    extraction: MemoExtraction,
) -> tuple[list[DealMatch], Optional[str], Optional[str]]:
    try:
        provider, conn, _config, *_rest = await _crm_context(supabase, user_id)
        pipeline_id = _rest[-1] if _rest else None
    except AmbiguousPrimaryCRMError:
        raise ValueError("Multiple CRMs are connected. Choose a primary CRM in Integrations first.")
    if not provider or not conn:
        return [], None, None
    matches = await provider.find_matching_deals(extraction, limit=5, pipeline_id=pipeline_id)
    return matches, str(conn["id"]), (conn.get("provider") or "").lower()


async def _build_preview_for_selection(
    supabase: Client,
    user_id: str,
    memo_id: str,
    extraction_data: Optional[dict] = None,
    selected_deal_id: Optional[str] = None,
    is_new_deal: bool = False,
    matched_deals: Optional[list[DealMatch]] = None,
) -> tuple[Optional[ApprovalPreview], str, Optional[str], list[dict]]:
    try:
        (
            provider,
            conn,
            config,
            allowed_fields,
            allowed_contact_fields,
            allowed_company_fields,
            allowed_line_item_fields,
            pipeline_id,
        ) = await _crm_context(supabase, user_id)
    except AmbiguousPrimaryCRMError:
        raise ValueError("Multiple CRMs are connected. Choose a primary CRM in Integrations first.")

    if not provider or not conn:
        return None, "CRM", None, []

    stored_extraction, transcript = await _load_memo_extraction(supabase, memo_id, user_id)
    effective_extraction = extraction_data or stored_extraction
    extraction = MemoExtraction(**effective_extraction)
    deal_id = None if is_new_deal else selected_deal_id
    matches = matched_deals or []
    if not deal_id and not is_new_deal:
        matches = await provider.find_matching_deals(extraction, limit=5, pipeline_id=pipeline_id)

    identity = await provider.resolve_identity(
        extraction, limit_deals=5, pipeline_id=pipeline_id
    )
    if identity is None:
        anchor = None
        selected_contact = None
        contact_candidates = []
    else:
        anchor = identity.selected
        selected_contact = anchor.to_contact_match() if anchor else None
        contact_candidates = list(identity.candidates or [])
    if anchor and anchor.deal_matches:
        seen: set[str] = set()
        merged: list = []
        for d in list(anchor.deal_matches) + list(matches):
            if d.deal_id in seen:
                continue
            seen.add(d.deal_id)
            merged.append(d)
        matches = merged[:5]

    create_new = bool(is_new_deal)
    if deal_id:
        create_new = False
    elif create_new:
        pass
    elif selected_contact and anchor and len(anchor.deal_matches) == 1:
        deal_id = anchor.deal_matches[0].deal_id
    elif selected_contact:
        create_new = False
    elif contact_candidates:
        create_new = False
    else:
        create_new = True

    preview = await provider.build_preview(
        memo_id=UUID(str(memo_id)),
        transcript=transcript,
        extraction=extraction,
        matched_deals=matches,
        selected_deal_id=deal_id,
        allowed_fields=allowed_fields,
        allowed_contact_fields=allowed_contact_fields,
        allowed_company_fields=allowed_company_fields,
        allowed_line_item_fields=allowed_line_item_fields,
        default_stage_name=config.default_stage_name if config else None,
        default_pipeline_id=config.default_pipeline_id if config else None,
        default_stage_id=config.default_stage_id if config else None,
        selected_contact=selected_contact,
        contact_candidates=contact_candidates,
        create_new_deal=create_new,
    )
    crm_name = _crm_display_name(conn.get("provider"))
    option_rows = [m.model_dump() for m in matches]
    return preview, crm_name, str(conn["id"]), option_rows


def _high_confidence_match(matches: list[DealMatch]) -> Optional[DealMatch]:
    if not matches:
        return None
    top = matches[0]
    second = matches[1] if len(matches) > 1 else None
    if top.match_confidence >= 0.92 and (
        second is None or top.match_confidence - second.match_confidence >= 0.12
    ):
        return top
    return None


async def _send_preview_for_selection(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
    user_id: str,
    conv_svc: ConversationService,
    conversation_id,
    memo_id: str,
    *,
    selected_deal_id: Optional[str] = None,
    is_new_deal: bool = False,
    extraction_data: Optional[dict] = None,
    matched_deals: Optional[list[DealMatch]] = None,
    selected_by_ai: bool = False,
) -> None:
    preview, crm_name, connection_id, option_rows = await _build_preview_for_selection(
        supabase,
        user_id,
        memo_id,
        extraction_data=extraction_data,
        selected_deal_id=selected_deal_id,
        is_new_deal=is_new_deal,
        matched_deals=matched_deals,
    )
    if not preview:
        text = (
            "*Captured update*\n"
            "I saved the memo, but no CRM is connected yet.\n\n"
            "Reply *1* to mark it reviewed, or connect a CRM in the dashboard first."
        )
        conv_svc.set_state(
            conversation_id,
            "waiting_approval",
            pending_memo_id=memo_id,
            pending_artifact_ids={"crm_connected": False},
        )
        conv_svc.add_message(conversation_id, "outbound", text, "extraction_summary", {"memo_id": memo_id})
        await wa_client.send_text(msg.from_phone, text, **_client_kwargs(msg))
        return

    artifacts = {
        "crm_connected": True,
        "connection_id": connection_id,
        "crm_name": crm_name,
        "selected_deal_id": preview.selected_deal.deal_id if preview.selected_deal else selected_deal_id,
        "is_new_deal": bool(preview.is_new_deal),
        "skip_deal": bool(preview.skip_deal),
        "contact_id": preview.selected_contact.contact_id if preview.selected_contact else None,
        "company_id": preview.selected_contact.company_id if preview.selected_contact else None,
        "deal_options": option_rows,
    }
    conv_svc.set_state(
        conversation_id,
        "waiting_approval",
        pending_memo_id=memo_id,
        pending_artifact_ids=artifacts,
    )
    text = _format_preview_message(preview, crm_name, selected_by_ai=selected_by_ai)
    conv_svc.add_message(conversation_id, "outbound", text, "extraction_summary", {"memo_id": memo_id})
    buttons = [
        {"id": "1", "title": "Update CRM"},
        {"id": "2", "title": "Choose deal"},
        {"id": "3", "title": "Edit fields"},
    ]
    await wa_client.send_interactive_buttons(msg.from_phone, text, buttons, **_client_kwargs(msg))


async def _approve_pending_memo(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
    user_id: str,
    conv_svc: ConversationService,
    conversation_id,
    memo_id: str,
    artifacts: Optional[dict] = None,
) -> None:
    artifacts = artifacts or {}
    payload = ApproveMemoRequest(
        deal_id=artifacts.get("selected_deal_id"),
        is_new_deal=bool(artifacts.get("is_new_deal", False)),
        contact_id=artifacts.get("contact_id"),
        company_id=artifacts.get("company_id"),
        skip_deal=bool(artifacts.get("skip_deal", False)),
    )
    try:
        result = await approve_memo_core(supabase, memo_id, user_id, payload)
        crm_name = artifacts.get("crm_name") or "CRM"
        done_msg = _format_done_message(result, crm_name)
        conv_svc.set_state(conversation_id, "idle")
        conv_svc.add_message(conversation_id, "outbound", done_msg, "text")
        await wa_client.send_text(msg.from_phone, done_msg, **_client_kwargs(msg))
    except ValueError as e:
        await wa_client.send_text(msg.from_phone, f"Could not update CRM: {e}", **_client_kwargs(msg))


async def _handle_deal_choice(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
    user_id: str,
    conv_svc: ConversationService,
    conversation_id,
    state,
) -> bool:
    choice = _parse_deal_choice(msg.text or msg.button_id or "")
    if choice is None or not state.pending_memo_id:
        await wa_client.send_text(msg.from_phone, "Reply with the number of the deal to use.", **_client_kwargs(msg))
        return True

    opts = (state.pending_artifact_ids or {}).get("deal_options") or []
    new_idx = (state.pending_artifact_ids or {}).get("new_deal_index", len(opts) + 1)
    extraction_data = None
    edits = _parse_field_edits(msg.text or "")
    if edits and state.pending_memo_id:
        current_extraction, _transcript = await _load_memo_extraction(supabase, str(state.pending_memo_id), user_id)
        field_specs = await get_field_specs(supabase, user_id)
        extraction_data = _apply_field_edits(current_extraction, edits, field_specs)
        supabase.table("memos").update({"extraction": extraction_data}).eq("id", str(state.pending_memo_id)).eq("user_id", user_id).execute()

    if choice == new_idx:
        await _send_preview_for_selection(
            supabase,
            msg,
            wa_client,
            user_id,
            conv_svc,
            conversation_id,
            str(state.pending_memo_id),
            is_new_deal=True,
            extraction_data=extraction_data,
        )
        return True

    idx = choice - 1
    if 0 <= idx < len(opts):
        deal_id = opts[idx].get("deal_id")
        await _send_preview_for_selection(
            supabase,
            msg,
            wa_client,
            user_id,
            conv_svc,
            conversation_id,
            str(state.pending_memo_id),
            selected_deal_id=deal_id,
            is_new_deal=False,
            matched_deals=[DealMatch(**o) for o in opts],
            extraction_data=extraction_data,
        )
        return True

    await wa_client.send_text(msg.from_phone, "That option is not in the list. Reply with one of the numbers shown.", **_client_kwargs(msg))
    return True


async def _handle_waiting_add_fields(
    supabase: Client,
    msg: IncomingMessage,
    wa_client: MessagingClient,
    user_id: str,
    conv_svc: ConversationService,
    conversation_id,
    state,
) -> bool:
    if not state.pending_memo_id:
        return False
    edits = _parse_field_edits(msg.text or "")
    if not edits:
        await wa_client.send_text(
            msg.from_phone,
            "Send edits as field/value lines, for example:\namount: 50000\nclose date: 2026-06-15\nnext step: send proposal Friday",
            **_client_kwargs(msg),
        )
        return True

    extraction_data, _transcript = await _load_memo_extraction(supabase, str(state.pending_memo_id), user_id)
    field_specs = await get_field_specs(supabase, user_id)
    updated = _apply_field_edits(extraction_data, edits, field_specs)
    supabase.table("memos").update({"extraction": updated}).eq("id", str(state.pending_memo_id)).eq("user_id", user_id).execute()
    artifacts = state.pending_artifact_ids or {}
    await _send_preview_for_selection(
        supabase,
        msg,
        wa_client,
        user_id,
        conv_svc,
        conversation_id,
        str(state.pending_memo_id),
        selected_deal_id=artifacts.get("selected_deal_id"),
        is_new_deal=bool(artifacts.get("is_new_deal", False)),
        extraction_data=updated,
    )
    return True


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

    account = await resolve_whatsapp_account(supabase, msg.from_phone)
    if not account:
        logger.info(
            "⚠️ User not found by phone, sending UNKNOWN_USER_MSG",
            extra=log_domain(DOMAIN_WHATSAPP, "lookup_user", message_id=msg.message_id, from_phone=msg.from_phone),
        )
        await wa_client.send_text(msg.from_phone, UNKNOWN_USER_MSG, **_client_kwargs(msg))
        return
    if not account.is_ready:
        logger.info(
            "⚠️ WhatsApp account not ready",
            extra=log_domain(
                DOMAIN_WHATSAPP,
                "account_not_ready",
                message_id=msg.message_id,
                from_phone=msg.from_phone,
                user_id=account.user_id,
            ),
        )
        await wa_client.send_text(msg.from_phone, account.readiness_error, **_client_kwargs(msg))
        return

    user_id = account.user_id

    conv_svc = ConversationService(supabase)
    intent_svc = IntentService()
    conv = _get_or_create_session(conv_svc, msg, user_id)
    state = None
    if conv:
        inbound_text = msg.text or msg.button_title or msg.button_id or ""
        conv_svc.add_message(conv.id, "inbound", inbound_text, "text", _metadata_for_message(msg))
        state = conv_svc.get_state(conv.id)
        if state and conv_svc.is_state_expired(state):
            state = None

    if msg.type == "button":
        logger.info(
            "📱 Processing button reply",
            extra=log_domain(DOMAIN_WHATSAPP, "button_handled", message_id=msg.message_id, from_phone=msg.from_phone, button_id=msg.button_id),
        )
        if conv and state:
            text_from_button = msg.button_id or msg.button_title or ""
            msg = IncomingMessage(
                message_id=msg.message_id,
                from_phone=msg.from_phone,
                timestamp=msg.timestamp,
                type="text",
                provider=_message_provider(msg),
                text=text_from_button,
                chat_id=getattr(msg, "chat_id", None),
                account_id=getattr(msg, "account_id", None),
            )
        else:
            if (msg.button_id or "").startswith(("approve:", "add:")):
                await _handle_button_reply(supabase, msg, wa_client, user_id)
                return
            await wa_client.send_text(msg.from_phone, "No pending extraction. Send a voice memo to get started.", **_client_kwargs(msg))
            return

    if msg.type == "text" and conv and state:
        if state.state == "waiting_deal_choice":
            if await _handle_deal_choice(supabase, msg, wa_client, user_id, conv_svc, conv.id, state):
                return

        if state.state == "waiting_add_fields":
            if await _handle_waiting_add_fields(supabase, msg, wa_client, user_id, conv_svc, conv.id, state):
                return

        if state.state == "waiting_approval" and state.pending_memo_id:
            norm = _normalize(msg.text or "")
            artifacts = state.pending_artifact_ids or {}
            choice = _parse_deal_choice(msg.text or "")
            if choice == 1 or norm in APPROVE_PATTERNS:
                await _approve_pending_memo(
                    supabase, msg, wa_client, user_id, conv_svc, conv.id,
                    str(state.pending_memo_id), artifacts,
                )
                return
            if choice == 2 or norm in {"choose", "choose deal", "change deal", "another deal", "select deal"}:
                extraction_data, _ = await _load_memo_extraction(supabase, str(state.pending_memo_id), user_id)
                extraction = MemoExtraction(**extraction_data)
                matches, _connection_id, _provider_name = await _find_candidate_deals(supabase, user_id, extraction)
                if not matches:
                    await wa_client.send_text(msg.from_phone, "I did not find matching deals. Reply *1* to create a new deal, or *3* to edit fields.", **_client_kwargs(msg))
                    return
                text = _format_deal_choices(matches, extraction)
                conv_svc.set_state(
                    conv.id,
                    "waiting_deal_choice",
                    pending_memo_id=str(state.pending_memo_id),
                    pending_artifact_ids={
                        "deal_options": [m.model_dump() for m in matches],
                        "new_deal_index": len(matches) + 1,
                    },
                )
                conv_svc.add_message(conv.id, "outbound", text, "text", {"memo_id": str(state.pending_memo_id)})
                await wa_client.send_text(msg.from_phone, text, **_client_kwargs(msg))
                return
            if choice == 3 or norm in ADD_PATTERNS:
                conv_svc.set_state(conv.id, "waiting_add_fields", pending_memo_id=str(state.pending_memo_id))
                text = "Send the corrections as field/value lines:\namount: 50000\nclose date: 2026-06-15\nnext step: send proposal Friday"
                conv_svc.add_message(conv.id, "outbound", text, "text")
                await wa_client.send_text(msg.from_phone, text, **_client_kwargs(msg))
                return
            if norm in REJECT_PATTERNS:
                supabase.table("memos").update({"status": "rejected"}).eq("id", str(state.pending_memo_id)).eq("user_id", user_id).execute()
                conv_svc.set_state(conv.id, "idle")
                await wa_client.send_text(msg.from_phone, "Rejected. Send a new voice note when ready.", **_client_kwargs(msg))
                return

            edits = _parse_field_edits(msg.text or "")
            if edits:
                if await _handle_waiting_add_fields(supabase, msg, wa_client, user_id, conv_svc, conv.id, state):
                    return

            resolved = await intent_svc.resolve(
                text=(msg.text or "").strip(),
                state=state.state,
                pending_memo_id=str(state.pending_memo_id),
                messages=conv_svc.get_last_messages(conv.id, 10),
            )
            if resolved.intent in ("approve", "add_fields", "reject") and resolved.memo_id:
                if resolved.intent == "approve":
                    await _approve_pending_memo(
                        supabase, msg, wa_client, user_id, conv_svc, conv.id,
                        str(state.pending_memo_id), artifacts,
                    )
                else:
                    await _handle_intent_reply(supabase, msg, wa_client, user_id, conv_svc, conv.id, resolved)
                return
            if resolved.intent == "crm_update":
                param_edits = _field_edits_from_params(resolved.params)
                if param_edits:
                    extraction_data, _transcript = await _load_memo_extraction(supabase, str(state.pending_memo_id), user_id)
                    field_specs = await get_field_specs(supabase, user_id)
                    updated = _apply_field_edits(extraction_data, param_edits, field_specs)
                    supabase.table("memos").update({"extraction": updated}).eq("id", str(state.pending_memo_id)).eq("user_id", user_id).execute()
                    await _send_preview_for_selection(
                        supabase,
                        msg,
                        wa_client,
                        user_id,
                        conv_svc,
                        conv.id,
                        str(state.pending_memo_id),
                        selected_deal_id=artifacts.get("selected_deal_id"),
                        is_new_deal=bool(artifacts.get("is_new_deal", False)),
                        extraction_data=updated,
                    )
                    return
            await wa_client.send_text(
                msg.from_phone,
                "I did not understand that. Reply *1* to update CRM, *2* to choose another deal, or *3* to edit fields.",
                **_client_kwargs(msg),
            )
            return

        norm = _normalize(msg.text or "")
        if norm in APPROVE_PATTERNS or norm in ADD_PATTERNS or norm in REJECT_PATTERNS:
            await wa_client.send_text(
                msg.from_phone,
                "No pending extraction. Send a voice memo or sales update to get started.",
                **_client_kwargs(msg),
            )
            return

    from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run

    audio_url: Optional[str] = None
    memo_id = None
    extraction = None
    with pipeline_run() as stages:
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

        conversation_id: Optional[str] = str(conv.id) if conv else None

        memo_id, extraction = await _extract_and_create_memo(
            supabase, user_id, transcript, msg.message_id, audio_url, conversation_id
        )
    if memo_id:
        persist_pipeline_meta(supabase, str(memo_id), stages)

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

    try:
        matches, _connection_id, _provider_name = await _find_candidate_deals(supabase, user_id, extraction)
    except ValueError as e:
        await wa_client.send_text(msg.from_phone, str(e), **_client_kwargs(msg))
        return

    if not conv:
        # Session tables may be missing in an older deployment. Still send a useful
        # preview instead of failing silently, but replies will require dashboard fallback.
        field_specs = await get_field_specs(supabase, user_id)
        fallback = _format_extraction_summary(extraction, None, field_specs)
        await wa_client.send_text(msg.from_phone, fallback, **_client_kwargs(msg))
        return

    top_match = _high_confidence_match(matches)
    if top_match:
        await _send_preview_for_selection(
            supabase,
            msg,
            wa_client,
            user_id,
            conv_svc,
            conv.id,
            memo_id,
            selected_deal_id=top_match.deal_id,
            matched_deals=matches,
            selected_by_ai=True,
        )
        return

    if matches:
        choice_msg = _format_deal_choices(matches, extraction)
        conv_svc.set_state(
            conv.id,
            "waiting_deal_choice",
            pending_memo_id=memo_id,
            pending_artifact_ids={
                "deal_options": [m.model_dump() for m in matches],
                "new_deal_index": len(matches) + 1,
            },
        )
        conv_svc.add_message(conv.id, "outbound", choice_msg, "extraction_summary", {"memo_id": memo_id})
        await wa_client.send_text(msg.from_phone, choice_msg, **_client_kwargs(msg))
        return

    await _send_preview_for_selection(
        supabase,
        msg,
        wa_client,
        user_id,
        conv_svc,
        conv.id,
        memo_id,
        is_new_deal=True,
    )


async def _transcribe_audio(
    supabase: Client,
    wa_client: MessagingClient,
    msg: IncomingMessage,
    user_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Download audio, transcribe via batch STT (bytes), upload to storage for memo. Return (transcript, audio_url)."""
    try:
        audio_bytes, content_type = await wa_client.download_media(msg)
        transcript = await transcribe_bytes(
            audio_bytes,
            content_type=content_type or "audio/ogg",
            user_id=user_id,
            diarization=True,
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
            "❌ Batch transcription failed: %s",
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

        from app.services.extraction_context import load_product_context
        from app.services.session_entities import load_stt_profile
        from app.services.transcript_sanitize import (
            prepare_transcript_for_extraction,
            schedule_transcript_polish,
        )

        product_context = load_product_context(supabase, user_id)
        profile = load_stt_profile(supabase, user_id)
        transcript_raw = transcript
        transcript, glossary_text = prepare_transcript_for_extraction(
            transcript_raw,
            glossary,
            extra_names=[profile.get("full_name"), profile.get("company_name")],
        )

        extraction_svc = ExtractionService()
        extraction = await extraction_svc.extract(
            transcript, field_specs,
            glossary_text=glossary_text,
            product_context=product_context,
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
        try:
            r = supabase.table("memos").insert(insert).execute()
        except Exception as insert_exc:
            # Lost a race against a redelivered webhook for the same message_id
            # (see migrations/016_whatsapp_message_id_unique.sql) - the other
            # request already created the memo, fetch and return it instead of
            # failing (and instead of silently dropping the message).
            if "duplicate key" in str(insert_exc).lower() or "23505" in str(insert_exc):
                logger.info(
                    "📋 Memo idempotent hit (race on insert)",
                    extra=log_domain(DOMAIN_WHATSAPP, "memo_idempotent_race", whatsapp_message_id=whatsapp_message_id),
                )
                retry = (
                    supabase.table("memos")
                    .select("id", "extraction")
                    .eq("whatsapp_message_id", whatsapp_message_id)
                    .limit(1)
                    .execute()
                )
                if retry.data:
                    return retry.data[0]["id"], MemoExtraction(**retry.data[0]["extraction"])
            raise
        if not r.data:
            return None, None
        memo_id = r.data[0]["id"]
        from app.services.pipeline_lease import update_memo_row

        update_memo_row(supabase, str(memo_id), {"transcript_raw": transcript_raw})
        schedule_transcript_polish(str(memo_id), user_id, transcript, supabase)
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
