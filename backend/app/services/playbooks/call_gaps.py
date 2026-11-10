"""What customers said that the playbook has no answer for, from every call read after it ended as well as from live help,
grouped by meaning so «es caro», «se nos va de precio» and «no nos sale a cuenta» become one question for the Head of Sales.

Two sources, one list:
  calls      objections in calls read against every playbook answer (C04 v10/v11) that matched none (`objection_id` null);
  live help  live-help cards about an objection that had no approved answer (`is_objection`, no `source_id`).
One model call (Together) groups them and drops the ones an answer written since already covers. When it fails, phrases are
grouped by their first words, as before. A colleague's reply after which the call moved forward rides along as a draft: the
manager edits it, never takes it as approved.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.playbooks.gaps import EXAMPLE_CHARS, MIN_REAL_CHARS, Gap, _ANSWER_REQUEST, _clip, _fold, _lang, _real_gaps

logger = logging.getLogger(__name__)

# Tests set a fake here so nothing reaches a provider; None is the real client.
_llm: Any = None


def set_grouping_llm(llm: Any) -> None:
    global _llm
    _llm = llm

DAYS = 28
MAX_PHRASES = 120
TIMEOUT_S = 30.0
DRAFT_CHARS = 400


def from_calls(rows: list[dict]) -> list[dict]:
    """The objections with no answer in conversations read against every answer: what the customer said, the call type,
    and the rep's reply when the call moved forward after it."""
    out = []
    for row in rows:
        if not row.get("is_conversation", True) or not row.get("answers_read"):
            continue
        for item in row.get("objections") or []:
            quote = " ".join(str(item.get("quote") or "").split())
            if item.get("kind") != "objection" or item.get("objection_id") or len(quote) < MIN_REAL_CHARS:
                continue
            worked = item.get("after") == "advanced" and item.get("response")
            out.append({"text": quote, "motion": row.get("motion"), "draft": str(item["response"]) if worked else None,
                        "at": row.get("observed_at") or ""})
    return out


def from_live_help(events: list[dict]) -> list[dict]:
    out = []
    for event in events:
        turn = " ".join(str(event.get("latest_turn") or "").split())
        if event.get("is_objection") and not event.get("source_id") and len(turn) >= MIN_REAL_CHARS:
            out.append({"text": turn, "motion": event.get("sales_motion_key"), "draft": None, "at": event.get("created_at") or ""})
    return out


def _prompt(phrases: list[dict], entries: list[dict], lang: str) -> list[dict]:
    answers = "\n".join(
        f"- {e.get('label') or e.get('category')}: {e.get('trigger') or ''}".rstrip(": ")
        for e in entries if str(e.get("guidance") or "").strip()
    ) or "(none)"
    listed = "\n".join(f"{i}. {_clip(p['text'], EXAMPLE_CHARS)}" for i, p in enumerate(phrases))
    system = (
        "You group what sales prospects said into the objections behind it. Two phrases go together only when one prepared "
        "answer would serve both (\"es caro\" and \"se nos va de precio\" yes; \"es caro\" and \"ya tenemos proveedor\" no). "
        "Leave out a phrase that one of the company's existing answers already covers. Return JSON: "
        '{"groups": [{"items": [numbers], "example": number}]}, where example is the clearest phrase of the group. '
        "Every number at most once. Invent nothing."
    )
    user = f"Company answers:\n{answers}\n\nPhrases ({'English' if lang == 'en' else 'Spanish'}):\n{listed}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _shape(raw: Any, count: int) -> list[tuple[list[int], int]]:
    groups, used = [], set()
    for group in (raw.get("groups") or []) if isinstance(raw, dict) else []:
        if not isinstance(group, dict):
            continue
        items = [i for i in group.get("items") or [] if isinstance(i, int) and 0 <= i < count and i not in used]
        if not items:
            continue
        used.update(items)
        example = group.get("example")
        groups.append((items, example if example in items else items[0]))
    return groups


async def group_by_meaning(phrases: list[dict], entries: list[dict], lang: str, *, llm: Any = None) -> Optional[list[tuple[list[int], int]]]:
    """[(phrase indexes, example index)] or None when the model could not be read."""
    if not phrases:
        return []
    try:
        llm = llm if llm is not None else _llm
        if llm is None:
            from app.services.llm import LLMClient

            llm = LLMClient()
        from app.config import settings

        result = llm.chat_json(messages=_prompt(phrases, entries, lang), model=settings.INTELLIGENCE_MODEL, timeout=TIMEOUT_S,
                               max_retries=1, reasoning_effort="minimal", max_tokens=2000)
        if inspect.isawaitable(result):
            result = await result
    except Exception:
        logger.warning("playbook gaps: grouping by meaning failed", exc_info=True)
        return None
    return _shape(result, len(phrases))


def _gap(rows: list[dict], example: dict, lang: str) -> Gap:
    text = _clip(example["text"], EXAMPLE_CHARS)
    motion = Counter(r["motion"] for r in rows if r.get("motion")).most_common(1)
    drafts = sorted((r for r in rows if r.get("draft")), key=lambda r: r["at"], reverse=True)
    question = f"A customer said “{text}” What do you answer?" if lang == "en" else f"Un cliente dijo «{text}» ¿Qué respondéis?"
    digest = hashlib.sha1(_fold(text)[:80].encode("utf-8")).hexdigest()[:10]
    return Gap(f"real:{digest}", "real", question, _ANSWER_REQUEST.format(example=text), len(rows), text,
               motion[0][0] if motion else None, _clip(drafts[0]["draft"], DRAFT_CHARS) if drafts else None)


async def unanswered_gaps(
    *, call_rows: list[dict], events: list[dict], entries: list[dict], lang: str, llm: Any = None,
) -> list[Gap]:
    """One question per objection with no answer, most repeated first."""
    lang = _lang(lang)
    phrases = sorted(from_calls(call_rows) + from_live_help(events), key=lambda p: p["at"], reverse=True)[:MAX_PHRASES]
    groups = await group_by_meaning(phrases, entries, lang, llm=llm)
    if groups is None:
        # The model could not be read: live help's phrases grouped by their first words, as before.
        return _real_gaps(events, lang)
    gaps = [_gap([phrases[i] for i in items], phrases[example], lang) for items, example in groups]
    return sorted(gaps, key=lambda g: (-g.seen, g.example or ""))


def recent_call_rows(supabase: Any, company_id: str, *, days: int = DAYS) -> list[dict]:
    """The company's conversations of the last `days`, as Coaching reads them. [] when they cannot be read."""
    try:
        from app.services.coaching import rep_coaching as engine
        from app.services.coaching.rep_coaching_reads import load_memos, load_team_reps

        user_ids = [rep["userId"] for rep in load_team_reps(supabase, company_id)]
        start = datetime.now(timezone.utc) - timedelta(days=days)
        rows = [engine.interaction_row(memo) for memo in load_memos(supabase, company_id, user_ids, start=start)]
        return [row for row in rows if row]
    except Exception:
        logger.warning("playbook gaps: calls could not be read", exc_info=True)
        return []
