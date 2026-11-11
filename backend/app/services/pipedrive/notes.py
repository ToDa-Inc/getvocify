"""Pipedrive Notes (v1). HTML content; one note can attach deal + person + org."""

from __future__ import annotations

from typing import Any, Optional

from app.services.hubspot.note_format import format_hubspot_note_body

import logging

from .client import PipedriveClient, unwrap_data
from .exceptions import PipedriveAuthError, PipedriveError

logger = logging.getLogger(__name__)


def format_note_content(
    *,
    summary: Optional[str],
    transcript: str,
    field_changes: Optional[list[dict[str, Any]]] = None,
    include_summary: bool = True,
) -> str:
    return format_hubspot_note_body(
        summary=summary,
        transcript=transcript,
        source=None,
        field_changes=field_changes,
        include_summary=include_summary,
    )


class PipedriveNoteService:
    def __init__(self, client: PipedriveClient) -> None:
        self.client = client

    async def create(
        self,
        content: str,
        *,
        deal_id: Optional[str] = None,
        person_id: Optional[str] = None,
        org_id: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> Optional[str]:
        body: dict[str, Any] = {"content": content}
        if deal_id:
            body["deal_id"] = int(deal_id)
        if person_id:
            body["person_id"] = int(person_id)
        if org_id:
            body["org_id"] = int(org_id)
        if len(body) == 1:
            return None
        created = None
        if author_id:
            # The member who recorded it is the note's author, not whoever connected Pipedrive. Pipedrive lets only an
            # admin connection set another author: refused, the note is written without it, as before.
            try:
                created = unwrap_data(await self.client.post("/notes", json_body={**body, "user_id": int(author_id)}, version="v1"))
            except PipedriveAuthError:
                raise
            except PipedriveError as e:
                logger.info("Pipedrive note: author %s refused (%s), written as the connected user", author_id, e.status_code)
        if created is None:
            created = unwrap_data(await self.client.post("/notes", json_body=body, version="v1"))
        if isinstance(created, dict) and created.get("id") is not None:
            return str(created["id"])
        return None
