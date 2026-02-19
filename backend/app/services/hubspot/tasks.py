"""
Task operations service for HubSpot.

Creates tasks from MemoExtraction nextSteps and associates them with deals.
Uses /crm/v3/objects/tasks API.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from .client import HubSpotClient
from .exceptions import HubSpotError
from app.models.memo import MemoExtraction


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
