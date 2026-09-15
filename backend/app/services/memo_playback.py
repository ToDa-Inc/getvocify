"""Signed playback URL for call recordings stored in private `call-recordings`."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def playback_audio_url(
    memo_data: dict[str, Any],
    *,
    sign: Optional[Callable[[str], str]] = None,
) -> str:
    path = str(memo_data.get("recording_path") or "").strip()
    if path:
        if sign is None:
            return ""
        try:
            return (sign(path) or "").strip()
        except Exception:
            logger.warning("Could not sign recording_path %s", path, exc_info=True)
            return ""
    return memo_data.get("audio_url") or ""


def can_retranscribe(memo_data: dict[str, Any]) -> bool:
    if (memo_data.get("status") or "") == "approved":
        return False
    source = (memo_data.get("source") or memo_data.get("source_type") or "").strip()
    path = str(memo_data.get("recording_path") or "").strip()
    if source == "vocify_call":
        return bool(path)
    if source == "hubspot_call":
        return bool(path or str(memo_data.get("hubspot_engagement_id") or "").strip())
    return False


def recording_path_for_memo(memo_data: dict[str, Any], supabase: Any = None) -> str:
    path = str(memo_data.get("recording_path") or "").strip()
    if path:
        return path
    source = (memo_data.get("source") or memo_data.get("source_type") or "").strip()
    memo_id = memo_data.get("id")
    if source != "vocify_call" or not memo_id or supabase is None:
        return ""
    found = (
        supabase.table("outbound_calls")
        .select("recording_path")
        .eq("memo_id", str(memo_id))
        .limit(1)
        .execute()
    )
    row = (found.data or [None])[0] or {}
    return str(row.get("recording_path") or "").strip()


def sign_memo_audio(memo_data: dict[str, Any], supabase: Any) -> str:
    from app.config import settings
    from app.services.storage import StorageService

    path = recording_path_for_memo(memo_data, supabase)
    return playback_audio_url({**memo_data, "recording_path": path}, sign=lambda p: StorageService(supabase).signed_call_recording_url(
        p, settings.CALL_RECORDING_URL_TTL_SECONDS
    ))
