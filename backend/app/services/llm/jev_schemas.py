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

# Next actions after a call (settings.JEV_DECISIONS_ENABLED): the wording measured on 151 labeled
# calls. "unknown" (low confidence) keeps the C04 verdict.
FOLLOWUP_EMAIL_NEEDED = {
    "question": "followup_email",
    "allowed": ["yes", "no"],
    "on_missing": "unknown",
    "instructions": "Must the rep send an email after this call? Yes when the rep promised to send something "
    "(information, a proposal, success cases, prices, a calendar invite) or the prospect asked for it "
    "('mándame un correo', 'envíame la info').",
    "criteria": {"yes": "an email/invite was promised or asked for", "no": "nothing to send"},
}
CALLBACK_NEEDED = {
    "question": "callback",
    "allowed": ["yes", "no"],
    "on_missing": "unknown",
    "instructions": "Will or should someone call again? Yes when the prospect asked to be called ('llámame luego', "
    "'en enero') or the rep said they would call. No when a meeting was booked, the prospect said a final no or "
    "asked not to be called, they are not the right person, or nobody mentioned calling again.",
    "criteria": {"yes": "a callback was asked for or promised", "no": "no callback"},
}
MEETING_BOOKED = {
    "question": "meeting_agreed",
    "allowed": ["yes", "no"],
    "on_missing": "unknown",
    "instructions": "Was a meeting (demo, visit, video call) at an agreed day accepted by both sides in this call? "
    "A callback is not a meeting.",
    "criteria": {"yes": "both sides accepted a meeting", "no": "no meeting agreed"},
}
DECISION_QUESTIONS = [FOLLOWUP_EMAIL_NEEDED, CALLBACK_NEEDED, MEETING_BOOKED]


def evidence_state(transcript: str, excerpts: list[str], *, limit: int = MAX_STATE_CHARS) -> dict:
    """Keep cited excerpts even when they sit past the first 16k characters."""
    cited = "\n".join(excerpt for excerpt in excerpts if excerpt)
    if len(cited) >= limit:
        return {"transcript": cited[-limit:]}
    head_budget = limit - len(cited) - (1 if cited else 0)
    head = (transcript or "")[: max(head_budget, 0)]
    text = f"{head}\n{cited}".strip() if cited else head
    return {"transcript": text}
