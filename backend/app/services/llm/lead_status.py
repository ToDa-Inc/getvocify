"""Call-outcome casuistry for contact lead status.

Lead status is not a fact the prospect states. It is what this call did to
the contact. Jev classifies it with these rules so "they could not talk"
stays attempted-to-contact and never becomes disqualified.
"""

from __future__ import annotations

import re
from typing import Any, Optional

LEAD_STATUS_PROPERTY = "hs_lead_status"
DISQUALIFIED_MIN_CONFIDENCE = 0.75
MIN_SIGNAL_CONFIDENCE = 0.50

_REACH = frozenset({"no_live_conversation", "live_conversation", "not_stated"})
_STANCE = frozenset({
    "unavailable",
    "rejected",
    "bad_timing",
    "next_step",
    "meeting_booked",
    "open",
    "not_stated",
})

_LEAD_STATUS_NAMES = frozenset({
    "hs_lead_status",
    "leadstatus",
    "lead_status",
})

LEAD_STATUS_RULES = (
    "Lead status is what this call did to the contact, not a label the speakers said. "
    "Not being available to talk is never disqualified. No answer, voicemail, busy, "
    "gatekeeper, in a meeting, driving, or 'call me later' / 'llámame luego' with no "
    "rejection is attempted to contact. "
    "Disqualified / unqualified only after a real conversation and an explicit "
    "rejection or a confirmed dead end: not interested, do not call again, wrong "
    "company with nobody to introduce, locked with a competitor and will not switch. "
    "A short call, a hang-up, or a reschedule is not this. "
    "Bad timing is not a no and not a failed dial: next quarter, next year, no budget "
    "this period. "
    "A referral or any concrete next step without a meeting on the calendar is in "
    "progress. A real conversation without that is connected. "
    "A meeting or demo actually booked is open deal. Do not pick New. "
    "Use null when no option is justified."
)

REACH_INSTRUCTIONS = (
    "Did this call reach a real two-way conversation about the offer? "
    "A few polite words do not count. Someone who could not talk — busy, in a "
    "meeting, driving, voicemail, no answer, gatekeeper, 'call me later' — is "
    "no_live_conversation."
)

REACH_CRITERIA = {
    "no_live_conversation": (
        "No commercial conversation. No answer, voicemail, busy, gatekeeper, they "
        "are in a meeting, driving, or asked for a callback without discussing the "
        "offer. Not being available to talk is this."
    ),
    "live_conversation": (
        "Both sides discussed the offer, the problem, or a next step. A later "
        "callback after that discussion is still a live conversation."
    ),
    "not_stated": "Cannot tell whether a real conversation happened.",
}

STANCE_INSTRUCTIONS = (
    "What did the prospect decide? Use the first matching criterion. "
    "Not being available to talk is never disqualified and never a rejection."
)

STANCE_CRITERIA = {
    "meeting_booked": (
        "They booked a meeting, demo, or a specific calendar slot. "
        "'Let's talk sometime' without a booking is not this."
    ),
    "bad_timing": (
        "They are not saying no. The moment is wrong: next quarter, next year, "
        "no budget this period, after a project or vacation. Not a failed dial "
        "and not a disqualification."
    ),
    "unavailable": (
        "They could not talk and did not reject the offer: busy, in a meeting, "
        "driving, voicemail, no answer, 'llámame luego' / call me later. "
        "This is never disqualified."
    ),
    "rejected": (
        "Explicit rejection or a confirmed dead end, and only after they actually "
        "engaged: not interested, no me interesa, do not call again, wrong company "
        "with no one to introduce, already bought and will not switch. "
        "'I can't talk', a short call, or a reschedule is not this."
    ),
    "next_step": (
        "A concrete next action that is not a booked meeting: send material, "
        "introduce the buyer, call on a named day, they will review internally. "
        "A referral to the right person is this, not a rejection."
    ),
    "open": (
        "A real conversation happened, with no hard no, no booked meeting, and "
        "no concrete next step."
    ),
    "not_stated": "No decision is available. Unclear audio and internal chatter stay here.",
}

