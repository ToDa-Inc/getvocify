"""Playbook imports stay drafts. A failed file does not replace the active version."""

from __future__ import annotations

import base64
import io
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
        text, pdf_reason = read_pdf(payload)
        if pdf_reason:
            status = "failed"
            reason = pdf_reason
            text = ""
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


def _pdf_bytes(payload: str) -> bytes:
    stripped = (payload or "").lstrip()
    if stripped.startswith("%PDF"):
        return stripped.encode("latin-1", errors="ignore")
    try:
        return base64.b64decode(stripped, validate=True)
    except Exception:
        return b""


def read_pdf(payload: str) -> tuple[str, Optional[str]]:
    """Extract text with pypdf. An encrypted or empty file does not become a draft."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(_pdf_bytes(payload)))
        if reader.is_encrypted:
            return "", "pdf_encrypted"
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return "", "pdf_has_no_text"
    if not text.strip():
        return "", "pdf_has_no_text"
    return text, None
