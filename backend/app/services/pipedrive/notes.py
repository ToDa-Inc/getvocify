"""Pipedrive Notes (v1). HTML content; one note can attach deal + person + org."""

from __future__ import annotations

from typing import Any, Optional

from app.services.hubspot.note_format import format_hubspot_note_body

from .client import PipedriveClient, unwrap_data


def format_note_content(
    *,
    summary: Optional[str],
    transcript: str,
    field_changes: Optional[list[dict[str, Any]]] = None,
) -> str:
    return format_hubspot_note_body(
        summary=summary,
        transcript=transcript,
        source=None,
        field_changes=field_changes,
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
        created = unwrap_data(await self.client.post("/notes", json_body=body, version="v1"))
        if isinstance(created, dict) and created.get("id") is not None:
            return str(created["id"])
        return None