_BUCKET_FALLBACKS = {
    "open_deal": ("open_deal", "in_progress"),
    "disqualified": ("disqualified",),
    "bad_timing": ("bad_timing", "in_progress", "connected"),
    "attempted": ("attempted",),
    "in_progress": ("in_progress", "connected"),
    "connected": ("connected", "in_progress"),
    "open": ("open",),
    "new": (),
}

_PREFERRED_VALUES = {
    "attempted": ("ATTEMPTED_TO_CONTACT",),
    "disqualified": ("UNQUALIFIED", "DISQUALIFIED"),
    "bad_timing": ("BAD_TIMING",),
    "in_progress": ("IN_PROGRESS",),
    "connected": ("CONNECTED",),
    "open_deal": ("OPEN_DEAL",),
    "open": ("OPEN",),
    "new": ("NEW",),
}

def is_lead_status_field(spec: dict) -> bool:
    name = str(spec.get("name") or "").strip().lower()
    if name in _LEAD_STATUS_NAMES:
        return True
    label = re.sub(r"[\s_-]+", " ", str(spec.get("label") or "").strip().lower())
    return label in {"lead status", "estado del lead"}


def lead_status_bucket(value: str, label: str = "") -> str:
    """Map one portal option onto a call-outcome bucket. First match wins."""
    raw_value = str(value or "").strip()
    raw_label = str(label or "").strip()
    blob = re.sub(r"[_-]+", " ", f"{raw_value} {raw_label}").lower()
    upper = raw_value.upper()

    if "open deal" in blob or upper == "OPEN_DEAL":
        return "open_deal"
    if any(k in blob for k in (
        "attempt", "intent", "no answer", "voicemail", "no contesta", "buzon", "buzón",
    )):
        return "attempted"
    if "timing" in blob or "nurtur" in blob:
        return "bad_timing"
    if any(k in blob for k in (
        "unqualif", "disqualif", "descalif", "no cualif", "bad fit", "not a fit",
        "not interested", "no interesado", "do not contact",
    )):
        return "disqualified"
    if re.search(r"\b(lost|perdido|perdida)\b", blob) and "reason" not in blob and "motivo" not in blob:
        return "disqualified"
    if "in progress" in blob or "en curso" in blob or upper == "IN_PROGRESS":
        return "in_progress"
    if "qualif" in blob:
        return "in_progress"
    if any(k in blob for k in ("connected", "contacted", "contactado")) or upper == "CONNECTED":
        return "connected"
    if upper == "NEW" or raw_label.lower() in {"new", "nuevo"}:
        return "new"
    if upper == "OPEN" or raw_label.lower() in {"open", "abierto"}:
        return "open"
    return "other"


def _option_value_label(option: Any) -> tuple[str, str]:
    if isinstance(option, dict):
        value = str(option.get("value", "") or "")
        label = str(option.get("label") or value)
    else:
        value = str(option or "")
        label = value
    return value, label


def lead_reach_question() -> tuple[str, dict[str, str]]:
    return REACH_INSTRUCTIONS, dict(REACH_CRITERIA)


def lead_stance_question() -> tuple[str, dict[str, str]]:
    return STANCE_INSTRUCTIONS, dict(STANCE_CRITERIA)


def decide_lead_bucket(
    *,
    reach: str,
    reach_confidence: float,
    stance: str,
    stance_confidence: float,
) -> Optional[str]:
    """Map Jev's two signals onto one outcome. Unavailable is never a rejection."""
    reach_choice = str(reach or "").strip()
    stance_choice = str(stance or "").strip()
    if reach_choice not in _REACH:
        reach_choice = "not_stated"
    if stance_choice not in _STANCE:
        stance_choice = "not_stated"
    reach_conf = float(reach_confidence or 0)
    stance_conf = float(stance_confidence or 0)

    if stance_choice == "meeting_booked" and stance_conf >= MIN_SIGNAL_CONFIDENCE:
        return "open_deal"
    if stance_choice == "bad_timing" and stance_conf >= MIN_SIGNAL_CONFIDENCE:
        return "bad_timing"
    if stance_choice == "unavailable" and stance_conf >= MIN_SIGNAL_CONFIDENCE:
        return "attempted"
    if (
        reach_choice == "no_live_conversation"
        and reach_conf >= MIN_SIGNAL_CONFIDENCE
        and stance_choice not in {"bad_timing", "next_step", "meeting_booked"}
    ):
        return "attempted"
    if stance_choice == "rejected":
        if stance_conf < DISQUALIFIED_MIN_CONFIDENCE:
            return None
        if reach_choice == "live_conversation" and reach_conf >= MIN_SIGNAL_CONFIDENCE:
            return "disqualified"
        if reach_choice == "no_live_conversation":
            return "attempted"
        return None
    if stance_choice == "next_step" and stance_conf >= MIN_SIGNAL_CONFIDENCE:
        return "in_progress"
    if reach_choice == "live_conversation" and reach_conf >= MIN_SIGNAL_CONFIDENCE:
        return "connected"
    if reach_choice == "no_live_conversation" and reach_conf >= MIN_SIGNAL_CONFIDENCE:
        return "attempted"
    return None


