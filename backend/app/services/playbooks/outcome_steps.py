"""Playbook steps whose result the rep declares, never the transcript.

Whether a meeting got booked is what the rep marks when the call ends (`memos.rep_outcome`),
not what a model reads into the conversation. A step about booking it is "met" only when the
rep marked the meeting as booked, "missed" when they marked anything else, and has no status
until they mark something.
"""

from __future__ import annotations

import re
import unicodedata

MEETING_BOOKED = "meeting_booked"
STEP_OUTCOMES = frozenset({MEETING_BOOKED})

_MEETING = re.compile(r"\b(meeting|reunion|reuniones|demo|cita|videollamada)\b")
_BOOK = re.compile(r"\b(cerr\w*|agend\w*|acept\w*|acord\w*|reserv\w*|book\w*|schedul\w*|fij\w*)\b")


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in folded if not unicodedata.combining(c)).lower()


def step_outcome(step: dict) -> str | None:
    """The rep outcome that settles this step: its own `outcome`, or MEETING_BOOKED when the
    step is about getting a meeting accepted (label or criterion name a meeting and booking it)."""
    explicit = str(step.get("outcome") or "").strip()
    if explicit:
        return explicit if explicit in STEP_OUTCOMES else None
    text = _plain(f"{step.get('label') or ''} {step.get('criterion') or ''}")
    if _MEETING.search(text) and _BOOK.search(text):
        return MEETING_BOOKED
    return None


def status_from_rep_outcome(outcome: str, rep_outcome: str | None) -> str:
    """met / missed from what the rep declared; unknown while nothing is declared."""
    if not rep_outcome:
        return "unknown"
    return "met" if rep_outcome == outcome else "missed"
