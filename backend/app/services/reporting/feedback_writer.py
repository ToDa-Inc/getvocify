"""The written feedback of a report (REPORT_FEEDBACK_ENABLED): one model call over the period's facts
(rep_digest), never over transcripts, so it can only say what the numbers and the coaching already
say. The answer is kept with a hash of its facts: the daily report is rebuilt every few minutes in
the evening, and the same facts never pay for a second call. Any failure means no feedback, never a
broken report."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path

from app.services.feature_flags import is_enabled

logger = logging.getLogger(__name__)

FLAG = "REPORT_FEEDBACK_ENABLED"
PROMPT_VERSION = "report_feedback_v1"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"
MAX_ITEMS = 3
MAX_ITEM_CHARS = 220
MAX_HEADLINE_CHARS = 160
TIMEOUT_S = 60.0


@lru_cache(maxsize=1)
def _prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def facts_hash(payload: dict) -> str:
    text = json.dumps({"v": PROMPT_VERSION, **payload}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clip(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _items(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_clip(raw, MAX_ITEM_CHARS) for raw in value) if item][:MAX_ITEMS]


def shape(raw, *, audience: str, names: list[str] | None = None) -> dict | None:
    """The model's answer, clipped; None when it has no headline. For the Head of Sales, only notes about
    reps that are in the facts are kept."""
    if not isinstance(raw, dict):
        return None
    headline = _clip(raw.get("headline"), MAX_HEADLINE_CHARS)
    if not headline:
        return None
    out = {
        "headline": headline,
        "went_well": _items(raw.get("went_well")),
        "to_improve": _items(raw.get("to_improve")),
        "focus": _clip(raw.get("focus"), MAX_ITEM_CHARS) or None,
    }
    if audience == "head_of_sales":
        allowed = {name.casefold() for name in names or []}
        out["people"] = [
            {"name": _clip(item.get("name"), 80), "note": _clip(item.get("note"), MAX_ITEM_CHARS)}
            for item in raw.get("people") or []
            if isinstance(item, dict) and str(item.get("name") or "").strip().casefold() in allowed and item.get("note")
        ]
    return out


async def _ask(payload: dict, llm=None) -> dict | None:
    from app.config import settings

    if llm is None:
        from app.services.llm import LLMClient

        llm = LLMClient()
    messages = [
        {"role": "system", "content": _prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    return await llm.chat_json(messages, model=settings.INTELLIGENCE_MODEL, temperature=0.2, timeout=TIMEOUT_S)


def write_feedback(
    supabase,
    *,
    company_id: str,
    payload: dict,
    previous: dict | None = None,
    llm=None,
) -> dict | None:
    """{headline, went_well, to_improve, focus, people?, input_hash, prompt_version} or None (flag off,
    nothing to say, or the model failed). `previous` is the feedback already stored for this report: the
    same facts reuse it. Blocking: the report tick runs in a worker thread."""
    if not is_enabled(supabase, company_id, FLAG):
        return None
    digest = payload.get("facts") or {}
    if payload.get("audience") == "rep" and not (digest.get("activity") or {}).get("calls") and not (
        digest.get("activity") or {}
    ).get("meetings_held"):
        return None
    key = facts_hash(payload)
    if isinstance(previous, dict) and previous.get("input_hash") == key:
        return previous
    names = [row.get("name") for row in digest.get("reps") or [] if row.get("name")]
    try:
        raw = asyncio.run(_ask(payload, llm))
    except Exception:
        logger.warning("report feedback failed", extra={"company_id": company_id}, exc_info=True)
        return None
    shaped = shape(raw, audience=str(payload.get("audience") or "rep"), names=names)
    if shaped is None:
        return None
    return {**shaped, "input_hash": key, "prompt_version": PROMPT_VERSION}