def option_for_bucket(spec: dict, bucket: str) -> Optional[str]:
    """Portal option for an outcome. Never borrows Unqualified for a missed call."""
    chain = _BUCKET_FALLBACKS.get(bucket)
    if not chain:
        return None
    grouped: dict[str, list[str]] = {}
    for option in spec.get("options") or []:
        value, label = _option_value_label(option)
        if not value:
            continue
        grouped.setdefault(lead_status_bucket(value, label), []).append(value)
    for name in chain:
        choices = grouped.get(name) or []
        if not choices:
            continue
        for preferred in _PREFERRED_VALUES.get(name) or ():
            if preferred in choices:
                return preferred
        return choices[0]
    return None


def resolve_lead_status(
    spec: dict,
    *,
    reach: str,
    reach_confidence: float,
    stance: str,
    stance_confidence: float,
) -> Optional[str]:
    bucket = decide_lead_bucket(
        reach=reach,
        reach_confidence=reach_confidence,
        stance=stance,
        stance_confidence=stance_confidence,
    )
    if not bucket:
        return None
    return option_for_bucket(spec, bucket)


def lead_status_value_in_patch(spec: dict, patch: Optional[dict]) -> bool:
    if not isinstance(patch, dict):
        return False
    name = spec.get("name")
    if not name:
        return False
    obj = spec.get("object_type") or "deals"
    if obj == "contacts":
        bag = patch.get("contact_properties")
    elif obj == "companies":
        bag = patch.get("company_properties")
    else:
        deals = patch.get("deals")
        if isinstance(deals, dict) and _present(deals.get(name)):
            return True
        return _present(patch.get(name)) and name not in {
            "contact_properties",
            "company_properties",
            "deals",
            "_abstained",
        }
    return isinstance(bag, dict) and _present(bag.get(name))


def generative_lead_status_to_drop(specs: Optional[list], patch: Optional[dict]) -> list[str]:
    """Fields Jev did not set. The generative guess must not survive."""
    dropped: list[str] = []
    for spec in specs or []:
        if not isinstance(spec, dict) or not is_lead_status_field(spec):
            continue
        name = spec.get("name")
        if name and not lead_status_value_in_patch(spec, patch):
            dropped.append(str(name))
    return dropped


def lead_status_field_instruction(spec: dict) -> str:
    if not is_lead_status_field(spec):
        return ""
    return f"Lead status rules: {LEAD_STATUS_RULES}"


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def extraction_has_lead_status(extraction: Any) -> bool:
    raw = getattr(extraction, "raw_extraction", None)
    if raw is None and isinstance(extraction, dict):
        raw = extraction.get("raw_extraction")
    if not isinstance(raw, dict):
        return False
    contact = raw.get("contact_properties")
    if isinstance(contact, dict) and _present(contact.get(LEAD_STATUS_PROPERTY)):
        return True
    return _present(raw.get(LEAD_STATUS_PROPERTY))


def strip_lead_status_for_unattended_sync(data: Optional[dict]) -> dict:
    """Copy used by auto-approve. The saved memo keeps the suggestion."""
    out = dict(data or {})
    raw = out.get("raw_extraction")
    if isinstance(raw, dict):
        raw = dict(raw)
        contact = raw.get("contact_properties")
        if isinstance(contact, dict):
            contact = dict(contact)
            contact.pop(LEAD_STATUS_PROPERTY, None)
            raw["contact_properties"] = contact
        raw.pop(LEAD_STATUS_PROPERTY, None)
        out["raw_extraction"] = raw
    return out
