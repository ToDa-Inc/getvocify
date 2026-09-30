"""What the playbooks API modules share: who may write, and the one shape of an editor answer."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, status

from app.services.company import Membership
from app.services.playbooks.structured import OBJECTION_CATEGORIES, editor_view
from app.services.playbooks.versions import can_publish

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
