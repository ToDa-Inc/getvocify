"""Playbook imports stay drafts. A failed file does not replace the active version."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

_CONTRADICTION = re.compile(r"\bnunca\b.*\bsiempre\b|\bsiempre\b.*\bnunca\b", re.IGNORECASE | re.DOTALL)


def start_import(
    *,
    import_id: str,
    kind: str,
    payload: str,
    active_version_id: Optional[str],
    existing: Optional[dict] = None,
    stt: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """Return an import record. Never publishes and never creates a commercial memo."""
    if existing and existing.get("id") == import_id:
        return {
            **existing,
            "duplicated": False,
            "published": False,
            "versions_created": 0,
        }

    text = payload or ""
    reason = None
    status = "ready"
    if kind == "pdf":
        text = _pdf_text(payload)
        if not text.strip():
            status = "failed"
            reason = "pdf_has_no_text"
    elif kind == "audio":
        if stt is None:
            status = "failed"
            reason = "stt_unavailable"
            text = ""
        else:
            text = stt(payload)
            if not text.strip():
                status = "failed"
                reason = "audio_has_no_speech"
    elif kind != "text":
        status = "failed"
        reason = "unsupported_source"
        text = ""

    contradictions = []
    if status == "ready" and _CONTRADICTION.search(text):
        contradictions.append("siempre/nunca")

    draft = None
    if status == "ready":
        draft = {
            "text": text.strip(),
            "source_ref": f"{kind}:{import_id}",
            "contradictions": contradictions,
        }

    return {
        "id": import_id,
        "import_id": import_id,
        "status": status,
        "reason": reason,
        "kind": kind,
        "draft": draft,
        "active_version_id": active_version_id,
        "active_version_unchanged": True,
        "published": False,
        "versions_created": 0,
        "memo_id": None,
        "crm_sync": False,
    }


def _pdf_text(payload: str) -> str:
    if payload.lstrip().startswith("%PDF") and "BT" not in payload and "Tj" not in payload:
        return ""
    return payload
