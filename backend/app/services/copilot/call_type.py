"""The call type (which playbook) during a live call.

At the start Vocify guesses for free: the type of the last conversation with this contact, else
the routing rule's default. Once the conversation says enough, one model call proposes a type from
the company's published ones. The rep's own pick always wins, and live help is grounded in
whatever type the call has, so live help and the notes after the call use one playbook.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.services.copilot.grounding import SuggestGrounding
from app.services.playbooks.catalog import INTERNAL_KEY
from app.services.playbooks.live import live_snapshot, live_snapshots

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT_S = 20.0

_PROPOSAL_SYSTEM = """You tell a sales rep which kind of call they are in, so live help uses the right playbook.

Pick the ONE type below whose purpose and steps best match what this conversation is about.
Judge by the prospect's situation and where the relationship is (a first conversation, an evaluation,
a decision), not by objections (they come up in any call) or by what the rep pitches.
Use only the keys listed. Set "confident" to false when the conversation doesn't show it yet.

Return only JSON: {"type": "<key>", "confident": true|false}"""


def provisional_type(
    last: Optional[str], rule: Optional[str], published: set[str],
) -> tuple[Optional[str], Optional[str]]:
    """(type, why) to start the call with, at no model cost: the last conversation with this
    contact, else the routing rule. Only a published type; an internal one says nothing about a
    customer call."""
    if last and last != INTERNAL_KEY and last in published:
        return last, "history"
    if rule and rule in published:
        return rule, "rule"
    return None, None


def guess(supabase: Any, company_id: str, user_id: str, kind: str, contact_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(type, why) to start the call with, at no model cost. With types by channel: only a type of
    this channel (with or without a playbook), starting from the last conversation with the contact,
    else what the capture would start with (the channel's only type or a saved CRM condition)."""
    from app.services.playbooks import channel_types

    last = last_contact_type(supabase, company_id, contact_id)
    if channel_types.enabled(supabase, company_id):
        try:
            keys = set(channel_types.candidates(channel_types._types(company_id), kind))
        except Exception:
            logger.warning("call type: channel types lookup failed", exc_info=True)
            return None, None
        start, _ = channel_types.resolve_at_capture(supabase, company_id, kind=kind, contact_id=contact_id)
        return provisional_type(last, start, keys)
    return provisional_type(last, rule_type(supabase, company_id, user_id, kind, contact_id), published_keys(supabase, company_id))


