"""Idempotent capture identity. capture_id is the reserved memo id."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, status
from supabase import Client

from app.services.playbooks.live import live_snapshots, live_version_id

logger = logging.getLogger(__name__)

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


MAX_AUDIO_BYTES = 512 * 1024 * 1024
AUDIO_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/pcm", "audio/l16"})


@dataclass
class CaptureIdentity:
    capture_id: str
    memo_id: str
    status: str
    should_start_pipeline: bool = False
    needs_batch_stt: bool = False
    audio_status: str = "partial"


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


_CALL_SOURCES = frozenset({"vocify_call", "hubspot_call"})


def interaction_kind_for(
    source: Optional[str],
    source_type: Optional[str],
    existing: Optional[str],
) -> str:
    """The capture channel. A valid stored value always wins; WhatsApp notes are post-visit notes."""
    kind = (existing or "").strip()
    if kind in INTERACTION_KINDS:
        return kind
    origin = (source or "").strip()
    if origin in _CALL_SOURCES:
        return "call"
    if origin == "whatsapp":
        return "visit"
    kind_hint = (source_type or "").strip()
    return "meeting" if kind_hint in ("meeting_transcript", "recall_bot") else "call"


def interaction_kind_of(memo: dict[str, Any]) -> str:
    """Rows from before interaction_kind was stamped are classified by origin."""
    return interaction_kind_for(memo.get("source"), memo.get("source_type"), memo.get("interaction_kind"))


def _is_unique_violation(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "duplicate key" in text or "23505" in text


def _is_memos_source_check_violation(exc: BaseException) -> bool:
    """True for a memos_source_check violation (23514): migration 061_memos_source_recall.sql
    (adding 'recall') has not run yet. Tolerant so the Recall bot capture (T14) still
    reserves - with source='web' until the migration lands - instead of a 500. Postgres'
    check-violation message doesn't echo the value, so this can't be narrower than the
    constraint name; reserve_capture only retries it for its own known source overrides."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        msg = (exc.message or str(exc)).lower()
        if code == "23514" and "memos_source_check" in msg:
            return True

    text = str(exc).lower()
    return "23514" in text and "memos_source_check" in text


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


def playbook_fields_for_capture(
    supabase: Client,
    company_id: str,
    *,
    sales_motion_key: Optional[str] = None,
    playbook_version_id: Optional[str] = None,
    resolved_version_id: Optional[str] = None,
    default_when_unspecified: bool = False,
    sales_role: Optional[str] = None,
    interaction_kind: Optional[str] = None,
    hubspot_contact_id: Optional[str] = None,
    hubspot_deal_id: Optional[str] = None,
) -> dict[str, Any]:
    """Pin the published playbook snapshot on a new memo row, same as desktop capture reserve.

    With PLAYBOOK_ROUTING_ENABLED the company's "when it applies" rules go before the role
    default, matched against what is cheaply known of the contact and deal (`hubspot_*_id`).
    The pin then also carries `pipeline_meta.playbook_pin` ({source, provisional?}) so a pin
    decided without a signal a rule needs (the deal, the contact) can be routed again once
    it is known (see playbooks.routing.repin_before_c04)."""
    from app.services.playbooks.versions import snapshot_for_capture

    motion = (sales_motion_key or "").strip() or None
    pinned_id = (playbook_version_id or "").strip() or None
    pin_source: Optional[str] = None
    pin_provisional = False
    if not motion and not pinned_id and interaction_kind:
        # D5: the rep's role picks the flow, but only behind the flag, and only when that
        # flow actually has something published. Otherwise the rule below (single published
        # playbook) still applies, unchanged.
        from app.services.feature_flags import is_enabled

        if is_enabled(supabase, company_id, "SALES_ROLES_ENABLED"):
            from app.services.playbooks.motion import motion_for

            candidate = motion_for(sales_role, interaction_kind)
            candidate_source = "role_default"
            provisional = False
            routing_on = is_enabled(supabase, company_id, "PLAYBOOK_ROUTING_ENABLED")
            if routing_on:
                # Never blocks the capture: a failed read is today's behaviour.
                try:
                    from app.services.playbooks.routing import resolve_motion

                    routed, why, provisional = resolve_motion(
                        supabase,
                        company_id,
                        sales_role=sales_role,
                        interaction_kind=interaction_kind,
                        contact_id=hubspot_contact_id,
                        deal_id=hubspot_deal_id,
                    )
                    if routed:
                        candidate, candidate_source = routed, why or "role_default"
                except Exception:
                    logger.warning("playbook routing failed, using the role default", exc_info=True)
            candidate_version = live_version_id(supabase, company_id, candidate)
            if not candidate_version and candidate_source == "rule":
                candidate = motion_for(sales_role, interaction_kind)
                candidate_source = "role_default"
                candidate_version = live_version_id(supabase, company_id, candidate)
            if candidate_version:
                motion = candidate
                resolved_version_id = candidate_version
                if routing_on:
                    pin_source = candidate_source
                    pin_provisional = provisional
    if not motion and not pinned_id:
        if not default_when_unspecified:
            return {}
        snapshots = live_snapshots(supabase, str(company_id))
        if len(snapshots) != 1:
            return {}
        snapshot = snapshots[0]
        return {
            "sales_motion_key": str(snapshot["sales_motion_key"]),
            "playbook_version_id": str(snapshot["version_id"]),
        }
    live = None if pinned_id else (resolved_version_id or live_version_id(supabase, company_id, motion))
    version = snapshot_for_capture(pinned_id, live)
    fields: dict[str, Any] = {}
    if motion:
        fields["sales_motion_key"] = motion
    if version:
        fields["playbook_version_id"] = str(version)
    if pin_source and motion:
        from app.services.playbooks.routing import merge_pin_meta

        fields["pipeline_meta"] = merge_pin_meta(None, pin_source, provisional=pin_provisional)
    return fields


