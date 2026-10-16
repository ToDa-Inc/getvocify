"""One input for the whole company (playbooks v2): the call types a document can be split into,
and making sure a detected type exists before its draft is saved.

Pure helpers over the company's motions and details (see routing.motions_and_stored); no I/O.
"""

from __future__ import annotations

from app.services.playbooks.structured import MAX_CRITERIA, MAX_STEPS
from app.services.playbooks.catalog import (
    CATALOG_KEYS,
    INTERNAL_KEY,
    catalog_label,
    catalog_order,
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


def candidate_types(routing: bool, motions: dict, details: dict, lang: str, *, by_channel: bool = False) -> list[dict]:
    """[{key, label, description}] the document can be split into, in catalog order.

    Types by channel: exactly the company's own list, the types its Proceso de venta shows (not
    paused, never Interna). Routing on: the five catalog types plus the company's own types that
    have a rule. Routing off: only `discovery` and `closing`. `label` is the company's own name
    for the type when it set one, else the catalog name in `lang`; `description` is for the model
    (the type's own recognition sentence when it has one)."""
    lang = "en" if lang == "en" else "es"
    out: list[dict] = []
    if by_channel:
        for key in sorted(motions, key=catalog_order):
            if key == INTERNAL_KEY or motions[key] == "paused":
                continue
            meta = details.get(key) or {}
            label = _label(key, meta, lang)
            recognize = str(meta.get("recognize") or "").strip()
            hint = _HINTS_ROUTING_ON.get(key) or _custom_hint(label, effective_applies_to(key, meta.get("applies_to")) or {})
            out.append({"key": key, "label": label, "description": f"{recognize} ({hint})" if recognize else hint})
        if out:
            return out
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


def ensure_payload(key: str, *, routing: bool, lang: str) -> dict:
    """The `ensure` of one item of repository.save_intake: the type is created first when the company does not have
    it yet, the way POST /types creates it: the type, and (routing on, a catalog type) its catalog label and default
    rule. A type that already exists is left alone."""
    payload: dict = {"name": catalog_label(key, lang) or key}
    if routing and is_catalog(key):
        payload["label"] = catalog_label(key, lang) or None
        payload["applies_to"] = default_applies_to(key)
    return payload


def _name(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def merge_split_results(results: list[list[dict]]) -> dict[str, dict]:
    """What several documents found, put together per call type -> {key: {key, reason, steps, objections, qualification}}.

    One intake replaces a type's draft, so a second document must not wipe the first one's: steps are added in order
    without repeating a name (at most MAX_STEPS; more marks the type "grouped"), the first answer to a fixed objection
    stays and the company's own objections and the criteria are added by name (criteria up to MAX_CRITERIA). Pure."""
    merged: dict[str, dict] = {}
    for types in results:
        for item in types:
            into = merged.setdefault(
                item["key"], {"key": item["key"], "reason": None, "steps": [], "objections": [], "qualification": []},
            )
            if item.get("reason") == "grouped":
                into["reason"] = "grouped"
            names = {_name(step.get("label")) for step in into["steps"]}
            for step in item.get("steps") or []:
                name = _name(step.get("label"))
                if not name or name in names:
                    continue
                if len(into["steps"]) >= MAX_STEPS:
                    into["reason"] = "grouped"
                    continue
                names.add(name)
                into["steps"].append(dict(step))
            keys = {_objection_key(o) for o in into["objections"]}
            for objection in item.get("objections") or []:
                key = _objection_key(objection)
                if key in keys:
                    continue
                keys.add(key)
                into["objections"].append(dict(objection))
            labels = {_name(c.get("label")) for c in into["qualification"]}
            for criterion in item.get("qualification") or []:
                name = _name(criterion.get("label"))
                if not name or name in labels or len(into["qualification"]) >= MAX_CRITERIA:
                    continue
                labels.add(name)
                into["qualification"].append(dict(criterion))
    return merged


def _objection_key(objection: dict) -> str:
    category = str(objection.get("category") or "").lower()
    return f"custom:{_name(objection.get('label'))}" if category == "custom" else category