def last_contact_type(supabase: Any, company_id: str, contact_id: Optional[str]) -> Optional[str]:
    """The type of the newest conversation the company had with this contact."""
    if not contact_id:
        return None
    try:
        rows = (
            supabase.table("memos")
            .select("sales_motion_key,created_at")
            .eq("company_id", company_id)
            .eq("hubspot_contact_id", contact_id)
            .neq("status", "failed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        ) or []
    except Exception:
        logger.warning("call type: last conversation lookup failed", exc_info=True)
        return None
    return (str(rows[0].get("sales_motion_key") or "").strip() or None) if rows else None


def rule_type(supabase: Any, company_id: str, user_id: str, kind: str, contact_id: Optional[str]) -> Optional[str]:
    """The type the routing rules would pin this rep's capture to (the same rules as after the call)."""
    from app.services.captures import playbook_fields_for_capture
    from app.services.company import sales_role_for_user

    try:
        fields = playbook_fields_for_capture(
            supabase,
            company_id,
            default_when_unspecified=True,
            sales_role=sales_role_for_user(supabase, user_id, company_id=company_id),
            interaction_kind=kind,
            hubspot_contact_id=contact_id,
        )
    except Exception:
        logger.warning("call type: routing failed", exc_info=True)
        return None
    return str(fields.get("sales_motion_key") or "").strip() or None


def published_keys(supabase: Any, company_id: str) -> set[str]:
    try:
        return {str(s["sales_motion_key"]) for s in live_snapshots(supabase, company_id)} - {INTERNAL_KEY}
    except Exception:
        logger.warning("call type: published playbooks lookup failed", exc_info=True)
        return set()


def published_types(supabase: Any, company_id: str, labels: dict[str, str]) -> list[dict]:
    """The types the rep can be offered ({key, label, steps}), by key: published, and named by
    the labels the rep sees."""
    snapshots = live_snapshots(supabase, company_id)
    types = [
        {
            "key": str(snapshot["sales_motion_key"]),
            "label": labels[str(snapshot["sales_motion_key"])],
            "steps": [str(step.get("label") or "") for step in snapshot.get("steps") or [] if step.get("label")],
        }
        for snapshot in snapshots
        if str(snapshot["sales_motion_key"]) in labels and snapshot["sales_motion_key"] != INTERNAL_KEY
    ]
    return sorted(types, key=lambda item: item["key"])


def channel_types_offered(supabase: Any, company_id: str, kind: str, labels: dict[str, str]) -> list[dict]:
    """Types by channel: the channel's types the rep can be offered ({key, label, about}), with or
    without a playbook, each described the way the call reading is told about it."""
    from app.services.playbooks import channel_types

    types = channel_types._types(company_id)
    keys = [key for key in channel_types.candidates(types, kind) if key in labels]
    about = channel_types.describe(supabase, company_id, types, keys)
    return [{"key": key, "label": labels[key], "about": about[key]} for key in keys]


def proposal_messages(transcript_window: str, types: list[dict]) -> list[dict]:
    listed = "\n".join(
        f'- key "{item["key"]}": {item["about"]}' if item.get("about")
        else f'- key "{item["key"]}": {item["label"]}. Steps: {", ".join(item["steps"]) or "none"}'
        for item in types
    )
    return [
        {"role": "system", "content": _PROPOSAL_SYSTEM},
        {"role": "user", "content": f"TYPES\n{listed}\n\nCONVERSATION SO FAR\n{transcript_window}"},
    ]


def parse_proposal(raw: Any, published: set[str]) -> Optional[tuple[str, bool]]:
    """(type, confident) when the model named a published type, else None: never a made-up type."""
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("type") or "").strip()
    if not key or key == INTERNAL_KEY or key not in published:
        return None
    return key, raw.get("confident") is True


async def ask_model(messages: list[dict]) -> Any:
    from app.services.copilot.suggest import _resolve_model
    from app.services.llm import LLMClient

    return await LLMClient().chat_json(
        messages,
        model=_resolve_model(),
        temperature=0.0,
        timeout=PROPOSAL_TIMEOUT_S,
        max_retries=1,
        reasoning_effort="minimal",
    )


async def propose(
    supabase: Any, company_id: str, transcript_window: str, labels: dict[str, str], kind: Optional[str] = None,
) -> Optional[tuple[str, bool]]:
    """One model call: the type the conversation so far points to. A published one; with types by
    channel, one of the call's channel."""
    from app.services.playbooks import channel_types

    try:
        if kind and channel_types.enabled(supabase, company_id):
            types = channel_types_offered(supabase, company_id, kind, labels)
        else:
            types = published_types(supabase, company_id, labels)
    except Exception:
        logger.warning("call type: published playbooks lookup failed", exc_info=True)
        return None
    if not types:
        return None
    try:
        raw = await ask_model(proposal_messages(transcript_window, types))
    except Exception:
        logger.warning("call type: proposal failed", exc_info=True)
        return None
    proposal = parse_proposal(raw, {item["key"] for item in types})
    logger.info("call type proposal company=%s types=%d result=%s", company_id, len(types), json.dumps(proposal))
    return proposal


def grounding_for_type(supabase: Any, company_id: str, key: str, kind: str) -> Optional[SuggestGrounding]:
    """Live help grounded in this type's published playbook; None when it has none."""
    if not key or key == INTERNAL_KEY:
        return None
    try:
        snapshot = live_snapshot(supabase, company_id, key)
    except Exception:
        logger.warning("call type: playbook lookup failed", exc_info=True)
        return None
    if snapshot is None:
        return None
    return SuggestGrounding(
        interaction_kind=kind,
        playbook_version_id=snapshot["version_id"],
        evidence_ids=frozenset(),
        playbook_snapshot=snapshot,
    )
