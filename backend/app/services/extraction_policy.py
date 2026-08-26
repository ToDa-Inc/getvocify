"""
Generic CRM fill policies for call extraction.

Field names differ per customer (Vocify has fit/angle/motion; others will not).
Classify from HubSpot/Salesforce name, label, and description — never a vendor-specific allowlist.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# HubSpot + Salesforce identity keys (names only; email is identity too).
_IDENTITY_NAMES = frozenset({
    "firstname",
    "lastname",
    "email",
    "first_name",
    "last_name",
    "firstname",
    "hs_email",
})
_IDENTITY_NAME_WRITE_KEYS = frozenset({
    "firstname",
    "lastname",
    "first_name",
    "last_name",
    "FirstName",
    "LastName",
})

_CALL_NOTE_NAMES = frozenset({"description", "summary"})

# Pre-call / outreach plan — never born from a live call.
_STRATEGY_RE = re.compile(
    r"\b("
    r"call angle|outreach angle|talk track|talktrack|talking point|"
    r"pre-?call|pre call|cadence|sequence message|outreach hook|"
    r"angulo|ángulo"
    r")\b",
    re.I,
)
_STRATEGY_NAME_RE = re.compile(r"(angle|talk_?track|pre_?call|cadence)\b", re.I)

# Account research / ICP — do not overwrite a value that enrichment already wrote.
_RESEARCH_RE = re.compile(
    r"\b("
    r"sales motion|icp|persona|enrichment|fit score|account fit|"
    r"encaje|icp fit|\bfit\b"
    r")\b",
    re.I,
)
_RESEARCH_NAME_RE = re.compile(
    r"(sales_?motion|\bfit\b|icp|persona|enrichment)",
    re.I,
)

FillPolicy = str  # identity | strategy | research | call_note | explicit


def _blob(spec: dict) -> str:
    parts = [
        str(spec.get("name") or ""),
        str(spec.get("label") or ""),
        str(spec.get("description") or ""),
    ]
    return " ".join(parts).replace("_", " ").replace("-", " ")


def classify_fill_policy(spec: dict) -> FillPolicy:
    """Return how a CRM field should be filled from a call transcript."""
    name = str(spec.get("name") or "").strip()
    name_l = name.lower()
    if name_l in _CALL_NOTE_NAMES:
        return "call_note"
    if name_l in _IDENTITY_NAMES or name in _IDENTITY_NAME_WRITE_KEYS:
        return "identity"
    if re.search(r"context_status|enriched_at", name_l):
        return "strategy"
    blob = _blob(spec)
    name_key = name.replace("-", "_")
    if _STRATEGY_RE.search(blob) or _STRATEGY_NAME_RE.search(name_key):
        return "strategy"
    if _RESEARCH_RE.search(blob) or _RESEARCH_NAME_RE.search(name_key):
        return "research"
    return "explicit"


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _object_bag(extracted: dict, object_type: str) -> dict:
    if object_type == "contacts":
        bag = extracted.get("contact_properties")
        if not isinstance(bag, dict):
            bag = {}
            extracted["contact_properties"] = bag
        return bag
    if object_type == "companies":
        bag = extracted.get("company_properties")
        if not isinstance(bag, dict):
            bag = {}
            extracted["company_properties"] = bag
        return bag
    return extracted


def _clear_field(extracted: dict, spec: dict) -> None:
    name = spec.get("name")
    if not name:
        return
    obj = spec.get("object_type") or "deals"
    bag = _object_bag(extracted, obj)
    if name in bag:
        bag[name] = None
    if obj != "deals" and name in extracted:
        extracted[name] = None


def apply_fill_policies(
    extracted: dict,
    field_specs: Optional[list[dict]] = None,
    existing_values: Optional[dict] = None,
) -> dict:
    """
    Defense-in-depth after the LLM returns JSON.

    - identity: do not change an existing name/email to a different spoken person
    - strategy: never write pre-call plan fields from a call
    - research: do not overwrite enrichment already on the record
    - call_note / explicit: leave LLM values (prompt already conservative)
    """
    if not extracted:
        return extracted
    out = dict(extracted)
    if isinstance(out.get("contact_properties"), dict):
        out["contact_properties"] = dict(out["contact_properties"])
    if isinstance(out.get("company_properties"), dict):
        out["company_properties"] = dict(out["company_properties"])

    existing_values = existing_values or {}
    for spec in field_specs or []:
        name = spec.get("name")
        if not name:
            continue
        obj = spec.get("object_type") or "deals"
        policy = classify_fill_policy(spec)
        existing_bag = existing_values.get(obj) or {}
        current = existing_bag.get(name) if isinstance(existing_bag, dict) else None

        bag = _object_bag(out, obj)
        proposed = bag.get(name)

        if isinstance(proposed, str) and proposed.strip().lower() == "unknown":
            _clear_field(out, spec)
            continue
        if policy == "strategy":
            _clear_field(out, spec)
            continue
        if policy == "research" and _has_value(current):
            _clear_field(out, spec)
            continue
        if policy == "identity" and _has_value(current):
            # Existing record already has this identity field — keep it as the default.
            _clear_field(out, spec)
            continue
        if _has_value(current) and _same_crm_value(proposed, current):
            _clear_field(out, spec)
            continue
    return out


def _same_crm_value(proposed: Any, current: Any) -> bool:
    if proposed is None or current is None:
        return False
    if isinstance(proposed, (int, float)) and isinstance(current, (int, float)):
        return float(proposed) == float(current)
    return str(proposed).strip() == str(current).strip()


def is_identity_name_field(name: str) -> bool:
    key = (name or "").strip()
    return key in _IDENTITY_NAME_WRITE_KEYS or key.lower() in {
        "firstname",
        "lastname",
        "first_name",
        "last_name",
    }


def drop_call_unsafe_props(
    props: dict[str, Any],
    *,
    existing_record: bool,
    current: Optional[dict] = None,
    object_type: str = "contacts",
) -> dict[str, Any]:
    """
    Last-gate filter for an existing CRM record.

    On update, keep the record's first/last name as-is (never propose or write a
    spoken name). Drop pre-call strategy fields. Drop research/ICP fields unless
    they are empty on the record.
    """
    if not existing_record or not props:
        return dict(props or {})
    current = current or {}
    out: dict[str, Any] = {}
    for key, value in props.items():
        spec = {"name": key, "object_type": object_type}
        policy = classify_fill_policy(spec)
        if is_identity_name_field(key):
            continue
        if policy == "strategy":
            continue
        if policy == "research":
            if not current or _has_value(current.get(key)):
                continue
        if policy == "identity" and key.lower() in {"email", "hs_email"}:
            if not current or _has_value(current.get(key)):
                continue
        out[key] = value
    return out


def strip_identity_name_props(props: dict[str, Any]) -> dict[str, Any]:
    """Drop first/last name keys so a spoken name cannot rename an existing contact."""
    return {k: v for k, v in (props or {}).items() if k not in _IDENTITY_NAME_WRITE_KEYS}


def format_existing_values_block(existing_values: Optional[dict]) -> str:
    """Human-readable current CRM snapshot for the extraction prompt."""
    if not existing_values:
        return ""
    lines: list[str] = []
    for obj in ("contacts", "companies", "deals"):
        bag = existing_values.get(obj) or {}
        if not isinstance(bag, dict):
            continue
        for key, val in bag.items():
            if not _has_value(val):
                continue
            display = val
            if isinstance(val, str) and len(val) > 280:
                display = val[:277] + "..."
            lines.append(f"- {obj}.{key} = {display}")
    if not lines:
        return ""
    return (
        "### CURRENT CRM VALUES (already on the record)\n"
        "These values are already stored. Prefer `null` (keep current) over a new inferred value.\n"
        "Never replace a person's name with a different speaker. Never replace pre-call / ICP fields "
        "from this conversation unless the prospect clearly corrected that same fact about themselves.\n"
        + "\n".join(lines)
    )


FILL_POLICY_LABELS: dict[FillPolicy, str] = {
    "identity": "Keep existing",
    "strategy": "Never from calls",
    "research": "Only if empty",
    "call_note": "Call note",
    "explicit": "From transcript",
}


def annotate_schema_fill_policies(schema: Any) -> Any:
    """Attach fill_policy to each CRM schema property using name/label/description."""
    props = list(getattr(schema, "properties", None) or [])
    object_type = getattr(schema, "object_type", None) or "deals"
    annotated = []
    for prop in props:
        if hasattr(prop, "model_copy"):
            policy = classify_fill_policy(
                {
                    "name": getattr(prop, "name", None),
                    "label": getattr(prop, "label", "") or "",
                    "description": getattr(prop, "description", "") or "",
                    "object_type": object_type,
                }
            )
            annotated.append(prop.model_copy(update={"fill_policy": policy}))
        elif isinstance(prop, dict):
            annotated.append({**prop, "fill_policy": classify_fill_policy({**prop, "object_type": object_type})})
        else:
            annotated.append(prop)
    if hasattr(schema, "model_copy"):
        return schema.model_copy(update={"properties": annotated})
    return schema


def fill_policy_instruction(policy: FillPolicy) -> str:
    return {
        "identity": (
            "Fill policy: identity — if CURRENT VALUE is set, return null and keep it. "
            "Do not propose firstname/lastname on an existing contact."
        ),
        "strategy": (
            "Fill policy: pre-call / outreach — return null. Do not fill talk tracks, call angles, "
            "or sequence copy from a live call."
        ),
        "research": (
            "Fill policy: account research — how the PROSPECT's company sells or whether they fit "
            "the ICP, not how we ran this call. Return null if CURRENT VALUE is set. If empty, fill "
            "from this call: map what they described to the closest allowed option (they will not "
            "say the option label). Numbers only when spoken for this metric. ICP cutoffs in the "
            "field description are scoring hints — still write the actual answer even if they miss the bar."
        ),
        "call_note": (
            "Fill policy: call note — write from this conversation (prospect-centric; no pitch recap)."
        ),
        "explicit": (
            "Fill policy: from this transcript — fill when the call answers the field. "
            "Enumerations: closest allowed option. Numbers/dates: only if stated. Otherwise null."
        ),
    }[policy]
