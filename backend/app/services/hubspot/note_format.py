"""
Format HubSpot CRM note bodies from call extraction + transcript.

HubSpot `hs_note_body` accepts HTML for timeline readability.
"""

from __future__ import annotations

import html
import re
from typing import Optional

from app.services.transcript_turns import parse_transcript_turns


_HEADING_RE = re.compile(r"^(#{1,3})\s+(\S.*)$")
_NEXT_STEPS_HEADING_RE = re.compile(r"^(próximos\s+pasos|next\s+steps)$", re.I)
_LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s+")
_NESTED_LIST_ITEM_RE = re.compile(r"^\s{2,}[-*+]\s+")
_STRIP_LIST_MARKER_RE = re.compile(r"^\s*[-*+]\s+")


def summary_looks_markdown(summary: str) -> bool:
    return bool(re.search(r"(?m)^#{1,3}\s+\S", summary or ""))


def first_bullet_plaintext(summary: str) -> Optional[str]:
    """First markdown bullet, for deal description (no heading hashes)."""
    for line in (summary or "").splitlines():
        s = line.strip()
        if _LIST_ITEM_RE.match(s):
            return _STRIP_LIST_MARKER_RE.sub("", s).replace("**", "").strip() or None
    return None


def _inline_html(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def format_summary_html(summary: str) -> str:
    """
    Granola-style markdown (# heading, - bullets, nested bullets, **bold**)
    to HubSpot-safe HTML. Prose summaries stay as paragraphs.
    Drops a Próximos pasos / Next steps heading so tasks are not duplicated
    in the note body.
    """
    text = (summary or "").strip()
    if not text:
        return ""
    if not summary_looks_markdown(text):
        parts = []
        for para in re.split(r"\n{2,}", text):
            para = para.strip()
            if para:
                parts.append(f"<p>{_inline_html(para)}</p>")
        return "\n".join(parts)

    sections: list[tuple[str, list[tuple[str, list[str]]]]] = []
    current_title = ""
    items: list[tuple[str, list[str]]] = []
    last_children: list[str] | None = None

    def flush():
        if current_title or items:
            sections.append((current_title, list(items)))

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            title = hm.group(2).strip()
            if _NEXT_STEPS_HEADING_RE.match(title):
                flush()
                break
            flush()
            current_title = title
            items = []
            last_children = None
            continue
        nested = bool(_NESTED_LIST_ITEM_RE.match(line))
        bullet = bool(_LIST_ITEM_RE.match(line))
        if not bullet:
            items.append((line.strip(), []))
            last_children = items[-1][1]
            continue
        body = _STRIP_LIST_MARKER_RE.sub("", line).strip()
        if nested and last_children is not None:
            last_children.append(body)
        else:
            items.append((body, []))
            last_children = items[-1][1]
    flush()

    html_parts: list[str] = []
    for title, sect_items in sections:
        if title:
            html_parts.append(f"<h3>{_inline_html(title)}</h3>")
        if sect_items:
            lis = []
            for text_item, children in sect_items:
                nested_html = ""
                if children:
                    nested_html = "<ul>" + "".join(f"<li>{_inline_html(c)}</li>" for c in children) + "</ul>"
                lis.append(f"<li>{_inline_html(text_item)}{nested_html}</li>")
            html_parts.append("<ul>" + "".join(lis) + "</ul>")
    return "\n".join(html_parts)


def looks_spanish(text: str) -> bool:
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


_OUTCOME_LABELS_EN = {"converted": "Converted", "on_hold": "On hold", "lost": "Lost"}
_OUTCOME_LABELS_ES = {"converted": "Convertido", "on_hold": "En pausa", "lost": "Perdido"}


def format_call_outcome_section(
    *,
    call_outcome: str,
    lost_reason: Optional[str],
    spanish: bool,
) -> str:
    """
    HTML block for the rep-marked call outcome - either appended to the
    memo's own transcript note (merged case, see format_hubspot_note_body
    below) or used as the whole body of a small standalone note (see
    format_standalone_call_outcome_note_body / call_outcome.py's
    _ensure_lost_reason_note). Only Lost carries a free-text reason today;
    Converted/On Hold have nothing beyond the outcome label itself, since
    their state is already visible on the contact's hs_lead_status.
    """
    label = (_OUTCOME_LABELS_ES if spanish else _OUTCOME_LABELS_EN).get(call_outcome, call_outcome)
    title = "Resultado de la llamada (Vocify)" if spanish else "Call outcome (Vocify)"
    parts = [f"<p><strong>{html.escape(title)}:</strong> {html.escape(label)}</p>"]
    reason = (lost_reason or "").strip()
    if call_outcome == "lost" and reason:
        reason_label = "Motivo" if spanish else "Reason"
        parts.append(f"<p><strong>{html.escape(reason_label)}:</strong> {html.escape(reason)}</p>")
    return "\n".join(parts)


def format_standalone_call_outcome_note_body(*, lost_reason: Optional[str], spanish: Optional[bool] = None) -> str:
    """
    Whole body for the standalone Lost-reason note - used only when the
    memo's own transcript note doesn't exist or wasn't created in this sync
    (see call_outcome.py's _ensure_lost_reason_note for exactly when).
    """
    if spanish is None:
        spanish = looks_spanish(lost_reason or "")
    return format_call_outcome_section(call_outcome="lost", lost_reason=lost_reason, spanish=spanish)


def format_hubspot_note_body(
    *,
    summary: Optional[str],
    transcript: str,
    source: Optional[str] = None,
    call_outcome: Optional[str] = None,
    lost_reason: Optional[str] = None,
) -> str:
    """
    Build an HTML HubSpot note: summary first, then readable transcript,
    then (when call_outcome == 'lost') a visually separated outcome section
    - see format_call_outcome_section. Merging it in here (one note, not
    two) is deliberate: a rep marking Lost on the same memo that generates
    the transcript note would otherwise get two back-to-back timeline
    entries for the same call, which reads as noise (see call_outcome.py
    module docstring / sync.py Step 7 for the merge bookkeeping).

    Strips raw SPEAKER: S1 diarization labels into human speaker names.
    """
    transcript = (transcript or "").strip()
    summary = (summary or "").strip()
    spanish = looks_spanish(f"{summary}\n{transcript}\n{lost_reason or ''}")

    parts: list[str] = []

    # Header
    if source == "hubspot_call":
        title = "Nota de llamada (Vocify)" if spanish else "Call note (Vocify)"
    else:
        title = "Nota Vocify" if spanish else "Vocify note"
    parts.append(f"<p><strong>{html.escape(title)}</strong></p>")

    # Summary: Granola-style markdown when present; otherwise a labeled paragraph.
    if summary:
        if summary_looks_markdown(summary):
            html_summary = format_summary_html(summary)
            if html_summary:
                parts.append(html_summary)
        else:
            summary_label = "Resumen" if spanish else "Summary"
            parts.append(f"<p><strong>{html.escape(summary_label)}</strong></p>")
            html_summary = format_summary_html(summary)
            if html_summary:
                parts.append(html_summary)
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

    if call_outcome == "lost":
        parts.append("<hr>")
        parts.append(format_call_outcome_section(call_outcome=call_outcome, lost_reason=lost_reason, spanish=spanish))

    body = "\n".join(parts)
    if len(body) > 65536:
        body = body[:65530] + "…"
    return body
