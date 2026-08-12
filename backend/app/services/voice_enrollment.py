"""Per-user Speechmatics voice enrollment for Call Copilot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

REP_LABEL = "Salesperson"
CONSENT_VERSION = "voice-enrollment-v1"


class VoiceEnrollmentService:
    def __init__(self, supabase: Client) -> None:
        self.supabase = supabase

    def get_status(self, user_id: str) -> dict[str, Any]:
        row = self._fetch(user_id)
        if not row:
            return {
                "enrolled": False,
                "rep_label": REP_LABEL,
                "sample_count": 0,
                "consented_at": None,
                "consent_version": None,
            }
        return {
            "enrolled": True,
            "rep_label": row.get("rep_label") or REP_LABEL,
            "sample_count": int(row.get("sample_count") or 1),
            "consented_at": row.get("consented_at"),
            "consent_version": row.get("consent_version"),
        }

    def get_identifiers_for_stt(self, user_id: str) -> Optional[dict[str, Any]]:
        """Return Speechmatics speakers config fragment, or None."""
        row = self._fetch(user_id)
        if not row:
            return None
        identifiers = row.get("speaker_identifiers") or []
        if not isinstance(identifiers, list) or not identifiers:
            return None
        cleaned = [str(x) for x in identifiers if x]
        if not cleaned:
            return None
        return {
            "label": row.get("rep_label") or REP_LABEL,
            "speaker_identifiers": cleaned,
        }

    def upsert_enrollment(
        self,
        user_id: str,
        speaker_identifiers: list[str],
        *,
        consent: bool,
        sample_count: int = 1,
        rep_label: str = REP_LABEL,
    ) -> dict[str, Any]:
        if not consent:
            raise ValueError("Explicit consent is required to enroll your voice")
        cleaned = [str(x).strip() for x in speaker_identifiers if str(x).strip()]
        if not cleaned:
            raise ValueError("No speaker identifiers received from enrollment")
        if len(cleaned) > 50:
            raise ValueError("Too many speaker identifiers (max 50)")

        label = (rep_label or REP_LABEL).strip() or REP_LABEL
        if label in {"S1", "S2", "UU"} or label.startswith("S") and label[1:].isdigit():
            raise ValueError("Reserved speaker label")

        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "user_id": user_id,
            "rep_label": label,
            "speaker_identifiers": cleaned,
            "sample_count": max(1, int(sample_count)),
            "consent_version": CONSENT_VERSION,
            "consented_at": now,
            "updated_at": now,
        }
        self.supabase.table("user_voice_enrollments").upsert(
            payload, on_conflict="user_id"
        ).execute()
        return self.get_status(user_id)

    def delete_enrollment(self, user_id: str) -> None:
        self.supabase.table("user_voice_enrollments").delete().eq(
            "user_id", user_id
        ).execute()

    def _fetch(self, user_id: str) -> Optional[dict[str, Any]]:
        try:
            resp = (
                self.supabase.table("user_voice_enrollments")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            return rows[0] if rows else None
        except Exception:
            logger.exception("Failed to load voice enrollment for %s", user_id)
            return None
