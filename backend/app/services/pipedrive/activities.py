"""Next-step activities via v2 Activities + v1 activityTypes discovery."""

from __future__ import annotations

from typing import Any, Optional

from .client import PipedriveClient, unwrap_data


class PipedriveActivityService:
    def __init__(self, client: PipedriveClient) -> None:
        self.client = client
        self._task_type: Optional[str] = None
        self._looked_up = False

    async def resolve_task_type(self) -> Optional[str]:
        if self._looked_up:
            return self._task_type
        self._looked_up = True
        raw = unwrap_data(await self.client.get("/activityTypes", version="v1"))
        rows = raw if isinstance(raw, list) else []
        task_key = None
        icon_key = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = row.get("key_string")
            if key == "task":
                task_key = key
                break
            if row.get("icon_key") == "task" and not icon_key:
                icon_key = key
        self._task_type = task_key or icon_key
        return self._task_type

    async def create_next_step(
        self,
        subject: str,
        *,
        note: Optional[str] = None,
        deal_id: Optional[str] = None,
        person_id: Optional[str] = None,
        org_id: Optional[str] = None,
        due_date: Optional[str] = None,
        due_time: Optional[str] = None,
    ) -> Optional[str]:
        """due_date and due_time are UTC, as Pipedrive expects."""
        activity_type = await self.resolve_task_type()
        if not activity_type:
            return None
        body: dict[str, Any] = {
            "subject": subject[:255],
            "type": activity_type,
        }
        if note:
            body["note"] = note
        if deal_id:
            body["deal_id"] = int(deal_id)
        if person_id:
            body["person_id"] = int(person_id)
        if org_id:
            body["org_id"] = int(org_id)
        if due_date:
            body["due_date"] = due_date
        if due_time:
            body["due_time"] = due_time
        created = unwrap_data(await self.client.post("/activities", json_body=body))
        if isinstance(created, dict) and created.get("id") is not None:
            return str(created["id"])
        return None
