"""The line a rep could have said at one moment of a call (Coaching → "Mejor").

What the playbook holds for a step or an objection is an instruction for the team ("distinguish what
'not now' means, don't assume"). A rep reading Coaching needs the sentence: this prospect's words, the
playbook's move, said out loud. It is written on demand for one occurrence, from what the playbook and
"Vuestra empresa" say and nothing else; when they give no base the answer is None, never an invented line.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Literal, Optional

from app.config import settings

logger = logging.getLogger(__name__)

SAY_MAX_CHARS = 320
CACHE_SECONDS = 24 * 3600.0
_MAX_CACHED = 2000
_cache: dict[str, tuple[float, tuple[Optional[str], bool]]] = {}

SYSTEM = """You write the one thing a sales rep could have said at a specific moment of a call, so they can say it next time.
You get what the team's playbook says for this moment, what was said in the call, and the company's own facts.

Rules:
- Spanish, tú form, spoken language, first person, as the rep would say it out loud. One or two sentences, 40 words at most.
- Use only what the playbook text and the company facts say. Never invent numbers, customers, features, prices, discounts or promises.
- For an objection: pick up the prospect's own words, then make the playbook's move. End with a question only when the playbook's answer does.
- For a step: say the step the way the playbook's example does, in this call's terms (this prospect, what they just said).
- Fit the line to the call excerpt: pick up what the prospect just said. You may reuse the playbook example's words, but never paste it whole when the excerpt makes it not fit.
- No coaching voice ("deberías", "intenta"), no filler ("entiendo perfectamente", "excelente pregunta"), no emojis, no quotation marks around the line.
- If the rep replied and their reply already makes the playbook's move, even in different words, order or style, the line is not needed:
  answer {"say": null, "fine": true}. Judge by purpose, not wording. A reply that dodges, only agrees, or skips the move is not fine.
- If the playbook text gives nothing to base a reply on for this moment, answer {"say": null, "fine": false}. Do not improvise.
Return only JSON: {"say": "<the line>" | null, "fine": true | false}"""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def build_messages(
    *,
    kind: Literal["step", "objection"],
    playbook_text: str,
    said: Optional[str],
    reply: Optional[str],
    reason: Optional[str],
    knowledge: str,
    excerpt: Optional[str] = None,
) -> list[dict]:
    parts = [f"Moment: {'a step of the playbook' if kind == 'step' else 'an objection from the prospect'}", f"Playbook:\n{playbook_text}"]
    if kind == "objection":
        parts.append(f"The prospect said: «{_clean(said)}»")
        parts.append(f"The rep replied: «{_clean(reply)}»" if _clean(reply) else "The rep did not reply to it.")
    else:
        parts.append(f"What happened: {_clean(reason)}" if _clean(reason) else "What happened: the step was not done.")
        if _clean(said):
            parts.append(f"The rep said: «{_clean(said)}»")
    if excerpt:
        parts.append(f"Call excerpt around that moment:\n{excerpt}")
    if knowledge:
        parts.append(knowledge)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]


EXCERPT_BEFORE = 700
EXCERPT_AFTER = 250


def excerpt(transcript: Any, quote: Optional[str]) -> Optional[str]:
    """What was said around the quote: the lines before it (what the prospect had just said) and a little
    after. None when the quote is not found in the transcript (it is then written from the quote alone)."""
    text = str(transcript or "")
    needle = " ".join(str(quote or "").lower().split())[:60]
    if not text or len(needle) < 8:
        return None
    flat = " ".join(text.split())
    at = flat.lower().find(needle)
    if at < 0:
        return None
    return flat[max(0, at - EXCERPT_BEFORE) : at + len(needle) + EXCERPT_AFTER].strip()


def playbook_text_for_step(step: dict) -> Optional[str]:
    label = _clean(step.get("label"))
    criterion = _clean(step.get("criterion"))
    example = _clean(step.get("example"))
    if not (criterion or example):
        return None
    lines = [f"Step: {label}", f"Counts as done when: {criterion}"] if criterion else [f"Step: {label}"]
    if example:
        lines.append(f"Example of how to say it: {example}")
    return "\n".join(lines)


def playbook_text_for_objection(answer: dict, entry: Optional[dict]) -> Optional[str]:
    guidance = _clean(answer.get("how"))
    if not guidance:
        return None
    label = _clean(answer.get("label")) or _clean((entry or {}).get("category"))
    lines = [f"Objection: {label}"] if label else []
    trigger = _clean((entry or {}).get("trigger"))
    if trigger:
        lines.append(f"What the prospect says: {trigger}")
    lines.append(f"The team's answer: {guidance}")
    return "\n".join(lines)


async def _ask(messages: list[dict]) -> Any:
    from app.services.llm import LLMClient

    return await LLMClient().chat_json(
        messages, model=(settings.COACH_REPLY_MODEL or settings.INTELLIGENCE_MODEL), temperature=0.2, timeout=30.0, max_retries=2, reasoning_effort="minimal", max_tokens=700,
    )


def _accept(raw: Any) -> tuple[Optional[str], bool]:
    """(the line, whether the rep's own reply already did the job). A reply that was fine needs no line."""
    if not isinstance(raw, dict):
        return None, False
    if raw.get("fine") is True:
        return None, True
    say = _clean(raw.get("say")).strip("«»\"“” ")
    return (say[:SAY_MAX_CHARS] or None), False


async def better_reply(messages: list[dict], *, cache_key: str) -> tuple[Optional[str], bool]:
    """(line, fine). The line is None when the playbook gives no base for it or the rep's reply was already
    fine. A failed model call raises: the screen says it could not write it, which is true, instead of
    saying the playbook has nothing."""
    digest = hashlib.sha256((cache_key + "\n" + messages[-1]["content"]).encode()).hexdigest()
    hit = _cache.get(digest)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    raw = await _ask(messages)
    if not isinstance(raw, dict) or ("say" not in raw and "fine" not in raw):
        raw = await _ask(messages)  # a reply with no answer at all (not even a null) is asked once more
    result = _accept(raw)
    if len(_cache) >= _MAX_CACHED:
        _cache.clear()
    _cache[digest] = (time.monotonic(), result)
    return result
