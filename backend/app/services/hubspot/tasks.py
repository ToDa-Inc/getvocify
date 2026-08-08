"""
Task operations service for HubSpot.

Creates tasks from MemoExtraction nextSteps and associates them with deals.
Supports listing, updating, and deleting tasks for deal merge flows.
Uses /crm/v3/objects/tasks API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .client import HubSpotClient
from .exceptions import HubSpotError
from app.models.memo import MemoExtraction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormattedTask:
    subject: str
    due_date: datetime
    task_type: str = "TODO"


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


_SCHEDULE_PATTERNS = [
    r"\bel\s+(?:pr[oó]ximo\s+|proximo\s+)?(?:lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[aá]bado|sabado|domingo)\b",
    r"\b(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[aá]bado|sabado|domingo)\s+que\s+viene\b",
    r"\b(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+next\s+week)?\b",
    r"\bma[nñ]ana\b|\btomorrow\b",
    r"\b(?:la\s+)?(?:pr[oó]xima|proxima)\s+semana\b|\bnext\s+week\b|\bsemana\s+que\s+viene\b",
    r"\ba\s+las\s+\d{1,2}(?::\d{2})?\s*(?:h|hrs?|horas?)?\b",
    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|h|hrs?)?\b",
    r"\bel\s+d[ií]a\s+\d{1,2}\b",
    r"\b(?:en|within)\s+\d+\s+d[ií]as?\b",
    r"\bque\s+viene\b|\bsiguiente\b",
]


def _strip_scheduling_phrases(text: str) -> str:
    cleaned = text or ""
    for pattern in _SCHEDULE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bcon\s+(?:[eé]l|ella|him|her|them)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned


def _apply_time_from_text(text: str, base: datetime) -> datetime:
    match = re.search(
        r"(?:a las|at)\s+(\d{1,2})(?::(\d{2}))?\s*(h|hrs?|horas?|am|pm)?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return base
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = (match.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _infer_task_title(cleaned: str, original: str, contact_name: Optional[str]) -> str:
    source = cleaned or original
    lower = source.lower()

    topic_match = re.search(r"(?:por|sobre|about|re:|re\.)\s+(.+)", lower)
    if topic_match:
        topic = topic_match.group(1).strip(" .")[:60]
        if topic and re.search(r"\b(llamar|call|hablar|phone|telefonear)\b", lower):
            return f"Llamar por {topic[0].upper()}{topic[1:]}" if len(topic) <= 40 else f"Llamada: {topic[:40]}"

    action_match = re.search(
        r"\b(enviar|mandar|send|revisar|review|preparar|prepare|agendar|schedule|confirmar|confirm)\b[^,.]*",
        source,
        re.IGNORECASE,
    )
    if action_match:
        title = action_match.group(0).strip()
        return title[0].upper() + title[1:]

    if re.search(r"\b(hablar|llamar|llamada|call|phone|telefonear|ring)\b", lower):
        if contact_name:
            first = contact_name.strip().split()[0]
            return f"Llamada con {first}"
        return "Llamada de seguimiento"

    if re.search(r"\bdemo\b", lower):
        return "Demo con el cliente" if contact_name else "Demo"
    if re.search(r"\b(reuni[oó]n|meeting|presentaci[oó]n)\b", lower):
        return "Reunión de seguimiento"

    if cleaned and len(cleaned) <= 60:
        return cleaned[0].upper() + cleaned[1:]

    return "Seguimiento"


def _infer_task_type(text: str) -> str:
    lower = (text or "").lower()
    if re.search(r"\b(enviar|email|mail|correo|send)\b", lower):
        return "EMAIL"
    if re.search(r"\b(hablar|llamar|llamada|call|phone|telefonear|ring)\b", lower):
        return "CALL"
    return "TODO"


def format_next_step_task(
    step: str,
    *,
    contact_name: Optional[str] = None,
    schedule_hint: Optional[str] = None,
) -> FormattedTask:
    """
    Turn a next-step phrase into a concise HubSpot task title and due date.
    Scheduling phrases are parsed for the calendar, not repeated in the title.
    """
    step = (step or "").strip()
    schedule_text = (schedule_hint or step).strip()
    due_date = _parse_date_from_text(schedule_text) or datetime.utcnow() + timedelta(days=3)
    due_date = _apply_time_from_text(schedule_text, due_date)

    cleaned = _strip_scheduling_phrases(step)
    subject = _infer_task_title(cleaned, step, contact_name)[:255]
    return FormattedTask(
        subject=subject,
        due_date=due_date,
        task_type=_infer_task_type(step),
    )


def _next_step_schedule_hints(extraction: MemoExtraction) -> list[str]:
    raw = extraction.raw_extraction or {}
    hints = raw.get("nextStepSchedules") or raw.get("next_step_schedules") or []
    if isinstance(hints, str):
        return [hints]
    return [str(h).strip() for h in hints if h is not None] if isinstance(hints, list) else []


_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _parse_date_from_text(text: str) -> Optional[datetime]:
    """
    Parse a date from Spanish/English phrases like:
    - "el martes", "el próximo martes"
    - "mañana"
    - "la próxima semana"
    - "next Tuesday"
    Also handles an already-resolved ISO date (e.g. "2025-09-11"), which the LLM
    sometimes returns directly for explicit calendar dates ("el 11 de septiembre")
    instead of the raw phrase - trusting it here avoids silently falling back to
    the "3 days from now" default and creating a task due on the wrong day.
    """
    if not text:
        return None
    lower = text.strip().lower()
    now = datetime.utcnow()

    iso_match = _ISO_DATE_RE.search(text)
    if iso_match:
        try:
            return datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass  # Malformed date (e.g. day 32) - fall through to phrase parsing

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


def _normalize_task_subject(subject: str) -> str:
    return " ".join((subject or "").lower().split())


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
        existing_subjects: Optional[set[str]] = None,
    ) -> list[str]:
        """
        Create HubSpot tasks from extraction nextSteps.
        Skips generic items like "Cerrar el trato" and subjects already on the deal.

        Returns:
            List of created task IDs
        """
        created: list[str] = []
        next_steps = extraction.nextSteps or []
        schedule_hints = _next_step_schedule_hints(extraction)
        seen = set(existing_subjects or set())

        for i, step in enumerate(next_steps):
            if not step or not isinstance(step, str):
                continue
            step = step.strip()
            if _should_skip_next_step(step):
                continue
            hint = schedule_hints[i] if i < len(schedule_hints) else None
            formatted = format_next_step_task(
                step,
                contact_name=extraction.contactName,
                schedule_hint=hint or None,
            )
            norm = _normalize_task_subject(formatted.subject)
            if norm in seen:
                continue

            task_id = await self.create_task(
                subject=formatted.subject,
                due_date=formatted.due_date,
                deal_id=deal_id,
                body=extraction.summary or "",
                hubspot_owner_id=hubspot_owner_id,
                task_type=formatted.task_type,
            )
            if task_id:
                created.append(task_id)
                seen.add(norm)

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
