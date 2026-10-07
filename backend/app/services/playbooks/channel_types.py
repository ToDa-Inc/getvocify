"""Types by channel (TYPE_BY_CHANNEL_ENABLED, spec 2026-10-07-interaction-types-by-channel-design).

A recording has a channel (call or meeting, from where it was captured) and a type (the company's
own list). A type belongs to the channels its rule names; the member's sales role plays no part,
and a type needs no playbook: without a published one it is a label, never scored.

The type is decided once, by the call reading after the call. Before that it is only a start:
the one type the channel has (`single`), a CRM condition the company saved (`crm_rule`), or
Vocify's live suggestion on the desktop (`live`). A person's pick (`manual`) and a CRM condition
are final; a `single` pin can only become Interna.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.playbooks.catalog import (
    INTERNAL_KEY,
    catalog_label,
    catalog_order,
    effective_applies_to,
    template_steps,
)
from app.services.playbooks.live import live_snapshots, live_version_id
from app.services.playbooks.motion import rule_matches, specificity
from app.services.playbooks.routing import PIN_META_KEY, build_context, merge_pin_meta

logger = logging.getLogger(__name__)

FLAG = "TYPE_BY_CHANNEL_ENABLED"
CALL_READING_FLAG = "INTELLIGENCE_CALL_READING_ENABLED"
CHANNELS = frozenset({"call", "meeting"})
# The statuses of a type that can be detected. "paused" is the type's own off switch in Settings.
_DETECTABLE = frozenset({"published", "draft", "missing"})
# Pins nothing after them may move: a person's pick and a CRM condition the company saved.
FINAL_SOURCES = frozenset({"manual", "crm_rule"})
SINGLE_SOURCE = "single"
CRM_SOURCE = "crm_rule"
LIVE_SOURCE = "live"


def enabled(supabase: Any, company_id: Optional[str]) -> bool:
    """On only together with the call reading: without it nothing after the call decides the type."""
    from app.services.feature_flags import is_enabled

    return bool(company_id) and is_enabled(supabase, company_id, FLAG) and is_enabled(supabase, company_id, CALL_READING_FLAG)


def type_channels(key: str, applies_to: Any) -> set[str]:
    """The channels a type belongs to: its rule's (the saved one, else the catalog's). No rule or
    no channel named = both. The role in the rule is ignored."""
    rule = effective_applies_to(key, applies_to)
    channels = set((rule or {}).get("channels") or [])
    return channels or set(CHANNELS)


def candidates(types: dict[str, dict], kind: Optional[str]) -> list[str]:
    """The keys a recording on this channel can be, in catalog order. Only call and meeting have
    types; a paused type, a deleted one (not listed) and Interna are never candidates."""
    if kind not in CHANNELS:
        return []
    keys = [
        key
        for key, row in types.items()
        if key != INTERNAL_KEY
        and row.get("status") in _DETECTABLE
        and kind in type_channels(key, row.get("applies_to"))
    ]
    return sorted(keys, key=catalog_order)


def _has_crm_condition(applies_to: dict) -> bool:
    return (applies_to.get("contact") or "any") != "any" or bool(applies_to.get("deal_stages"))


def crm_rules(types: dict[str, dict], keys: list[str]) -> list[dict]:
    """[{key, applies_to}] of the candidates whose SAVED rule has a CRM condition and no role. A rule
    written for a role (the old SDR/AE routing) or a catalog default only contributes its channels."""
    from app.services.playbooks.catalog import RuleError, validate_applies_to

    out: list[dict] = []
    for key in keys:
        stored = (types.get(key) or {}).get("applies_to")
        if not stored:
            continue
        try:
            rule = validate_applies_to(stored)
        except RuleError:
            continue
        if rule["role"] == "any" and _has_crm_condition(rule):
            out.append({"key": key, "applies_to": rule})
    return out


def crm_choice(rules: list[dict], kind: str, context: dict) -> Optional[str]:
    """The one type whose CRM condition matches what is known; the most specific wins, and two
    different types tied at the top decide nothing (the call reading does). Unknown never matches."""
    matches = [(specificity(rule["applies_to"]), rule["key"]) for rule in rules
               if rule_matches(rule["applies_to"], None, kind, context)]
    if not matches:
        return None
    best = max(score for score, _ in matches)
    keys = {key for score, key in matches if score == best}
    return keys.pop() if len(keys) == 1 else None


def _needs(rules: list[dict]) -> dict[str, bool]:
    need = {"contact": False, "inbound": False, "stage": False}
    for rule in rules:
        contact = rule["applies_to"].get("contact") or "any"
        need["contact"] |= contact in ("new", "contacted")
        need["inbound"] |= contact == "inbound"
        need["stage"] |= bool(rule["applies_to"].get("deal_stages"))
    return need


def _types(company_id: str) -> dict[str, dict]:
    from app.services.playbooks.repository import get_playbook_repository

    return get_playbook_repository().list_types(company_id, include_draft=False)


def resolve_at_capture(
    supabase: Any,
    company_id: str,
    *,
    kind: Optional[str],
    contact_id: Optional[str] = None,
    deal_id: Optional[str] = None,
    exclude_memo_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """(key, "single" | "crm_rule") to start a recording with, or (None, None) to leave it to the
    call reading. Never raises: a failed read is "nothing decided"."""
    try:
        types = _types(str(company_id))
        keys = candidates(types, kind)
        if not keys:
            return None, None
        if len(keys) == 1:
            return keys[0], SINGLE_SOURCE
        rules = crm_rules(types, keys)
        if not rules:
            return None, None
        context = build_context(
            supabase, str(company_id), _needs(rules),
            contact_id=contact_id, deal_id=deal_id, exclude_memo_id=exclude_memo_id,
        )
        key = crm_choice(rules, str(kind), context)
        return (key, CRM_SOURCE) if key else (None, None)
    except Exception:
        logger.warning("type by channel: capture resolve failed", exc_info=True)
        return None, None


def pin_source(pipeline_meta: Any) -> Optional[str]:
    pin = pipeline_meta.get(PIN_META_KEY) if isinstance(pipeline_meta, dict) else None
    return pin.get("source") if isinstance(pin, dict) else None


def may_move(pipeline_meta: Any, key: str) -> bool:
    """Whether a decider after the capture (the call reading, a CRM re-check) may pin `key` over
    what the memo has. A person's pick and a CRM condition are final; the channel's only type can
    still turn out to be an internal conversation."""
    source = pin_source(pipeline_meta)
    if source in FINAL_SOURCES:
        return False
    if source == SINGLE_SOURCE:
        return key == INTERNAL_KEY
    return True


def pin_fields(supabase: Any, company_id: str, key: str, source: str, existing_meta: Any = None, **extra: Any) -> dict:
    """The memo columns for pinning `key`: its live playbook version when it has one, else none
    (a label, never scored)."""
    version = None if key == INTERNAL_KEY else live_version_id(supabase, str(company_id), key)
    return {
        "sales_motion_key": key,
        "playbook_version_id": str(version) if version else None,
        "pipeline_meta": merge_pin_meta(existing_meta, source, **extra),
    }


def recheck_crm(supabase: Any, memo: dict) -> dict:
    """Right before C04: a CRM condition the company saved, matched with what is known by now (the
    contact or deal may only be known after the capture). It beats the call reading and a live
    suggestion; a person's pick or an earlier CRM decision stays. Returns the memo as it is now.
    Never raises."""
    try:
        from app.services.captures import interaction_kind_of

        company_id = str(memo.get("company_id") or "")
        meta = memo.get("pipeline_meta")
        if not company_id or not memo.get("id") or pin_source(meta) in FINAL_SOURCES:
            return memo
        kind = interaction_kind_of(memo)
        types = _types(company_id)
        rules = crm_rules(types, candidates(types, kind))
        if not rules:
            return memo
        context = build_context(
            supabase, company_id, _needs(rules),
            contact_id=memo.get("hubspot_contact_id"),
            deal_id=memo.get("hubspot_deal_id") or memo.get("matched_deal_id"),
            exclude_memo_id=str(memo["id"]),
        )
        key = crm_choice(rules, kind, context)
        current = memo.get("sales_motion_key")
        if not key or key == current:
            return memo
        update = pin_fields(supabase, company_id, key, CRM_SOURCE, meta, **({"repinned_from": current} if current else {}))
        from app.services.playbooks.type_classifier import NOT_MANUAL_FILTER

        supabase.table("memos").update(update).eq("id", str(memo["id"])).or_(NOT_MANUAL_FILTER).execute()
        return {**memo, **update}
    except Exception:
        logger.warning("type by channel: CRM re-check failed", exc_info=True)
        return memo


def type_name(key: str, row: Optional[dict], lang: str = "es") -> str:
    return (row or {}).get("label") or catalog_label(key, lang) or key


def describe(supabase: Any, company_id: str, types: dict[str, dict], keys: list[str]) -> dict[str, str]:
    """{key: what it is} for the AI, the same for the live suggestion and the call reading: its name,
    how to recognise it (the company's sentence), and the steps of its published playbook (else the
    catalog's starter steps). One read for every playbook."""
    try:
        steps_by_key = {
            str(snap["sales_motion_key"]): [str(step.get("label")) for step in snap.get("steps") or [] if step.get("label")]
            for snap in live_snapshots(supabase, str(company_id))
        }
    except Exception:
        logger.warning("type by channel: playbook steps unavailable", exc_info=True)
        steps_by_key = {}
    out: dict[str, str] = {}
    for key in keys:
        row = types.get(key) or {}
        parts = [f"{type_name(key, row)}."]
        recognize = " ".join(str(row.get("recognize") or "").split())
        if recognize:
            parts.append(recognize if recognize.endswith(".") else f"{recognize}.")
        steps = steps_by_key.get(key) or [step["label"] for step in template_steps(key, "en") if step.get("label")]
        if steps:
            parts.append(f"A good one covers: {', '.join(steps)}.")
        out[key] = " ".join(parts)
    return out
