"""What earlier calls with this contact left behind, for live objection coaching.

Built only from stored memo extractions (summary + C04 intelligence) of
customer conversations; internal memos are left out, as in Ask. Nothing is
inferred: no memos, no block.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from supabase import Client

from app.services.playbooks.catalog import INTERNAL_KEY
from app.services.request_coalesce import CoalesceCache

logger = logging.getLogger(__name__)

MAX_MEMOS = 5
MAX_OBJECTIONS = 4
MAX_COMMITMENTS = 3
_CACHE = CoalesceCache(ttl_seconds=120)


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _intelligence(memo: dict) -> dict:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    intel = extraction.get("intelligence")
    return intel if isinstance(intel, dict) else {}


def format_contact_history(memos: list[dict]) -> str:
    """Newest memo first. Returns "" when nothing useful is stored."""
    ordered = sorted(memos, key=lambda m: str(m.get("created_at") or ""), reverse=True)[:MAX_MEMOS]
    if not ordered:
        return ""
    lines: list[str] = []

    latest = ordered[0]
    day = str(latest.get("created_at") or "")[:10]
    extraction = latest.get("extraction") if isinstance(latest.get("extraction"), dict) else {}
    summary = _clip(extraction.get("summary"), 280)
    interest = _intelligence(latest).get("interest")
    head = f"Last conversation ({day})" if day else "Last conversation"
    if summary:
        lines.append(f"{head}: {summary}")
    if isinstance(interest, str) and interest:
        lines.append(f"Interest at the end of it: {interest}")

    objections: list[str] = []
    seen_quotes: set[str] = set()
    for memo in ordered:
        for item in _intelligence(memo).get("objections") or []:
            if not isinstance(item, dict) or len(objections) >= MAX_OBJECTIONS:
                continue
            quote = _clip(item.get("quote"), 160)
            if not quote or quote.lower() in seen_quotes:
                continue
            seen_quotes.add(quote.lower())
            tags = ", ".join(str(t) for t in (item.get("category"), item.get("resolution")) if t)
            line = f'- "{quote}"' + (f" ({tags})" if tags else "")
            reply = _clip((item.get("response") or {}).get("text") if isinstance(item.get("response"), dict) else None, 160)
            if reply:
                line += f' — rep answered: "{reply}"'
            objections.append(line)
    if objections:
        lines.append("Objections they raised before:")
        lines.extend(objections)

    commitments: list[str] = []
    for item in _intelligence(latest).get("commitments") or []:
        if not isinstance(item, dict) or len(commitments) >= MAX_COMMITMENTS:
            continue
        text = _clip(item.get("text"), 160)
        if not text:
            continue
        due = str(item.get("due_at") or "")[:10]
        commitments.append(f"- {text}" + (f" (due {due})" if due else ""))
    if commitments:
        lines.append("Open commitments from the last conversation:")
        lines.extend(commitments)

    competitors: list[str] = []
    for memo in ordered:
        for item in _intelligence(memo).get("competitor_mentions") or []:
            name = _clip(item.get("name") if isinstance(item, dict) else None, 60)
            if name and name not in competitors:
                competitors.append(name)
    if competitors:
        lines.append("Competitors they mentioned: " + ", ".join(competitors[:3]))

    return "\n".join(lines)


def _read_memos(
    supabase: Client,
    company_id: str,
    contact_id: str,
    allowed_user_ids: Optional[list[str]],
) -> list[dict]:
    query = (
        supabase.table("memos")
        .select("id,created_at,extraction,user_id,sales_motion_key")
        .eq("company_id", company_id)
        .eq("hubspot_contact_id", contact_id)
        .order("created_at", desc=True)
        .limit(MAX_MEMOS * 2)
    )
    if allowed_user_ids is not None:
        query = query.in_("user_id", allowed_user_ids)
    rows = [row for row in query.execute().data or [] if row.get("sales_motion_key") != INTERNAL_KEY]
    return rows[:MAX_MEMOS]


async def load_contact_history(
    supabase: Client,
    *,
    company_id: str,
    contact_id: str,
    allowed_user_ids: Optional[list[str]],
) -> str:
    """The history block for one contact, cached briefly. Never raises.

    `allowed_user_ids` follows the pre-call brief: None reads every company
    memo for the contact, a list restricts the authors, [] reads nothing.
    """
    if allowed_user_ids is not None and not allowed_user_ids:
        return ""
    scope = ",".join(sorted(allowed_user_ids)) if allowed_user_ids is not None else "*"

    async def _load() -> str:
        try:
            return format_contact_history(_read_memos(supabase, company_id, contact_id, allowed_user_ids))
        except Exception as e:
            logger.warning("Contact history unavailable for suggest: %s", e)
            return ""

    return await _CACHE.get_or_set(f"{company_id}:{contact_id}:{scope}", _load)
