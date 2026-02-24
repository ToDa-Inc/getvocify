"""
Task operations service for HubSpot.

Creates tasks from MemoExtraction nextSteps and associates them with deals.
Supports listing, updating, and deleting tasks for deal merge flows.
Uses /crm/v3/objects/tasks API.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from .client import HubSpotClient
from .exceptions import HubSpotError
from app.models.memo import MemoExtraction

logger = logging.getLogger(__name__)


# Patterns that are too generic - don't create tasks for these
SKIP_TASK_PATTERNS = [
    r"\bcerrar\s+(el\s+)?(trato|deal|negocio)\b",
    r"\bclose\s+(the\s+)?(deal|trato)\b",
    r"\bcerrar\s+el\s+acuerdo\b",
    r"\bcerrar\s+la\s+venta\b",
    r"\bclose\s+the\s+sale\b",
    r"\bfinalizar\s+(el\s+)?(trato|deal)\b",
    r"\bclose\s+the\s+deal\b",
    r"\bcerrar\s+contrato\b",
]


def _should_skip_next_step(text: str) -> bool:
    """Return True if this next step is too generic to create a task."""
    if not text or len(text.strip()) < 5:
        return True
    lower = text.strip().lower()
    for pattern in SKIP_TASK_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return True
    return False


def _parse_date_from_text(text: str) -> Optional[datetime]:
    """
    Parse a date from Spanish/English phrases like:
    - "el martes", "el próximo martes"
    - "mañana"
    - "la próxima semana"
    - "next Tuesday"
    """
    if not text:
        return None
    lower = text.strip().lower()
    now = datetime.utcnow()

    # Spanish weekdays
    dias = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    }
    # English
    dias.update({
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    })

    # "mañana" / "tomorrow"
    if "mañana" in lower or "manana" in lower or "tomorrow" in lower:
        return now + timedelta(days=1)

    # "el martes", "next tuesday", "el próximo martes"
    for day_name, day_num in dias.items():
        if day_name in lower:
            # Find next occurrence of this weekday
            days_ahead = (day_num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week
            if "próxim" in lower or "proxim" in lower or "next" in lower or "siguiente" in lower:
                pass  # Already getting next occurrence
            return now + timedelta(days=days_ahead)

    # "la próxima semana" / "next week"
    if "próxima semana" in lower or "proxima semana" in lower or "next week" in lower:
        return now + timedelta(days=7)

    # Default: 3 days from now
    return now + timedelta(days=3)


class HubSpotTasksService:
    """
    Service for creating HubSpot tasks from voice memo next steps.
    """

    OBJECT_TYPE = "tasks"
    # Task-to-deal association type (HubSpot default: 216 = Task to deal)
    TASK_TO_DEAL_ASSOCIATION_TYPE = "216"

    def __init__(self, client: HubSpotClient):
        self.client = client

    def _to_timestamp_ms(self, dt: datetime) -> str:
        """Convert datetime to HubSpot timestamp (milliseconds)."""
        return str(int(dt.timestamp() * 1000))

    async def create_task(
        self,
        subject: str,
        due_date: datetime,
        deal_id: Optional[str] = None,
        body: Optional[str] = None,
        priority: str = "MEDIUM",
        task_type: str = "TODO",
        hubspot_owner_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a task in HubSpot and optionally associate with a deal.

        Args:
            subject: Task title (hs_task_subject)
            due_date: Due date for hs_timestamp
            deal_id: Optional deal ID to associate
            body: Optional task notes (hs_task_body)
            priority: LOW, MEDIUM, HIGH
            task_type: EMAIL, CALL, TODO

        Returns:
            Task ID if created, None on error
        """
        properties = {
            "hs_timestamp": self._to_timestamp_ms(due_date),
            "hs_task_subject": subject[:255] if subject else "Follow-up",
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": priority,
            "hs_task_type": task_type,
        }
        if hubspot_owner_id:
            properties["hubspot_owner_id"] = str(hubspot_owner_id)
        if body:
            properties["hs_task_body"] = body[:65535]

        payload: dict = {"properties": properties}
        if deal_id:
            payload["associations"] = [
                {
                    "to": {"id": deal_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": int(self.TASK_TO_DEAL_ASSOCIATION_TYPE),
                        }
                    ],
                }
            ]

        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.OBJECT_TYPE}",
                data=payload,
            )
            if response and "id" in response:
                return str(response["id"])
            return None
        except HubSpotError:
            return None

    async def create_tasks_from_extraction(
        self,
        extraction: MemoExtraction,
        deal_id: Optional[str] = None,
        hubspot_owner_id: Optional[str] = None,
    ) -> list[str]:
        """
        Create HubSpot tasks from extraction nextSteps.
        Skips generic items like "Cerrar el trato".

        Returns:
            List of created task IDs
        """
        created: list[str] = []
        next_steps = extraction.nextSteps or []

        for step in next_steps:
            if not step or not isinstance(step, str):
                continue
            step = step.strip()
            if _should_skip_next_step(step):
                continue

            due_date = _parse_date_from_text(step) or datetime.utcnow() + timedelta(days=3)
            task_id = await self.create_task(
                subject=step[:255],
                due_date=due_date,
                deal_id=deal_id,
                body=extraction.summary or "",
                hubspot_owner_id=hubspot_owner_id,
            )
            if task_id:
                created.append(task_id)

        return created

    async def list_tasks_for_deal(
        self,
        deal_id: str,
        properties: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        List tasks associated with a deal.
        Returns list of {id, subject, due_date} for each task.

        Args:
            deal_id: HubSpot deal ID
            properties: Optional list of properties to fetch (default: hs_task_subject, hs_timestamp)

        Returns:
            List of task dicts with id, subject, due_date (datetime or None)
        """
        props = properties or ["hs_task_subject", "hs_timestamp"]
        try:
            # Get task IDs associated with deal (v4 associations)
            resp = await self.client.get(
                f"/crm/v4/objects/deals/{deal_id}/associations/tasks"
            )
            if not resp or "results" not in resp:
                return []

            task_ids = []
            for r in resp.get("results", []):
                for to_item in r.get("to", []):
                    oid = to_item.get("toObjectId")
                    if oid is not None:
                        task_ids.append(str(oid))
                # Fallback: objectId
                oid = r.get("objectId") or r.get("id")
                if oid is not None and str(oid) not in task_ids:
                    task_ids.append(str(oid))

            if not task_ids:
                return []

            # Batch read task details
            batch_body = {
                "inputs": [{"id": tid} for tid in task_ids],
                "properties": props,
            }
            batch_resp = await self.client.post(
                "/crm/v3/objects/tasks/batch/read",
                data=batch_body,
            )
            if not batch_resp or "results" not in batch_resp:
                return []

            tasks = []
            for t in batch_resp.get("results", []):
                tid = t.get("id")
                if not tid:
                    continue
                props_map = t.get("properties", {}) or {}
                subject = props_map.get("hs_task_subject", "")
                ts_ms = props_map.get("hs_timestamp")
                due_date = None
                if ts_ms:
                    try:
                        due_date = datetime.utcfromtimestamp(int(ts_ms) / 1000)
                    except (ValueError, TypeError):
                        pass
                tasks.append({
                    "id": str(tid),
                    "subject": subject or "",
                    "due_date": due_date,
                })
            return tasks
        except HubSpotError as e:
            logger.warning("Failed to list tasks for deal %s: %s", deal_id, e)
            return []

    async def update_task(
        self,
        task_id: str,
        subject: Optional[str] = None,
        due_date: Optional[datetime] = None,
        hubspot_owner_id: Optional[str] = None,
    ) -> bool:
        """
        Update an existing task.

        Args:
            task_id: HubSpot task ID
            subject: New subject (hs_task_subject)
            due_date: New due date (hs_timestamp)
            hubspot_owner_id: Optional owner ID

        Returns:
            True if updated successfully
        """
        properties = {}
        if subject is not None:
            properties["hs_task_subject"] = subject[:255] if subject else ""
        if due_date is not None:
            properties["hs_timestamp"] = self._to_timestamp_ms(due_date)
        if hubspot_owner_id is not None:
            properties["hubspot_owner_id"] = str(hubspot_owner_id)
        if not properties:
            return True
        try:
            await self.client.patch(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{task_id}",
                data={"properties": properties},
            )
            return True
        except HubSpotError:
            return False

    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task (moved to recycling bin in HubSpot).

        Returns:
            True if deleted successfully
        """
        try:
            await self.client.delete(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{task_id}"
            )
            return True
        except HubSpotError:
            return False
