"""The turn check: has the prospect finished their thought, and is it an objection?

One Jev (System One) call answers both in about 0.3 s, so live help can show its card the
moment the prospect stops instead of waiting for the transcription to settle and a model to
start writing. The answer itself is still written by the suggest model, for this type.
"""

from __future__ import annotations

from typing import Optional

from app.services.llm.jev import JevClient

# Confidence below this is treated as "not sure": no card, and never a held-back one.
MIN_CONFIDENCE = 0.5
LATEST_CHARS = 1000
CONVERSATION_CHARS = 6000

OBJECTIONS: dict[str, str] = {
    "none": "Small talk, agreement, describing their situation, agreeing on a next step or a goodbye, or anything that is not pushback or a product question. Saying they are short of time but still going on with the call («dime, pero rápido») is not pushback. Not recognising who is calling or what it is about («no te ubico», «no caigo», «¿de qué?») is none.",
    "price": "Too expensive, budget, cost.",
    "timing": "Pushback on the moment: not now, not buying anything at the moment, cannot talk now (in a meeting, travelling or away for a period), call me in a few months. Not recognising the caller is not timing.",
    "authority": "Someone else decides or must approve.",
    "competitor": "Already use or prefer another tool.",
    "status_quo": "Happy with how they work today, no need to change.",
    "trust": "Doubts, fear it won't work or will make mistakes, wants proof.",
    "question": "A direct question about the product or offer.",
}

QUESTIONS = {
    "turn": {
        "type": "choice",
        "instructions": "Has the prospect finished what they wanted to say in LATEST, or are they mid-thought and likely to keep talking?",
        "criteria": {
            "finished": "A complete thought: a statement, objection or question that stands on its own.",
            "continuing": "Cut off or mid-thought: trailing connector, unfinished clause, or clearly more to come.",
        },
    },
    "objection": {
        "type": "choice",
        "instructions": "Does LATEST (said by the prospect on a sales call) push back or ask about the product?",
        "criteria": OBJECTIONS,
    },
}


def _sure(answer: object, allowed) -> Optional[str]:
    if not isinstance(answer, dict) or answer.get("choice") not in allowed:
        return None
    try:
        confidence = float(answer.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    return answer["choice"] if confidence >= MIN_CONFIDENCE else None


def questions_for(custom: Optional[dict[str, dict[str, str]]]) -> dict:
    """The two questions. The team's own objections join the fixed kinds as choices, described the way
    the playbook words them, so a turn that means one of them is not filed under "none"."""
    if not custom:
        return QUESTIONS
    criteria = {
        **OBJECTIONS,
        **{
            entry_id: f"Only when they say this or the same thing in other words, not something related to it: the team's own objection «{entry['label']}»."
            + (f" They say things like: {entry['trigger']}" if entry["trigger"] else "")
            for entry_id, entry in custom.items()
        },
    }
    return {**QUESTIONS, "objection": {**QUESTIONS["objection"], "criteria": criteria}}


async def read_turn(
    conversation: str, latest: str, custom: Optional[dict[str, dict[str, str]]] = None,
) -> dict[str, Optional[bool | str]]:
    """{"finished", "objection"}; both None when the classifier can't be reached. When the turn means one
    of the playbook's own objections (`custom`), objection is "custom" with that entry's id and label."""
    answers = await JevClient()._post_systemone(
        {"conversation": conversation[-CONVERSATION_CHARS:], "LATEST": latest[-LATEST_CHARS:]},
        questions_for(custom),
    )
    if not answers:
        return {"finished": None, "objection": None}
    reading: dict[str, Optional[bool | str]] = {
        "finished": _sure(answers.get("turn"), {"finished", "continuing"}) != "continuing",
        "objection": _sure(answers.get("objection"), {*OBJECTIONS, *(custom or {})}) or "none",
    }
    if reading["objection"] in (custom or {}):
        entry_id = str(reading["objection"])
        reading = {**reading, "objection": "custom", "entry_id": entry_id, "label": custom[entry_id]["label"]}
    return reading
