"""
Format HubSpot CRM note bodies from call extraction + transcript.

HubSpot `hs_note_body` accepts HTML for timeline readability.
"""

from __future__ import annotations

import html
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


def _looks_spanish(text: str) -> bool:
    t = (text or "").lower()
    if re.search(r"[áéíóúñ¿¡]", t):
        return True
    cues = ("hola", "gracias", "nosotros", "llamada", "próxim", "proxim", "sí", "que tal")
    return sum(1 for c in cues if c in t) >= 2


def _speaker_display(raw: Optional[str], spanish: bool) -> str:
    s = (raw or "").strip().upper().replace(" ", "")
    m = re.search(r"(\d+)", s)
    num = m.group(1) if m else None
    if num == "1":
        return "Comercial" if spanish else "Rep"
    if num == "2":
        return "Contacto" if spanish else "Prospect"
    if num:
        return f"Interlocutor {num}" if spanish else f"Speaker {num}"
    return "Interlocutor" if spanish else "Speaker"


def parse_transcript_turns(transcript: str) -> list[dict]:
    """Parse Speechmatics-style SPEAKER: S1 blocks into turns."""
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


def format_hubspot_note_body(
    *,
    summary: Optional[str],
    transcript: str,
    source: Optional[str] = None,
) -> str:
    """
    Build an HTML HubSpot note: summary first, then readable transcript.

    Strips raw SPEAKER: S1 diarization labels into human speaker names.
    """
    transcript = (transcript or "").strip()
    summary = (summary or "").strip()
    spanish = _looks_spanish(f"{summary}\n{transcript}")

    parts: list[str] = []

    # Header
    if source == "hubspot_call":
        title = "Nota de llamada (Vocify)" if spanish else "Call note (Vocify)"
    else:
        title = "Nota Vocify" if spanish else "Vocify note"
    parts.append(f"<p><strong>{html.escape(title)}</strong></p>")

    # Summary section (required structure even if short)
    summary_label = "Resumen" if spanish else "Summary"
    parts.append(f"<p><strong>{html.escape(summary_label)}</strong></p>")
    if summary:
        for para in re.split(r"\n{2,}", summary):
            para = para.strip()
            if para:
                parts.append(f"<p>{html.escape(para)}</p>")
    else:
        missing = (
            "Sin resumen disponible — revisar la transcripción."
            if spanish
            else "No summary available — see transcript below."
        )
        parts.append(f"<p><em>{html.escape(missing)}</em></p>")

    # Transcript section
    if transcript:
        tx_label = "Transcripción" if spanish else "Transcript"
        parts.append(f"<p><strong>{html.escape(tx_label)}</strong></p>")
        turns = parse_transcript_turns(transcript)
        for turn in turns:
            text = html.escape(turn["text"]).replace("\n", "<br>")
            if turn.get("speaker"):
                label = html.escape(_speaker_display(turn["speaker"], spanish))
                parts.append(
                    f"<p><strong>{label}:</strong><br>{text}</p>"
                )
            else:
                parts.append(f"<p>{text}</p>")

    body = "\n".join(parts)
    if len(body) > 65536:
        body = body[:65530] + "…"
    return body
