"""Post-transcript screening for Vocify-placed calls.

Decides whether a connected call had a real two-way conversation worth
running LLM extraction on. Twilio dial status (busy/no-answer/etc.) is
handled separately via the dial-status webhook.
"""

from __future__ import annotations

from typing import Literal

from app.services.transcript_turns import normalize_speaker, parse_transcript_turns

ScreeningOutcome = Literal["connected", "voicemail", "no_response"]

MIN_CONNECTED_DURATION_SEC = 30
MIN_SECONDARY_SPEAKER_WORDS = 8
MIN_TURNS_PER_SPEAKER = 2


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
    if not stats:
        # Undiarized audio: treat long monologues as voicemail prompts.
        return "voicemail"

    speakers = sorted(stats.items(), key=lambda item: item[1]["words"], reverse=True)
    if len(speakers) == 1:
        return "voicemail"

    if duration < MIN_CONNECTED_DURATION_SEC:
        return "no_response"

    primary_words = speakers[0][1]["words"]
    secondary_words = speakers[1][1]["words"]
    secondary_turns = speakers[1][1]["turns"]

    if secondary_words < MIN_SECONDARY_SPEAKER_WORDS:
        return "no_response"
    if secondary_turns < MIN_TURNS_PER_SPEAKER:
        return "no_response"
    if secondary_words < max(3, primary_words // 10):
        return "no_response"

    return "connected"
