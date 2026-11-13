"""The turn check: has the prospect finished their thought, and is it an objection?

One Jev (System One) call answers both in about 0.3 s, so live help can show its card the
moment the prospect stops instead of waiting for the transcription to settle and a model to
start writing. The answer itself is still written by the suggest model, for this type.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.services.llm.jev import JevClient

# Confidence below this is treated as "not sure": no card, and never a held-back one.
MIN_CONFIDENCE = 0.5
LATEST_CHARS = 1000
CONVERSATION_CHARS = 6000
# Without an answer in this long, the same question is asked again and the first answer wins (a failed one at once).
# 420 checks on 13 Nov 2026: half in 0.25 s, 9 in 10 under 0.34 s, 9 over 1 s (up to 1.7 s); the card waits for it.
AGAIN_S = 0.6

OBJECTIONS: dict[str, str] = {
    "none": "Small talk, agreement, describing their situation, agreeing on a next step or a goodbye, or anything that is not pushback or a product question. Saying they are short of time but still going on with the call («dime, pero rápido») is not pushback. Not recognising who is calling or what it is about («no te ubico», «no caigo», «¿de qué?») is none. A complaint about the provider or tool they have today («nos sale a precio de oro para lo que da», «nadie lo mira») is none: it is about what they have, not pushback against the seller. Being happy with it and not wanting to change is pushback.",
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


def _entry_criterion(entry: dict[str, str]) -> str:
    said = f" They say things like: {entry['trigger']}" if entry.get("trigger") else ""
    if entry.get("label"):
        return (f"Only when they say this or the same thing in other words, not something related to it: the team's own "
                f"objection «{entry['label']}».{said}")
    return (f"Only when they push back with the objection this answer of the team is written for, not something related "
            f"to it: «{entry.get('answer', '')}».{said}")


def questions_for(custom: Optional[dict[str, dict[str, str]]]) -> dict:
    """The two questions. With a playbook, the choices are its answers (described the way the playbook words them),
    plus "none" and a direct question: what they said is matched against what the company answers, never filed under a
    kind from a list in code (Dani, 2026-11-09: «llamamos al cliente y ya está» came back as status quo). Without a
    playbook there is nothing to answer from, and the usual kinds only say whether it is pushback."""
    if not custom:
        return QUESTIONS
    criteria = {
        "none": OBJECTIONS["none"],
        "question": OBJECTIONS["question"],
        **{entry_id: _entry_criterion(entry) for entry_id, entry in custom.items()},
    }
    return {**QUESTIONS, "objection": {**QUESTIONS["objection"], "criteria": criteria}}


async def read_turn(
    conversation: str, latest: str, custom: Optional[dict[str, dict[str, str]]] = None,
) -> dict[str, Optional[bool | str]]:
    """{"finished", "objection"}; both None when the classifier can't be reached. When the turn means one
    of the playbook's own objections (`custom`), objection is "custom" with that entry's id and label."""
    questions = questions_for(custom)
    answers = await _asked_twice_if_slow(
        {"conversation": conversation[-CONVERSATION_CHARS:], "LATEST": latest[-LATEST_CHARS:]}, questions,
    )
    if not answers:
        return {"finished": None, "objection": None}
    reading: dict[str, Optional[bool | str]] = {
        "finished": _sure(answers.get("turn"), {"finished", "continuing"}) != "continuing",
        "objection": _sure(answers.get("objection"), set(questions["objection"]["criteria"])) or "none",
    }
    if reading["objection"] in (custom or {}):
        entry_id = str(reading["objection"])
        reading = {**reading, "objection": "custom", "entry_id": entry_id, "label": custom[entry_id]["label"] or entry_id}
    return reading


async def _asked_twice_if_slow(state: dict[str, Any], questions: dict) -> Optional[dict[str, Any]]:
    """The classifier's answers, or None: asked once, and again when the first has not answered in AGAIN_S or failed."""
    client = JevClient()
    running = {asyncio.ensure_future(client._post_systemone(state, questions))}
    again = True
    try:
        while running:
            done, running = await asyncio.wait(running, timeout=AGAIN_S if again else None, return_when=asyncio.FIRST_COMPLETED)
            answers = next((t.result() for t in done if t.result()), None)
            if answers:
                return answers
            if again and (not done or not running):  # still waiting, or the only one failed
                running.add(asyncio.ensure_future(client._post_systemone(state, questions)))
                again = False
        return None
    finally:
        for task in running:
            task.cancel()
