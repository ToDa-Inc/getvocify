"""Which type (playbook) a call was, from what was said.

Jev picks one of the company's published types, or `internal`, reading the conversation
with what is known around it: the channel, the app it happened in, whether the contact was
spoken to before, and the rep's sales role. A confident answer pins the memo and wins over
the routing rules (the content is the stronger signal); "unknown" or a low confidence
leaves the rule-based pin alone, and a type the rep or a manager set by hand never moves.

Runs alongside extraction, so it adds no wait to the post-call flow.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.playbooks.catalog import INTERNAL_KEY, catalog_types

logger = logging.getLogger(__name__)

# Jev's calibrated confidence needed to set the type over the rules.
CONFIDENT = 0.7
# Conversation sent to Jev: the opening says what the call is for, the end where it went.
HEAD_CHARS = 8000
TAIL_CHARS = 4000
# Only conversations with someone else are typed; a voice note is the rep talking alone.
TYPED_CHANNELS = ("call", "meeting")
UNKNOWN = "unknown"

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
    """What a type looks like, for Jev: its name, goal, usual setting and the steps of a good one."""
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


def type_criteria(published: list[dict]) -> dict[str, str]:
    """{key: description} for every published type, plus internal and unknown."""
    criteria = {option["key"]: describe_type(option["key"], option.get("label")) for option in published}
    criteria[INTERNAL_KEY] = "Internal: no customer or prospect takes part (team meeting, 1:1, coaching)."
    criteria[UNKNOWN] = "Not clear from the conversation which of these it is."
    return criteria


def conversation_excerpt(transcript: str) -> str:
    text = (transcript or "").strip()
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text
    return f"{text[:HEAD_CHARS]}\n[…]\n{text[-TAIL_CHARS:]}"


def published_types(company_id: str) -> list[dict]:
    """[{key, label}] of the company's live (published) types."""
    from app.services.playbooks.repository import get_playbook_repository
    from app.services.playbooks.routing import motions_and_stored

    motions, stored = motions_and_stored(get_playbook_repository().list_types(company_id, include_draft=False))
    return [
        {"key": key, "label": (stored.get(key) or {}).get("label") or None}
        for key, state in motions.items()
        if state == "published" and key != INTERNAL_KEY
    ]


async def classify_memo_type(supabase: Any, memo_id: str, transcript: str, jev: Any = None) -> Optional[tuple[str, float]]:
    """(type key, confidence) for a call or meeting, or None when it can't be asked. Never raises."""
    try:
        from app.services.captures import interaction_kind_of
        from app.services.company import sales_role_for_user
        from app.services.llm.jev import JevClient
        from app.services.playbooks.routing import contact_status

        jev = jev or JevClient()
        if not jev.is_available or not (transcript or "").strip():
            return None
        rows = (
            supabase.table("memos")
            .select("id,company_id,user_id,source,source_type,interaction_kind,hubspot_contact_id,hubspot_deal_id,pipeline_meta")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        ).data or []
        memo = rows[0] if rows else None
        if not memo or not memo.get("company_id"):
            return None
        channel = interaction_kind_of(memo)
        if channel not in TYPED_CHANNELS:
            return None
        company_id = str(memo["company_id"])
        published = published_types(company_id)
        if not published:
            return None
        meta = memo.get("pipeline_meta") if isinstance(memo.get("pipeline_meta"), dict) else {}
        state = {
            "conversation": conversation_excerpt(transcript),
            "channel": channel,
            "app": str(meta.get("call_source") or UNKNOWN),
            "contact_history": contact_status(
                supabase,
                company_id,
                contact_id=memo.get("hubspot_contact_id"),
                deal_id=memo.get("hubspot_deal_id"),
                exclude_memo_id=str(memo_id),
            )
            or UNKNOWN,
            "rep_role": sales_role_for_user(supabase, str(memo.get("user_id") or ""), company_id=company_id) or UNKNOWN,
        }
        answer = await jev.classify_choice(
            state,
            "call_type",
            "Which kind of sales conversation is `conversation`? Judge by what is said: who is "
            "speaking, why the call happens and what it is trying to achieve. `channel`, `app`, "
            "`contact_history` and `rep_role` are context. If it does not clearly fit one, choose unknown.",
            type_criteria(published),
        )
        if not answer:
            return None
        logger.info("Call type for memo %s: %s (%.2f)", memo_id, answer[0], answer[1])
        return answer
    except Exception:
        logger.warning("call type classification failed", exc_info=True)
        return None


def apply_memo_type(supabase: Any, memo_id: str, answer: Optional[tuple[str, float]]) -> None:
    """Pins a confident answer. A manual pin, "unknown", a low confidence or a type with no
    live version changes nothing. Never raises."""
    if not answer:
        return
    key, confidence = answer
    if key == UNKNOWN or confidence < CONFIDENT:
        return
    try:
        from app.services.playbooks.live import live_version_id
        from app.services.playbooks.routing import PIN_META_KEY, merge_pin_meta

        rows = (
            supabase.table("memos")
            .select("id,company_id,sales_motion_key,playbook_version_id,pipeline_meta")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        ).data or []
        memo = rows[0] if rows else None
        if not memo:
            return
        meta = memo.get("pipeline_meta") if isinstance(memo.get("pipeline_meta"), dict) else {}
        pin = meta.get(PIN_META_KEY) if isinstance(meta.get(PIN_META_KEY), dict) else {}
        if pin.get("source") == "manual":
            return
        current = memo.get("sales_motion_key")
        version: Optional[str] = None
        if key != INTERNAL_KEY:
            live = live_version_id(supabase, str(memo.get("company_id")), key)
            if not live:
                return
            version = str(live)
        extra: dict[str, Any] = {"confidence": round(confidence, 2)}
        if current and current != key:
            extra["changed_from"] = current
        # "jev" is not re-pinnable: the routing rules never move it afterwards.
        supabase.table("memos").update(
            {
                "sales_motion_key": key,
                "playbook_version_id": version,
                "pipeline_meta": merge_pin_meta(meta, "jev", **extra),
            }
        ).eq("id", str(memo_id)).execute()
    except Exception:
        logger.warning("call type pin failed", exc_info=True)
