"""What the playbooks API modules share: who may write, and the one shape of an editor answer."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel

from app.services.company import Membership
from app.services.playbooks.imports import start_import
from app.services.playbooks.knowledge import normalize_knowledge, sections
from app.services.playbooks.structured import OBJECTION_CATEGORIES, editor_view
from app.services.playbooks.versions import can_publish

logger = logging.getLogger(__name__)

SALES_ROLES_FLAG = "SALES_ROLES_ENABLED"
MANAGE_ROLES = frozenset({"owner", "admin"})


def require_manager(membership: Membership) -> None:
    if not can_publish(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owner o admin pueden importar un playbook")


def editor_response(sales_motion_key: str, snapshot: dict) -> dict:
    """The one shape of GET /editor, PUT /draft and DELETE /draft. `source` stays the
    state of what is shown ("draft" | "published" | "empty", which the current editor
    reads); the material it was structured from is `source_doc` ({id, kind, name} | null)."""
    version = snapshot.get("version")
    return {
        "sales_motion_key": sales_motion_key,
        "source": snapshot["state"],
        "source_doc": snapshot.get("source"),
        "version_id": (version or {}).get("id"),
        "updated_at": (version or {}).get("updated_at"),
        "has_live": bool(snapshot.get("has_live")),
        "paused": bool(snapshot.get("paused")),
        "categories": list(OBJECTION_CATEGORIES),
        **editor_view(version),
    }


_transcriber = None


def set_playbook_transcriber(transcriber) -> None:
    global _transcriber
    _transcriber = transcriber


async def audio_text(payload: str) -> str:
    transcriber = _transcriber
    if transcriber is None:
        import base64

        from app.services.stt_batch import transcribe_bytes

        raw = base64.b64decode(payload)
        return await transcribe_bytes(raw, source="playbook_import")
    result = transcriber(payload)
    if asyncio.iscoroutine(result):
        return await result
    return result


class StructureRequest(BaseModel):
    """Material a manager gives Vocify: pasted text, or a PDF / an audio recording in base64."""

    kind: str
    payload: str = ""
    name: Optional[str] = None


def unreadable(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": code})


def fill_failed() -> HTTPException:
    return unreadable("fill_failed")


async def read_source(body: StructureRequest) -> str:
    """The text of what the manager gave us (pasted text, a PDF or an audio recording, read
    the way imports read them). 422 `detail.code`: pdf_encrypted, pdf_has_no_text,
    audio_has_no_speech, stt_unavailable, unsupported_source, empty_source."""
    stt = None
    if body.kind == "audio":
        try:
            spoken = await audio_text(body.payload)
            stt = lambda _raw, spoken=spoken: spoken  # noqa: E731
        except Exception:
            stt = None
    record = start_import(
        import_id=f"source:{uuid.uuid4()}", kind=body.kind, payload=body.payload, active_version_id=None, stt=stt,
    )
    if record.get("status") != "ready":
        raise unreadable(str(record.get("reason") or "unsupported_source"))
    text = str((record.get("draft") or {}).get("text") or "").strip()
    if not text:
        raise unreadable("empty_source")
    return text


def product_context(supabase, company_id: str) -> str:
    """The product description the company wrote in Settings → Offer ("" when there is none)."""
    try:
        rows = supabase.table("companies").select("product_context").eq("id", company_id).limit(1).execute().data or []
        return str((rows[0] if rows else {}).get("product_context") or "").strip()
    except Exception:
        logger.warning("product_context not read for playbook fill")
        return ""


def company_context(supabase, repository, company_id: str) -> str:
    """What the company says about itself, for a model that writes on its behalf: the product
    description and "Vuestra empresa" (only the parts that hold something)."""
    parts = []
    offer = product_context(supabase, company_id)
    if offer:
        parts.append(f"Product: {offer}")
    try:
        data = normalize_knowledge((repository.get_knowledge(company_id) or {}).get("data"))
        filled = {key: data[key] for key in sections(data)}
        if filled:
            parts.append(json.dumps(filled, ensure_ascii=False))
    except Exception:
        logger.warning("company knowledge not read for playbook fill")
    return "\n".join(parts)

