"""One input for the whole company (playbooks v2): the call types a document can be split into,
and making sure a detected type exists before its draft is saved.

Pure helpers over the store's `motions()` / `details()`; no I/O of their own except through
the store passed in.
"""

from __future__ import annotations

from typing import Any

from app.services.playbooks.catalog import (
    CATALOG_KEYS,
    catalog_label,
    default_applies_to,
    effective_applies_to,
    is_catalog,
)

# Flag off: two buckets. Everything before a meeting is `discovery`, everything an AE runs is
# `closing` (the D5 role defaults), whatever the document calls it.
_FLAG_OFF_KEYS = ("discovery", "closing")

_HINTS_ROUTING_ON = {
    "discovery": "SDR cold call: the first outbound call to a prospect who does not know us "
    "(opening with permission, reason for calling, finding the pain, qualifying, booking a meeting)",
    "inbound": "SDR call to a lead who asked for information (a form, a demo request): referencing "
    "their request, what made them ask, qualifying, booking a meeting",
    "ae_discovery": "AE first meeting or discovery call with a qualified prospect: agenda, current "
    "situation, pain and impact, who decides and how, agreeing the next meeting",
    "closing": "AE demo and close: a focused demo, handling concerns, agreeing a next step with a "
    "date (proposal, trial or signature)",
    "negotiation": "AE proposal and negotiation: reviewing the proposal and its price, validating "
    "decision makers, price and terms objections, agreeing a signing date",
}
_HINTS_ROUTING_OFF = {
    "discovery": "Everything that happens before a sales meeting: SDR work, prospecting, cold calls, "
    "inbound leads, qualification, booking the meeting",
    "closing": "Everything an AE runs: discovery meeting, demo, proposal, negotiation and closing",
}


def _custom_hint(label: str, applies_to: dict) -> str:
    parts = []
    role = applies_to.get("role")
    if role and role != "any":
        parts.append(f"role {role.upper()}")
    channels = applies_to.get("channels") or []
    if channels:
        parts.append("channel " + "/".join(channels))
    contact = applies_to.get("contact")
    if contact and contact != "any":
        parts.append(f"contact {contact}")
    rule = "; ".join(parts) or "any call"
    return f"The company's own call type \"{label}\" ({rule})"


def _label(key: str, meta: dict, lang: str) -> str:
    return str(meta.get("label") or "").strip() or catalog_label(key, lang) or key


def candidate_types(routing: bool, motions: dict, details: dict, lang: str) -> list[dict]:
    """[{key, label, description}] the document can be split into, in catalog order.

    Routing on: the five catalog types plus the company's own types that have a rule.
    Routing off: only `discovery` and `closing`. `label` is the company's own name for the
    type when it set one, else the catalog name in `lang`; `description` is for the model."""
    lang = "en" if lang == "en" else "es"
    out: list[dict] = []
    if not routing:
        for key in _FLAG_OFF_KEYS:
            out.append({
                "key": key,
                "label": _label(key, details.get(key) or {}, lang),
                "description": _HINTS_ROUTING_OFF[key],
            })
        return out
    for key in CATALOG_KEYS:
        out.append({
            "key": key,
            "label": _label(key, details.get(key) or {}, lang),
            "description": _HINTS_ROUTING_ON[key],
        })
    for key in sorted((set(motions) | set(details)) - set(CATALOG_KEYS)):
        meta = details.get(key) or {}
        applies_to = effective_applies_to(key, meta.get("applies_to"))
        if applies_to is None:
            continue  # a type with no rule applies to no call: not something to route content to
        label = _label(key, meta, lang)
        out.append({"key": key, "label": label, "description": _custom_hint(label, applies_to)})
    return out


def public_candidates(candidates: list[dict]) -> list[dict]:
    return [{"key": c["key"], "label": c["label"]} for c in candidates]


def ensure_type(store: Any, company_id: str, key: str, role: str, *, routing: bool, lang: str) -> None:
    """The type exists for the company before its draft is saved. A catalog type that is not
    there yet is added the way POST /types adds it: the type, and (routing on) its catalog
    label and default rule. A type that already exists is left alone."""
    if key in store.motions(company_id) or key in store.details(company_id):
        return
    store.add_type(company_id, key, catalog_label(key, lang) or key, role)
    if routing and is_catalog(key):
        store.save_type_meta(
            company_id, key, label=catalog_label(key, lang) or None, applies_to=default_applies_to(key),
        )

