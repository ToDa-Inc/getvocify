"""Parse, dedupe, and serialize diarized call transcripts."""

from __future__ import annotations

import re
from typing import Optional

_SPEAKER_LINE = re.compile(
    r"^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*:?\s*$",
    re.IGNORECASE,
)
_SPEAKER_INLINE = re.compile(
    r"^(?:SPEAKER:\s*)?(S\d+|Speaker\s*\d+)\s*[:.-]\s*(.+)$",
    re.IGNORECASE,
)


def normalize_speaker(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    m = re.search(r"(\d+)", str(raw))
    return f"S{m.group(1)}" if m else str(raw).strip().upper()


def parse_transcript_turns(transcript: str) -> list[dict]:
    """Parse Speechmatics-style SPEAKER: S1 / Speaker 1 blocks into turns."""
    raw = (transcript or "").strip()
    if not raw:
        return []

    turns: list[dict] = []
    current: Optional[dict] = None
    for line in raw.splitlines():
        trimmed = line.strip()
        if not trimmed:
            if current and current.get("text"):
                current["text"] += "\n"
            continue
        inline = _SPEAKER_INLINE.match(trimmed)
        if inline:
            if current and (current.get("text") or "").strip():
                turns.append(current)
            current = {"speaker": inline.group(1), "text": inline.group(2).strip()}
            continue
        only = _SPEAKER_LINE.match(trimmed)
        if only:
            if current and (current.get("text") or "").strip():
                turns.append(current)
            current = {"speaker": only.group(1), "text": ""}
            continue
        if not current:
            current = {"speaker": None, "text": trimmed}
        else:
            current["text"] = f"{current['text']}\n{trimmed}" if current["text"] else trimmed

    if current and (current.get("text") or "").strip():
        turns.append(current)

    if not turns and raw:
        return [{"speaker": None, "text": raw}]

    out = []
    for t in turns:
        text = re.sub(r"\n+$", "", (t.get("text") or "")).strip()
        if text:
            out.append({"speaker": t.get("speaker"), "text": text})
    return out


def _fingerprint(turn: dict) -> str:
    speaker = normalize_speaker(turn.get("speaker")) or ""
    text = re.sub(r"\s+", " ", (turn.get("text") or "")).strip().lower()
    return f"{speaker}:{text[:160]}"


def dedupe_repeated_conversation(turns: list[dict]) -> list[dict]:
    """Drop a second copy of the same call (Speaker 1 view + SPEAKER: S1 raw)."""
    if len(turns) < 4:
        return turns
    fps = [_fingerprint(t) for t in turns]
    n = len(turns)
    if n % 2 == 0:
        mid = n // 2
        if fps[:mid] == fps[mid:]:
            return turns[:mid]
    for size in range(2, n // 2 + 1):
        if fps[:size] == fps[size : size * 2] and size * 2 == n:
            return turns[:size]
    return turns


def merge_consecutive_turns(turns: list[dict]) -> list[dict]:
    out: list[dict] = []
    for turn in turns:
        speaker = normalize_speaker(turn.get("speaker"))
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        if out and normalize_speaker(out[-1].get("speaker")) == speaker:
            out[-1]["text"] = f"{out[-1]['text']}\n{text}"
        else:
            out.append({"speaker": speaker, "text": text})
    return out


def serialize_transcript_turns(turns: list[dict]) -> str:
    parts: list[str] = []
    for turn in turns:
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        speaker = normalize_speaker(turn.get("speaker"))
        if speaker:
            parts.append(f"SPEAKER: {speaker}\n{text}")
        else:
            parts.append(text)
    return "\n\n".join(parts)


def normalize_diarized_transcript(transcript: str) -> str:
    turns = merge_consecutive_turns(
        dedupe_repeated_conversation(parse_transcript_turns(transcript))
    )
    if not turns:
        return (transcript or "").strip()
    return serialize_transcript_turns(turns)
