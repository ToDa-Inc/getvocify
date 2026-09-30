"""Playbook intake API: one document in, a draft per call type (and the company's knowledge) out.

POST /playbooks/structure reads the whole company's document; POST /playbooks/{key}/structure structures it for
one call type when the caller already knows which. Neither publishes anything."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.playbooks.api_support import audio_text, editor_response, require_manager
from app.services.playbooks.imports import start_import
from app.services.playbooks.intake import candidate_types, ensure_payload, public_candidates
from app.services.playbooks.knowledge import merge_knowledge, sections
from app.services.playbooks.repository import PlaybookRepository, get_playbook_repository
from app.services.playbooks.routing import motions_and_stored, routing_enabled
from app.services.playbooks.structure import (
    detect_language,
    set_playbook_structure_llm,
    split_source,
    structure_source,
)
from app.services.playbooks.structured import normalize_objections, normalize_qualification

logger = logging.getLogger(__name__)

__all__ = ["router", "set_playbook_structure_llm"]

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbook-intake"])

class StructureRequest(BaseModel):
    kind: str
    payload: str = ""
    name: Optional[str] = None


_DEFAULT_SOURCE_NAMES = {
    "es": {"text": "Texto pegado", "pdf": "PDF", "audio": "Audio"},
    "en": {"text": "Pasted text", "pdf": "PDF", "audio": "Audio"},
}


def _unreadable(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": code})


async def _read_source(body: StructureRequest) -> str:
    """The text of what the manager gave us (pasted text, a PDF or an audio recording, read
    the way imports read them). 422 `detail.code`: pdf_encrypted, pdf_has_no_text,
    audio_has_no_speech, stt_unavailable, unsupported_source, empty_source."""
    stt = None
    if body.kind == "audio":
        try:
            spoken = await audio_text(body.payload)
            stt = lambda _raw, spoken=spoken: spoken
        except Exception:
            stt = None
    record = start_import(
        import_id=f"source:{uuid.uuid4()}", kind=body.kind, payload=body.payload, active_version_id=None, stt=stt,
    )
    if record.get("status") != "ready":
        raise _unreadable(str(record.get("reason") or "unsupported_source"))
    text = str((record.get("draft") or {}).get("text") or "").strip()
    if not text:
        raise _unreadable("empty_source")
    return text


def _keep_source(repository: PlaybookRepository, membership: Membership, key: Optional[str], body: StructureRequest, text: str, lang: str):
    name = (body.name or "").strip()[:200] or _DEFAULT_SOURCE_NAMES[lang].get(body.kind, body.kind)
    try:
        return repository.save_source(membership.company_id, key, body.kind, name, text)
    except Exception:  # keeping the original is a courtesy; it never blocks structuring
        logger.exception("playbook source not saved")
        return None


@router.post("/structure")
async def structure_company_source(
    body: StructureRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    """One input for the whole company. Vocify detects which call types the document covers
    (with routing on: the five catalog types and the company's own types that have a rule;
    off: discovery and closing), structures each with ONE model call and saves each as that
    type's draft (a live version stays live until published). If the model fails nothing is
    saved and `fallback` is true: the caller asks which call type it is and uses
    POST /{key}/structure."""
    require_manager(membership)
    repository = get_playbook_repository()
    text = await _read_source(body)
    lang = detect_language(text)
    routing = routing_enabled(supabase, membership.company_id)
    motions, stored = motions_and_stored(repository.list_types(membership.company_id, include_draft=False))
    candidates = candidate_types(routing, motions, stored, lang)
    source = _keep_source(repository, membership, None, body, text, lang)
    result = await split_source(text, candidates, lang)

    found = {item["key"]: item for item in result["types"]}
    items, reasons = [], {}
    for candidate in candidates:  # candidate order (catalog order), not the model's
        item = found.get(candidate["key"])
        if item is None:
            continue
        key = item["key"]
        criteria = normalize_qualification(item.get("qualification"))
        reasons[key] = item["reason"]
        items.append({
            "key": key,
            "steps": item["steps"],
            "entries": normalize_objections(item["objections"]),
            # A document without criteria must not wipe the ones already in the draft.
            "qualification": criteria or None,
            "ensure": ensure_payload(key, routing=routing, lang=lang),
        })
    existing, merged, filled = _merge_company(repository, membership.company_id, result.get("company"))
    source_id = (source or {}).get("id")
    saved = {"types": [], "knowledge": None}
    if items or filled:
        saved = repository.save_intake(membership.company_id, items, merged if filled else None, source_id)
    types = [
        {
            "sales_motion_key": entry["sales_motion_key"],
            "reason": reasons[entry["sales_motion_key"]],
            "editor": editor_response(
                entry["sales_motion_key"],
                repository.editor_snapshot(membership.company_id, entry["sales_motion_key"], include_draft=True),
            ),
        }
        for entry in saved["types"]
    ]
    return {
        "source": source,
        "fallback": bool(result["fallback"]),
        # Why the model path failed ({kind, detail}), so the screen can say it instead of guessing.
        "error": result.get("error") if result["fallback"] else None,
        "reason": result["reason"],
        "candidates": public_candidates(candidates),
        "types": types,
        "company": _company_payload(saved["knowledge"] or existing, merged, filled),
    }


def _merge_company(repository: PlaybookRepository, company_id: str, found: Optional[dict]) -> tuple[Optional[dict], Optional[dict], list]:
    """What the document said about the company added to what is already stored, never overwriting it:
    (the stored row, the merged knowledge, the keys filled now). The write is part of the intake (one
    transaction with the call types). A failed read (the table is not there yet) means there is nothing to
    merge: the call types are still saved."""
    try:
        existing = repository.get_knowledge(company_id)
    except Exception:
        logger.exception("company knowledge not read")
        return None, None, []
    merged, filled = merge_knowledge((existing or {}).get("data") or {}, found)
    return existing, merged, filled


def _company_payload(row: Optional[dict], merged: Optional[dict], filled: list) -> Optional[dict]:
    """{knowledge, updated_at, sections, filled}, None when the document had nothing company-level and nothing
    is stored."""
    if merged is None or not sections(merged):
        return None
    return {
        "knowledge": merged,
        "updated_at": (row or {}).get("updated_at"),
        "sections": sections(merged),
        "filled": filled,
    }


@router.post("/{sales_motion_key}/structure")
async def structure_playbook_source(
    sales_motion_key: str,
    body: StructureRequest,
    membership: Membership = Depends(get_membership),
):
    """Turns pasted text, a PDF or an audio recording into steps and objection answers for
    this call type. Creates no version: the caller reviews the result and saves it as the
    draft. The material is kept as `source` so the playbook can link back to it. If the
    model fails the steps come from the line parser and `fallback` is true."""
    require_manager(membership)
    repository = get_playbook_repository()
    text = await _read_source(body)
    lang = detect_language(text)
    source = _keep_source(repository, membership, sales_motion_key, body, text, lang)
    result = await structure_source(text, sales_motion_key, lang)
    return {"sales_motion_key": sales_motion_key, **result, "source": source}