def with_author_company(supabase: Client, row: dict[str, Any]) -> dict[str, Any]:
    """company_id is immutable once set, so it has to be stamped at insert. A failed lookup never blocks capture."""
    if row.get("company_id") or not row.get("user_id"):
        return row
    from app.services import company

    try:
        company_id = company.get_company_id_for_user(supabase, str(row["user_id"]))
    except Exception as exc:
        logger.warning("memo company lookup failed for %s: %s", row.get("user_id"), exc)
        return row
    return {**row, "company_id": company_id} if company_id else row


def pin_playbook_on_row(supabase: Client, row: dict[str, Any]) -> dict[str, Any]:
    """Pin the company's playbook on a new memo row the same way the dialer does
    (the rep's flow per D5, else the single published playbook). Without a pin a memo is
    never scored against the playbook: no adherence, no debrief, no Playbook tab entry.
    A row that already carries a pin keeps it; a failed lookup never blocks the capture."""
    if row.get("playbook_version_id") or row.get("sales_motion_key"):
        return row
    company_id = row.get("company_id")
    user_id = row.get("user_id")
    if not company_id or not user_id:
        return row
    try:
        from app.services.company import sales_role_for_user

        fields = playbook_fields_for_capture(
            supabase,
            str(company_id),
            default_when_unspecified=True,
            sales_role=sales_role_for_user(supabase, str(user_id)),
            interaction_kind=interaction_kind_of(row),
            hubspot_contact_id=row.get("hubspot_contact_id"),
            hubspot_deal_id=row.get("hubspot_deal_id") or row.get("matched_deal_id"),
        )
    except Exception:
        logger.warning("playbook pin failed for a new memo", exc_info=True)
        return row
    if "pipeline_meta" in fields and isinstance(row.get("pipeline_meta"), dict):
        fields = {**fields, "pipeline_meta": {**row["pipeline_meta"], **fields["pipeline_meta"]}}
    return {**row, **fields}


