"""Idempotent capture identity. capture_id is the reserved memo id."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, status
from supabase import Client

INTERACTION_KINDS = frozenset({"call", "meeting", "visit", "voice_note"})
CAPTURE_STATUSES = (
    "recording",
    "upload_pending",
    "processing",
    "complete",
    "failed",
)
MEMO_PIPELINE_STATUSES = frozenset(
    {
        "uploading",
        "transcribing",
        "extracting",
        "pending_transcript",
        "pending_review",
        "approved",
        "rejected",
        "failed",
    }
)
CAPTURE_STATUS_TO_MEMO_STATUS = {
    "recording": "uploading",
    "upload_pending": "uploading",
    "processing": "extracting",
    "complete": "pending_review",
    "failed": "failed",
}


@dataclass
class CaptureIdentity:
    capture_id: str
    memo_id: str
    status: str
    should_start_pipeline: bool = False


class CaptureContentConflict(Exception):
    """Complete payload does not match the finalized input review."""

    def __init__(
        self,
        *,
        capture_id: str,
        memo_id: str,
        status: str,
        needs_new_review: bool = True,
    ):
        super().__init__("Capture content requires a new review")
        self.capture_id = capture_id
        self.memo_id = memo_id
        self.status = status
        self.needs_new_review = needs_new_review


def source_type_for_kind(interaction_kind: str) -> str:
    if interaction_kind == "meeting":
        return "meeting_transcript"
    return "voice_memo"


def _is_unique_violation(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "duplicate key" in text or "23505" in text


def _as_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.isoformat()
    return str(value)


def content_fingerprint(
    transcript: Optional[str],
    audio_duration: Optional[float],
    turns: Optional[list] = None,
) -> str:
    canonical = {
        "transcript": (transcript or "").strip(),
        "audio_duration": audio_duration,
        "turns": turns or [],
    }
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def insert_memo_row(supabase: Client, payload: dict[str, Any]) -> dict:
    """Shared memo insert. source_type is always persisted."""
    row = dict(payload)
    source_type = str(row.get("source_type") or "voice_memo").strip() or "voice_memo"
    row["source_type"] = source_type
    result = supabase.table("memos").insert(row).execute()
    data = result.data or []
    if not data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create memo",
        )
    return data[0]


def _identity_from_row(row: dict, *, should_start_pipeline: bool = False) -> CaptureIdentity:
    memo_id = str(row["id"])
    capture_status = row.get("capture_status") or "recording"
    return CaptureIdentity(
        capture_id=memo_id,
        memo_id=memo_id,
        status=str(capture_status),
        should_start_pipeline=should_start_pipeline,
    )


def _find_own_capture(
    supabase: Client,
    user_id: str,
    client_capture_id: str,
) -> Optional[dict]:
    result = (
        supabase.table("memos")
        .select("*")
        .eq("user_id", user_id)
        .eq("client_capture_id", client_capture_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _load_owned_capture(supabase: Client, user_id: str, capture_id: str) -> dict:
    result = (
        supabase.table("memos")
        .select("*")
        .eq("id", str(capture_id))
        .limit(1)
        .execute()
    )
    rows = result.data or []
    row = rows[0] if rows else None
    if not row or str(row.get("user_id")) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    return row


def reserve_capture(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    client_capture_id: str,
    started_at: Any,
    interaction_kind: str,
    sales_motion_key: Optional[str] = None,
    playbook_version_id: Optional[str] = None,
) -> CaptureIdentity:
    client_id = (client_capture_id or "").strip()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_capture_id is required",
        )
    kind = (interaction_kind or "").strip()
    if kind not in INTERACTION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid interaction_kind",
        )

    existing = _find_own_capture(supabase, user_id, client_id)
    if existing:
        return _identity_from_row(existing)

    payload = {
        "user_id": user_id,
        "company_id": company_id,
        "client_capture_id": client_id,
        "capture_started_at": _as_iso(started_at),
        "interaction_kind": kind,
        "sales_motion_key": sales_motion_key,
        "playbook_version_id": playbook_version_id,
        "capture_status": "recording",
        "capture_input_revision": 0,
        "status": CAPTURE_STATUS_TO_MEMO_STATUS["recording"],
        "source": "desktop",
        "source_type": source_type_for_kind(kind),
        "audio_url": "",
        "audio_duration": 0,
    }
    try:
        created = insert_memo_row(supabase, payload)
    except Exception as exc:
        if not _is_unique_violation(exc):
            raise
        created = _find_own_capture(supabase, user_id, client_id)
        if not created:
            raise
    return _identity_from_row(created)


def complete_capture(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    capture_id: str,
    transcript: Optional[str] = None,
    audio_duration: Optional[float] = None,
    turns: Optional[list] = None,
) -> CaptureIdentity:
    del company_id  # scope is the session author; company is already on the row
    row = _load_owned_capture(supabase, user_id, capture_id)
    fingerprint = content_fingerprint(transcript, audio_duration, turns)
    existing_fp = row.get("capture_content_fingerprint")
    if existing_fp:
        if existing_fp == fingerprint:
            return _identity_from_row(row, should_start_pipeline=False)
        raise CaptureContentConflict(
            capture_id=str(row["id"]),
            memo_id=str(row["id"]),
            status=str(row.get("capture_status") or "processing"),
            needs_new_review=True,
        )

    has_extraction = isinstance(row.get("extraction"), dict) and bool(row.get("extraction"))
    capture_status = "complete" if has_extraction else "processing"
    update = {
        "transcript": (transcript or "").strip() or None,
        "audio_duration": audio_duration,
        "capture_content_fingerprint": fingerprint,
        "capture_status": capture_status,
        "status": CAPTURE_STATUS_TO_MEMO_STATUS[capture_status],
    }
    (
        supabase.table("memos")
        .update(update)
        .eq("id", row["id"])
        .eq("user_id", user_id)
        .execute()
    )
    row.update(update)
    return _identity_from_row(row, should_start_pipeline=not has_extraction)
