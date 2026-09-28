"""Human notes. The author is the session, and the same annotation id stays one note."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.intelligence.annotations import AnnotationError, SupabaseAnnotationStore, accept_annotation
from app.services.intelligence.patterns import objection_view

router = APIRouter(prefix="/api/v1", tags=["annotations"])
_NOTES: dict = {}
_STORE = None


def set_annotation_store(store) -> None:
    global _STORE
    _STORE = store


class NoteBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    offset_ms: int = Field(ge=0)
    expected_revision: Optional[int] = None
    client_capture_id: Optional[str] = None


def _public(note: dict) -> dict:
    return {
        "annotation_id": note["annotation_id"],
        "client_capture_id": note.get("client_capture_id"),
        "memo_id": note.get("memo_id"),
        "text": note["text"],
        "offset_ms": note["offset_ms"],
        "revision": note["revision"],
        "author_id": note["author_id"],
        "source_type": note["source_type"],
    }


@router.put("/captures/{client_capture_id}/annotations/{annotation_id}")
async def put_capture_note(
    client_capture_id: str,
    annotation_id: str,
    body: NoteBody,
    membership: Membership = Depends(get_membership),
):
    return _save(annotation_id, body, membership, client_capture_id=client_capture_id, memo_id=None)


@router.put("/memos/{memo_id}/annotations/{annotation_id}")
async def put_memo_note(
    memo_id: str,
    annotation_id: str,
    body: NoteBody,
    membership: Membership = Depends(get_membership),
):
    return _save(annotation_id, body, membership, client_capture_id=body.client_capture_id, memo_id=memo_id)


def _save(annotation_id: str, body: NoteBody, membership: Membership, *, client_capture_id: str | None, memo_id: str | None):
    try:
        if _STORE is not None:
            note = _STORE.save(
                annotation_id=annotation_id,
                client_capture_id=client_capture_id,
                text=body.text,
                offset_ms=body.offset_ms,
                expected_revision=body.expected_revision,
                author_id=membership.user_id,
                company_id=membership.company_id,
                memo_id=memo_id,
            )
        else:
            note = accept_annotation(
                _NOTES,
                annotation_id=annotation_id,
                client_capture_id=client_capture_id,
                text=body.text,
                offset_ms=body.offset_ms,
                expected_revision=body.expected_revision,
                author_id=membership.user_id,
                company_id=membership.company_id,
                memo_id=memo_id,
            )
    except AnnotationError as error:
        if error.code == "conflict":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_public(error.note)) from error
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nota no válida") from error
    return _public(note)


@router.get("/memos/{memo_id}/objections")
async def get_objections(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    try:
        notes = (
            supabase.table("interaction_annotations")
            .select("annotation_id,text,offset_ms,author_id,turn_id,memo_id,company_id")
            .eq("company_id", membership.company_id)
            .eq("memo_id", memo_id)
            .execute()
        )
        patterns = (
            supabase.table("interaction_patterns")
            .select("pattern_id,category,kind,resolution,response,prospect_quotes,superseded,memo_id")
            .eq("memo_id", memo_id)
            .execute()
        )
    except Exception:
        return objection_view(notes=[], patterns=[], readable=False)
    return objection_view(notes=notes.data or [], patterns=patterns.data or [], readable=True)
