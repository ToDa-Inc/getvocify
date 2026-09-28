"""Question specs for Jev. Missing answers stay unknown."""

from __future__ import annotations

MAX_STATE_CHARS = 16000

OBJECTION_KIND = {
    "question": "objection_kind",
    "allowed": ["price", "timing", "obstacle", "unknown"],
    "on_missing": "unknown",
    "instructions": "Is the remark a commercial price objection, a timing objection, a practical obstacle, or unknown? Do not treat 'I am driving' as price or timing.",
}

MEETING_AGREED = {
    "question": "meeting_agreed",
    "allowed": ["agreed", "not_agreed", "unknown"],
    "on_missing": "unknown",
    "instructions": "Did both sides agree to meet? A suggestion that was not confirmed stays unknown.",
}

PAIN_CONFIRMED = {
    "question": "pain_confirmed",
    "allowed": ["confirmed", "not_confirmed", "unknown"],
    "on_missing": "unknown",
    "instructions": "Did the prospect confirm a concrete pain? If it was not stated, stay unknown.",
}

INTELLIGENCE_QUESTIONS = [MEETING_AGREED, PAIN_CONFIRMED]


def evidence_state(transcript: str, excerpts: list[str], *, limit: int = MAX_STATE_CHARS) -> dict:
    """Keep cited excerpts even when they sit past the first 16k characters."""
    cited = "\n".join(excerpt for excerpt in excerpts if excerpt)
    if len(cited) >= limit:
        return {"transcript": cited[-limit:]}
    head_budget = limit - len(cited) - (1 if cited else 0)
    head = (transcript or "")[: max(head_budget, 0)]
    text = f"{head}\n{cited}".strip() if cited else head
    return {"transcript": text}
