"""Post-transcript screening for Vocify-placed calls.

Twilio already reports busy / no-answer / failed on the dial-status webhook.
This module only decides whether a *connected* recording should skip LLM
extraction (true voicemail greeting) or be analyzed.

Calls of 30s+ with any transcript are extracted. Diarization imbalance is not
treated as no-answer — a long two-party demo often lands 90% of words on one
speaker.
"""

from __future__ import annotations

import re
from typing import Literal

from app.services.transcript_turns import normalize_speaker, parse_transcript_turns

ScreeningOutcome = Literal["connected", "voicemail", "no_response"]

MIN_CONNECTED_DURATION_SEC = 30

_SPEAKER_ONLY = re.compile(
    r"^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*:?\s*$",
    re.IGNORECASE,
)
_SHORT_REPLY = re.compile(
    r"^(s[ií]|vale+|ok+|okay|claro|de acuerdo|perfecto|genial|yes|yeah)\.?!?$",
    re.IGNORECASE,
)
_VOICEMAIL_HINT = re.compile(
    r"despu[eé]s del tono|buz[oó]n de voz|leave (?:a |your )?message|"
    r"no puedo atender|no est[aá] disponible|voicemail",
    re.IGNORECASE,
)


def _content_lines(transcript: str) -> list[str]:
    lines: list[str] = []
    for raw in (transcript or "").splitlines():
        trimmed = raw.strip()
        if not trimmed or _SPEAKER_ONLY.match(trimmed):
            continue
        lines.append(trimmed)
    return lines


def looks_like_collapsed_dialogue(transcript: str) -> bool:
    """True when STT left one speaker label but the text is still a two-way call.

    Deepgram often collapses both sides onto S1. Treating that as voicemail
    skips extraction on real conversations.
    """
    lines = _content_lines(transcript)
    if len(lines) < 4:
        return False
    questions = sum(1 for line in lines if "?" in line or "¿" in line)
    short_replies = sum(1 for line in lines if _SHORT_REPLY.match(line.rstrip(".,!")))
    return questions >= 2 and (short_replies >= 1 or len(lines) >= 8)


def looks_like_voicemail(transcript: str) -> bool:
    return bool(_VOICEMAIL_HINT.search(transcript or ""))


def _speaker_stats(transcript: str) -> dict[str, dict[str, int]]:
    """Reuses the shared turn parser instead of a bespoke regex.

    `sanitize_user_transcript` serializes diarized turns as
    "SPEAKER: S1\\ntext" blocks (see transcript_turns.serialize_transcript_turns),
    not the "S1: text" inline shorthand — parse_transcript_turns understands
    both, plus named-speaker variants, so screening stays correct even if
    upstream formatting changes.
    """
    stats: dict[str, dict[str, int]] = {}
    for turn in parse_transcript_turns(transcript):
        speaker = normalize_speaker(turn.get("speaker"))
        if not speaker:
            continue
        text = (turn.get("text") or "").strip()
        words = len(text.split()) if text else 0
        bucket = stats.setdefault(speaker, {"turns": 0, "words": 0})
        bucket["turns"] += 1
        bucket["words"] += words
    return stats


def classify_call_outcome(transcript: str, duration: float) -> ScreeningOutcome:
    """Classify a connected call from its diarized transcript."""
    cleaned = (transcript or "").strip()
    if not cleaned:
        return "no_response"

    stats = _speaker_stats(cleaned)
    one_sided = len(stats) <= 1

    if duration >= MIN_CONNECTED_DURATION_SEC:
        if (
            one_sided
            and looks_like_voicemail(cleaned)
            and not looks_like_collapsed_dialogue(cleaned)
        ):
            return "voicemail"
        return "connected"

    if one_sided:
        return "voicemail"
    return "no_response"