def insert_memo_row(supabase: Client, payload: dict[str, Any], *, pin_playbook: bool = False) -> dict:
    """Shared memo insert. source_type is always persisted. pin_playbook stamps the
    company's playbook like every other capture path (uploads, extension recordings)."""
    row = with_author_company(supabase, dict(payload))
    source_type = str(row.get("source_type") or "voice_memo").strip() or "voice_memo"
    row["source_type"] = source_type
    row["interaction_kind"] = interaction_kind_of(row)
    if pin_playbook:
        row = pin_playbook_on_row(supabase, row)
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
    resolved_version_id: Optional[str] = None,
    sales_role: Optional[str] = None,
    source: str = "desktop",
    source_type: Optional[str] = None,
    hubspot_contact_id: Optional[str] = None,
) -> CaptureIdentity:
    """`source`/`source_type` default to the desktop capture values (unchanged for every
    existing caller); T14's Recall bot is the first caller to override them
    (source="recall", source_type="recall_bot") so a bot-completed meeting is
    distinguishable from a desktop recording of one."""
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

    playbook = playbook_fields_for_capture(
        supabase,
        company_id,
        sales_motion_key=sales_motion_key,
        playbook_version_id=playbook_version_id,
        resolved_version_id=resolved_version_id,
        sales_role=sales_role,
        interaction_kind=kind,
        hubspot_contact_id=hubspot_contact_id,
    )
    payload = {
        "user_id": user_id,
        "company_id": company_id,
        "client_capture_id": client_id,
        "capture_started_at": _as_iso(started_at),
        "interaction_kind": kind,
        **playbook,
        "capture_status": "recording",
        "capture_input_revision": 0,
        "status": CAPTURE_STATUS_TO_MEMO_STATUS["recording"],
        "source": source,
        "source_type": source_type or source_type_for_kind(kind),
        "audio_url": "",
        "audio_duration": 0,
    }
    if hubspot_contact_id:
        payload["hubspot_contact_id"] = hubspot_contact_id
    try:
        created = insert_memo_row(supabase, payload)
    except Exception as exc:
        if _is_memos_source_check_violation(exc) and payload["source"] != "web":
            # Migration 061 hasn't run yet: this source value isn't in the DB's
            # check constraint. Never invented silently for an unknown value - only
            # for the one override reserve_capture itself set (source="recall").
            payload["source"] = "web"
            created = insert_memo_row(supabase, payload)
        elif not _is_unique_violation(exc):
            raise
        else:
            created = _find_own_capture(supabase, user_id, client_id)
            if not created:
                raise
    return _identity_from_row(created)


def _audio_extension(content_type: str) -> str:
    if content_type in {"audio/pcm", "audio/l16"}:
        return "pcm"
    return "wav"


def store_capture_audio(
    supabase: Client,
    *,
    user_id: str,
    capture_id: str,
    audio: bytes,
    content_type: str,
    byte_length: Optional[int] = None,
) -> CaptureIdentity:
    """Store capture audio in the private call-recordings bucket. Never a public URL."""
    from app.services.storage import CALL_RECORDINGS_BUCKET

    row = _load_owned_capture(supabase, user_id, capture_id)
    size = byte_length if byte_length is not None else len(audio)
    if size > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="El audio supera 512 MiB")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(status_code=422, detail="Formato de audio no admitido")
    if mime in {"audio/wav", "audio/x-wav", "audio/wave"} and not audio.startswith(b"RIFF"):
        raise HTTPException(status_code=422, detail="WAV incompleto")

    path = f"{user_id}/{row['id']}.{_audio_extension(mime)}"
    try:
        supabase.storage.from_(CALL_RECORDINGS_BUCKET).upload(
            path=path,
            file=audio,
            file_options={"content-type": mime, "upsert": "true"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="No se pudo guardar el audio") from exc

    update = {
        "recording_path": path,
        "audio_status": "partial",
        "capture_status": "upload_pending",
        "status": CAPTURE_STATUS_TO_MEMO_STATUS["upload_pending"],
    }
    (
        supabase.table("memos")
        .update(update)
        .eq("id", row["id"])
        .eq("user_id", user_id)
        .execute()
    )
    row.update(update)
    identity = _identity_from_row(row)
    identity.audio_status = "partial"
    return identity


def complete_capture(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    capture_id: str,
    transcript: Optional[str] = None,
    audio_duration: Optional[float] = None,
    turns: Optional[list] = None,
    transcript_complete: bool = True,
    audio_status: Optional[str] = None,
) -> CaptureIdentity:
    del company_id  # scope is the session author; company is already on the row
    row = _load_owned_capture(supabase, user_id, capture_id)
    if not transcript_complete:
        update = {
            "transcript": (transcript or "").strip() or None,
            "audio_duration": audio_duration,
            "capture_turns": turns or [],
            "transcript_complete": False,
            "audio_status": audio_status or row.get("audio_status") or "partial",
            "capture_status": "processing",
            "status": CAPTURE_STATUS_TO_MEMO_STATUS["processing"],
        }
        (
            supabase.table("memos")
            .update(update)
            .eq("id", row["id"])
            .eq("user_id", user_id)
            .execute()
        )
        row.update(update)
        identity = _identity_from_row(row, should_start_pipeline=False)
        identity.needs_batch_stt = (update["audio_status"] == "complete")
        identity.audio_status = str(update["audio_status"])
        return identity

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
        "capture_turns": turns or [],
        "transcript_complete": True,
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
