"""What the call note Vocify writes in the CRM carries: the summary, the transcript, both or neither.

One company-wide choice (Settings > CRM), kept on each of the company's CRM connections
(crm_connections.metadata) so every sync reads it from the connection it already writes to.
Absent means both on: the note as it always was.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

SUMMARY_KEY = "note_includes_summary"
TRANSCRIPT_KEY = "note_includes_transcript"


@dataclass(frozen=True)
class NoteParts:
    summary: bool = True
    transcript: bool = True

    @property
    def any(self) -> bool:
        return self.summary or self.transcript


def note_parts(meta: Optional[dict]) -> NoteParts:
    meta = meta if isinstance(meta, dict) else {}
    return NoteParts(summary=meta.get(SUMMARY_KEY) is not False, transcript=meta.get(TRANSCRIPT_KEY) is not False)


def _parts_for_connection(supabase: Any, connection_id: str) -> NoteParts:
    row = supabase.table("crm_connections").select("metadata,company_id").eq("id", str(connection_id)).single().execute()
    data = (row.data or {}) if row else {}
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    if SUMMARY_KEY in meta or TRANSCRIPT_KEY in meta or not data.get("company_id"):
        return note_parts(meta)
    # A CRM connected after the choice was saved: the company's choice still holds.
    return company_note_parts(supabase, str(data["company_id"]))


async def load_note_parts(supabase: Any, connection_id: Any) -> NoteParts:
    """Never fails a sync: an unreadable setting is the default (both on)."""
    if not supabase or not connection_id:
        return NoteParts()
    try:
        return await asyncio.to_thread(_parts_for_connection, supabase, str(connection_id))
    except Exception:
        logger.warning("Could not read the note setting of connection %s", connection_id, exc_info=True)
        return NoteParts()


def company_note_parts(supabase: Any, company_id: str) -> NoteParts:
    """The company's choice: what its connections hold (the first one that has it set)."""
    rows = supabase.table("crm_connections").select("metadata").eq("company_id", company_id).execute().data or []
    for row in rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if SUMMARY_KEY in meta or TRANSCRIPT_KEY in meta:
            return note_parts(meta)
    return NoteParts()


def save_company_note_parts(supabase: Any, company_id: str, parts: NoteParts) -> NoteParts:
    rows = supabase.table("crm_connections").select("id,metadata").eq("company_id", company_id).execute().data or []
    for row in rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        supabase.table("crm_connections").update(
            {"metadata": {**meta, SUMMARY_KEY: parts.summary, TRANSCRIPT_KEY: parts.transcript}}
        ).eq("id", row["id"]).execute()
    return parts
