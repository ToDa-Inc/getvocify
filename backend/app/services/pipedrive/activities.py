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
        owner_id: Optional[str] = None,
        due_date: Optional[str] = None,
        due_time: Optional[str] = None,
    ) -> Optional[str]:
        """due_date and due_time are UTC, as Pipedrive expects. owner_id (Lista 3): the
        Vocify user's own Pipedrive user id, resolved from their login email
        (sync._get_pipedrive_owner_id_for_user) - activities are always newly created
        here, so it is always safe to stamp."""
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
            # v2 activities: person_id is read-only, the person goes in as the primary participant.
            body["participants"] = [{"person_id": int(person_id), "primary": True}]
        if org_id:
            body["org_id"] = int(org_id)
        if owner_id:
            body["owner_id"] = int(owner_id)
        if due_date:
            body["due_date"] = due_date
        if due_time:
            body["due_time"] = due_time
        created = unwrap_data(await self.client.post("/activities", json_body=body))
        if isinstance(created, dict) and created.get("id") is not None:
            return str(created["id"])
        return None


async def activity_type_for(client: PipedriveClient, kind: str) -> Optional[str]:
    """The account's own activity type for a call or a meeting (key "call"/"meeting", else one with that icon)."""
    rows = unwrap_data(await client.get("/activityTypes", version="v1"))
    by_icon: Optional[str] = None
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("is_deleted") or row.get("active_flag") is False:
            continue
        if row.get("key_string") == kind:
            return kind
        if row.get("icon_key") == kind and not by_icon:
            by_icon = row.get("key_string")
    return by_icon


async def log_conversation(
    client: PipedriveClient,
    *,
    kind: str,
    subject: str,
    note_html: str,
    deal_id: Optional[str] = None,
    person_id: Optional[str] = None,
    org_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    duration: Optional[str] = None,
    existing_activity_id: Optional[str] = None,
) -> Optional[str]:
    """The call or meeting as a done activity whose note is the call's summary. A call Vocify dialed already has its
    activity (call_log.py): that one gets the summary instead of a second activity."""
    if existing_activity_id:
        await client.patch(f"/activities/{existing_activity_id}", json_body={"note": note_html})
        return str(existing_activity_id)
    activity_type = await activity_type_for(client, kind)
    if not activity_type:
        return None
    body: dict[str, Any] = {"subject": subject[:255], "type": activity_type, "done": True, "note": note_html}
    if deal_id:
        body["deal_id"] = int(deal_id)
    if person_id:
        # v2 activities: person_id is read-only, the person goes in as the primary participant.
        body["participants"] = [{"person_id": int(person_id), "primary": True}]
    if org_id:
        body["org_id"] = int(org_id)
    if owner_id:
        body["owner_id"] = int(owner_id)
    if due_date:
        body["due_date"] = due_date
    if due_time:
        body["due_time"] = due_time
    if duration:
        body["duration"] = duration
    try:
        created = unwrap_data(await client.post("/activities", json_body=body))
    except Exception:
        if "duration" not in body:
            raise
        body.pop("duration")
        created = unwrap_data(await client.post("/activities", json_body=body))
    return str(created["id"]) if isinstance(created, dict) and created.get("id") is not None else None
