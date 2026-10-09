"""Which type (playbook) a call was, as the call reading said.

The call reading (C04 v8, intelligence/call_reading.py) already reads every call once to say
who spoke and what kind of call it was; given the company's published types it also names the
playbook the call fits, in that same pass, so a call is never read twice. That answer pins the
memo over Vocify's own guesses (the role default, a catalog rule). Deliberate choices are never
moved: a type someone picked by hand, or a rule the company saved for that type. A call with no
real conversation keeps its pin, and "unknown" changes nothing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.playbooks.catalog import INTERNAL_KEY, catalog_types

logger = logging.getLogger(__name__)

# The pin source for a type the call reading chose. Not re-pinnable: rules never move it.
READING_SOURCE = "reading"

_GOALS = {
    "meeting_booked": "book a meeting",
    "demo_booked": "book a demo",
    "proposal_and_close": "present the product and move to close",
    "close_date": "agree terms and a close date",
}
_CONTACTS = {
    "new": "a first conversation with a new prospect",
    "contacted": "a prospect already spoken to",
    "inbound": "a lead who asked to be contacted",
}


def describe_type(key: str, label: Optional[str]) -> str:
    """What a type looks like: its name, goal, usual setting and the steps of a good one."""
    entry = next((t for t in catalog_types() if t["key"] == key), None)
    if not entry:
        return f"{label or key}: a call type defined by this company."
    name = label or f"{entry['label']['en']} ({entry['label']['es']})"
    parts = [name]
    if entry.get("goal") in _GOALS:
        parts.append(f"Goal: {_GOALS[entry['goal']]}.")
    applies = entry.get("applies_to") or {}
    setting = [", ".join(applies.get("channels") or [])] if applies.get("channels") else []
    if applies.get("contact") in _CONTACTS:
        setting.append(_CONTACTS[applies["contact"]])
    if setting:
        parts.append(f"Usually: {'; '.join(setting)}.")
    steps = [step["label"] for step in (entry.get("template") or {}).get("en", []) if step.get("label")]
    if steps:
        parts.append(f"A good one covers: {', '.join(steps)}.")
    return " ".join(parts)


def _company_types(company_id: str) -> tuple[dict, dict]:
    from app.services.playbooks.repository import get_playbook_repository
    from app.services.playbooks.routing import motions_and_stored

    return motions_and_stored(get_playbook_repository().list_types(company_id, include_draft=False))


_INTERNAL_DESCRIPTION = "Internal: no customer or prospect takes part (team meeting, 1:1, coaching)."


def reading_playbooks(
    company_id: Optional[str], *, kind: Optional[str] = None, supabase: Any = None,
) -> Optional[dict[str, str]]:
    """{key: what it is} for the call reading: the company's published types plus internal.
    None when the company has none published (then the reading names no playbook).

    With types by channel: the types of the recording's channel, with or without a playbook,
    described by name, recognition sentence and steps (channel_types.describe)."""
    if not company_id:
        return None
    if supabase is not None:
        from app.services.playbooks import channel_types

        if channel_types.enabled(supabase, str(company_id)):
            try:
                types = channel_types._types(str(company_id))
                keys = channel_types.candidates(types, kind)
                if not keys:
                    return None
                return {**channel_types.describe(supabase, str(company_id), types, keys), INTERNAL_KEY: _INTERNAL_DESCRIPTION}
            except Exception:
                logger.warning("could not load the channel's types for the call reading", exc_info=True)
                return None
    try:
        motions, stored = _company_types(str(company_id))
    except Exception:
        logger.warning("could not load playbook types for the call reading", exc_info=True)
        return None
    published = {
        key: describe_type(key, (stored.get(key) or {}).get("label") or None)
        for key, state in motions.items()
        if state == "published" and key != INTERNAL_KEY
    }
    if not published:
        return None
    published[INTERNAL_KEY] = _INTERNAL_DESCRIPTION
    return published


def apply_reading_type(supabase: Any, memo_id: str, reading: Optional[dict]) -> None:
    """Pins the playbook the call reading named. Nothing named, a manual pin, a rule the
    company saved, or a type with no live version changes nothing. Never raises."""
    key = (reading or {}).get("playbook")
    if not key:
        return
    try:
        from app.services.playbooks.live import live_version_id
        from app.services.playbooks.routing import PIN_META_KEY, merge_pin_meta

        rows = (
            supabase.table("memos")
            .select("id,company_id,sales_motion_key,playbook_version_id,pipeline_meta,interaction_kind,source,source_type")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        ).data or []
        memo = rows[0] if rows else None
        if not memo:
            return
        from app.services.playbooks import channel_types

        if channel_types.enabled(supabase, str(memo.get("company_id") or "")):
            _apply_by_channel(supabase, memo, key)
            return
        meta = memo.get("pipeline_meta") if isinstance(memo.get("pipeline_meta"), dict) else {}
        pin = meta.get(PIN_META_KEY) if isinstance(meta.get(PIN_META_KEY), dict) else {}
        if pin.get("source") == "manual":
            return
        current = memo.get("sales_motion_key")
        if pin.get("source") == "rule" and current:
            # A rule the company saved for this type is its own decision; a catalog default is ours.
            _, stored = _company_types(str(memo.get("company_id")))
            if (stored.get(current) or {}).get("applies_to"):
                return
        version: Optional[str] = None
        if key != INTERNAL_KEY:
            live = live_version_id(supabase, str(memo.get("company_id")), key)
            if not live:
                return
            version = str(live)
        extra: dict[str, Any] = {}
        if current and current != key:
            extra["changed_from"] = current
        supabase.table("memos").update(
            {
                "sales_motion_key": key,
                "playbook_version_id": version,
                "pipeline_meta": merge_pin_meta(meta, READING_SOURCE, **extra),
            }
        ).eq("id", str(memo_id)).execute()
    except Exception:
        logger.warning("call type pin failed", exc_info=True)


def _apply_by_channel(supabase: Any, memo: dict, key: str) -> None:
    """Types by channel: the reading's type is the memo's unless a person picked one or a CRM condition
    decided it (a `single` pin only becomes Interna). The write is conditional on the pin not having
    become final meanwhile, so a retag made while the call was being read always wins."""
    from app.services.captures import interaction_kind_of
    from app.services.playbooks import channel_types

    company_id = str(memo.get("company_id") or "")
    meta = memo.get("pipeline_meta") if isinstance(memo.get("pipeline_meta"), dict) else {}
    current = memo.get("sales_motion_key")
    if key == current or not channel_types.may_move(meta, key):
        return
    if key != INTERNAL_KEY and key not in channel_types.candidates(channel_types._types(company_id), interaction_kind_of(memo)):
        return
    extra = {"changed_from": current} if current else {}
    update = channel_types.pin_fields(supabase, company_id, key, READING_SOURCE, meta, **extra)
    channel_types.write_unless_final(supabase, str(memo["id"]), update, channel_types.pin_source(meta))
