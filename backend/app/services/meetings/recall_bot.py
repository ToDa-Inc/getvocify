"""T14: Recall.ai meeting bot. Reserves the capture the bot's recording will complete,
and finishes it through the exact same path a desktop capture completes with a
transcript/turns (`app.services.captures.complete_capture`) - no second completion
path invented for a bot-recorded meeting.

`client_capture_id="recall:{bot_id}"` is how the webhook (no user session, only a
signature) finds the memo a `bot.done` event belongs to: bot ids are Recall's own,
globally unique identifiers, so a plain lookup by that column is enough - no new
migration/column needed for this task.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from supabase import Client

from app.services.captures import CaptureIdentity, complete_capture, reserve_capture

logger = logging.getLogger(__name__)


def client_capture_id_for_bot(bot_id: str) -> str:
    return f"recall:{bot_id}"


def reserve_recall_capture(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    started_at: Any,
    bot_id: str,
    sales_role: Optional[str] = None,
    contact_id: Optional[str] = None,
) -> CaptureIdentity:
    return reserve_capture(
        supabase,
        user_id=user_id,
        company_id=company_id,
        client_capture_id=client_capture_id_for_bot(bot_id),
        started_at=started_at,
        interaction_kind="meeting",
        sales_role=sales_role,
        source="recall",
        source_type="recall_bot",
        hubspot_contact_id=contact_id,
    )


def find_capture_by_bot_id(supabase: Client, bot_id: str) -> Optional[dict]:
    rows = (
        supabase.table("memos")
        .select("*")
        .eq("client_capture_id", client_capture_id_for_bot(bot_id))
        .eq("source_type", "recall_bot")
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def rep_full_name(supabase: Client, user_id: str) -> Optional[str]:
    """Best-effort, for the transcript's rep/prospect split (recall_client.
    turns_from_recall_transcript). Never raises - a lookup failure just means every
    turn stays `unknown` instead of blocking the capture."""
    try:
        rows = (
            supabase.table("user_profiles")
            .select("full_name")
            .eq("id", user_id)
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning("Recall bot: rep name lookup failed for %s: %s", user_id, exc)
        return None
    name = (rows[0].get("full_name") if rows else None) or None
    return str(name).strip() or None if name else None


def complete_recall_capture(
    supabase: Client,
    memo_row: dict[str, Any],
    *,
    transcript: str,
    turns: list[dict[str, Any]],
) -> CaptureIdentity:
    return complete_capture(
        supabase,
        user_id=memo_row["user_id"],
        company_id=memo_row.get("company_id"),
        capture_id=memo_row["id"],
        transcript=transcript,
        audio_duration=None,
        turns=turns,
        transcript_complete=True,
    )
