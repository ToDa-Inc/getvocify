"""
Task operations service for HubSpot.

Creates tasks from MemoExtraction nextSteps and associates them with deals.
Supports listing, updating, and deleting tasks for deal merge flows.
Uses /crm/v3/objects/tasks API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from .client import HubSpotClient
from .exceptions import HubSpotError
from app.models.memo import MemoExtraction

logger = logging.getLogger(__name__)

# Date-only task due dates (extension picker, LLM YYYY-MM-DD) default to 9:00 local.
# Europe/Madrid covers CET/CEST for the team's timezone.
TASK_DUE_TZ = ZoneInfo("Europe/Madrid")
TASK_DEFAULT_DUE_HOUR = 9
TASK_DEFAULT_DUE_MINUTE = 0

_EXPLICIT_TIME_RE = re.compile(
    r"(?:a las|at)\s+(\d{1,2})(?::(\d{2}))?\s*(h|hrs?|horas?|am|pm)?",
    re.IGNORECASE,
)


def _task_tz_now() -> datetime:
    return datetime.now(TASK_DUE_TZ)


def _calendar_date(dt: datetime) -> datetime.date:
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone(TASK_DUE_TZ).date()


def _at_default_task_hour(dt: datetime) -> datetime:
    """Set 9:00 Europe/Madrid on the parsed calendar day."""
    day = _calendar_date(dt)
    return datetime(
        day.year,
        day.month,
        day.day,
        TASK_DEFAULT_DUE_HOUR,
        TASK_DEFAULT_DUE_MINUTE,
        0,
        tzinfo=TASK_DUE_TZ,
    )


def _default_task_due_in_days(days: int) -> datetime:
    target = _task_tz_now().date() + timedelta(days=days)
    return datetime(
        target.year,
        target.month,
        target.day,
        TASK_DEFAULT_DUE_HOUR,
        TASK_DEFAULT_DUE_MINUTE,
        0,
        tzinfo=TASK_DUE_TZ,
    )


def _has_explicit_time_in_text(text: str) -> bool:
    return bool(_EXPLICIT_TIME_RE.search(text or ""))


def normalize_task_due_datetime(dt: datetime) -> datetime:
    """
    Ensure HubSpot task due datetimes are timezone-aware and not midnight
    when only a calendar date was provided (extension picker, YYYY-MM-DD).
    """
    if dt.tzinfo is None:
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
            return _at_default_task_hour(dt)
        return dt.replace(tzinfo=TASK_DUE_TZ)
    local = dt.astimezone(TASK_DUE_TZ)
    if local.hour == 0 and local.minute == 0 and local.second == 0 and local.microsecond == 0:
        return local.replace(
            hour=TASK_DEFAULT_DUE_HOUR,
            minute=TASK_DEFAULT_DUE_MINUTE,
            second=0,
            microsecond=0,
        )
    return local



@dataclass(frozen=True)
class FormattedTask:
    subject: str
    due_date: datetime
    task_type: str = "TODO"


TaskSkipReason = Literal[
    "empty",
    "generic",
    "duplicate",
    "hubspot_error",
    "hubspot_empty_response",
]


@dataclass
class TaskSkip:
    reason: TaskSkipReason
    step: str
    subject: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TaskBatchResult:
    created_ids: list[str] = field(default_factory=list)
    skipped: list[TaskSkip] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return len(self.created_ids)


def summarize_task_batch(
    requested_count: int,
    batch: TaskBatchResult,
    *,
    merge_mode: bool = False,
    merge_failed: bool = False,
    already_synced: bool = False,
    no_target: bool = False,
) -> Optional[str]:
    """Human-readable warning when the rep expected tasks but none (or too few) were created."""
    if requested_count <= 0:
        return None
    created = batch.created_count
    if created >= requested_count:
        return None

    if already_synced:
        return (
            f"Tasks were not created again ({requested_count} requested) — "
            "this memo was already synced. Edit and re-approve to retry."
        )
    if no_target:
        return (
            f"No HubSpot deal or contact to attach {requested_count} task(s) to. "
            "Pick a contact or deal and sync again."
        )
    if merge_failed:
        if created == 0:
            return (
                f"Could not merge tasks with the existing deal ({requested_count} requested). "
                "Try syncing again or create the task manually in HubSpot."
            )
        return (
            f"Task merge failed partway — created {created} of {requested_count}. "
            "Check HubSpot for the rest."
        )

    if created == 0:
        if merge_mode:
            return (
                f"No new tasks were added ({requested_count} requested). "
                "The deal already has similar tasks, or the merge decided no changes were needed."
            )
        by_reason: dict[str, int] = {}
        for skip in batch.skipped:
            by_reason[skip.reason] = by_reason.get(skip.reason, 0) + 1
        parts: list[str] = []
        if by_reason.get("duplicate"):
            parts.append(f"{by_reason['duplicate']} duplicate(s)")
        if by_reason.get("generic"):
            parts.append(f"{by_reason['generic']} too generic")
        if by_reason.get("hubspot_error") or by_reason.get("hubspot_empty_response"):
            n = by_reason.get("hubspot_error", 0) + by_reason.get("hubspot_empty_response", 0)
            parts.append(f"{n} HubSpot error(s)")
        detail = f" ({', '.join(parts)})" if parts else ""
        return f"No tasks were created{detail}. Check backend logs for details."

    return f"Created {created} of {requested_count} tasks — some were skipped as duplicates or too generic."


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
    match = _EXPLICIT_TIME_RE.search(text or "")
    if not match:
        return base
    day = _calendar_date(base)
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = (match.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return datetime(day.year, day.month, day.day, hour, minute, 0, tzinfo=TASK_DUE_TZ)


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
    time_source = " ".join(filter(None, [schedule_hint, step])).strip() or schedule_text
    parsed = _parse_date_from_text(schedule_text)
    if parsed:
        due_date = parsed
    else:
        due_date = _default_task_due_in_days(3)
    if _has_explicit_time_in_text(time_source):
        due_date = _apply_time_from_text(time_source, due_date)
    else:
        due_date = _at_default_task_hour(due_date)

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


def detected_task_due_iso(step: str, schedule_hint: Optional[str] = None) -> Optional[str]:
    """ISO date only when the transcript actually timed the task — never the +3 day default."""
    parsed = _parse_date_from_text((schedule_hint or step or "").strip())
    return parsed.date().isoformat() if parsed else None


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
    now = _task_tz_now()

    iso_match = _ISO_DATE_RE.search(text)
    if iso_match:
        try:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            return datetime(y, m, d)
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

    return None


def _normalize_task_subject(subject: str) -> str:
    return " ".join((subject or "").lower().split())


class HubSpotTasksService:
    """
    Service for creating HubSpot tasks from voice memo next steps.
    """

    OBJECT_TYPE = "tasks"
    # Task-to-deal association type (HubSpot default: 216 = Task to deal)
    TASK_TO_DEAL_ASSOCIATION_TYPE = "216"
    # Task-to-contact association type (HubSpot default: 204 = Task to contact).
    # Used when a memo has no associated deal (contact-first flow) so next-step
    # tasks still land somewhere instead of being silently dropped.
    TASK_TO_CONTACT_ASSOCIATION_TYPE = "204"

    def __init__(self, client: HubSpotClient):
        self.client = client

    def _to_timestamp_ms(self, dt: datetime) -> str:
        """Convert datetime to HubSpot timestamp (milliseconds)."""
        normalized = normalize_task_due_datetime(dt)
        return str(int(normalized.timestamp() * 1000))

    async def create_task(
        self,
        subject: str,
        due_date: datetime,
        deal_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        body: Optional[str] = None,
        priority: str = "MEDIUM",
        task_type: str = "TODO",
        hubspot_owner_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a task in HubSpot and associate it with a generic target.

        Args:
            subject: Task title (hs_task_subject)
            due_date: Due date for hs_timestamp
            deal_id: Optional deal ID to associate (kept optional - existing callers
                that only pass deal_id keep working unchanged)
            contact_id: Optional contact ID to associate. Used for the contact-first
                flow when there's no deal to hang the task off of.
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
        associations = []
        if deal_id:
            associations.append(
                {
                    "to": {"id": deal_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": int(self.TASK_TO_DEAL_ASSOCIATION_TYPE),
                        }
                    ],
                }
            )
        if contact_id:
            associations.append(
                {
                    "to": {"id": contact_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": int(self.TASK_TO_CONTACT_ASSOCIATION_TYPE),
                        }
                    ],
                }
            )
        if associations:
            payload["associations"] = associations

        target_type = "deal" if deal_id else ("contact" if contact_id else "none")
        target_id = deal_id or contact_id
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.OBJECT_TYPE}",
                data=payload,
            )
            if response and "id" in response:
                task_id = str(response["id"])
                logger.info(
                    "HubSpot task created",
                    extra={
                        "task_id": task_id,
                        "subject": properties["hs_task_subject"][:80],
                        "target_type": target_type,
                        "target_id": target_id,
                        "due_date": due_date.isoformat(),
                    },
                )
                return task_id
            logger.warning(
                "HubSpot task create returned no id",
                extra={
                    "subject": properties["hs_task_subject"][:80],
                    "target_type": target_type,
                    "target_id": target_id,
                    "response_keys": list(response.keys()) if isinstance(response, dict) else None,
                },
            )
            return None
        except HubSpotError as e:
            logger.warning(
                "HubSpot task create failed: %s",
                e.message,
                extra={
                    "subject": properties["hs_task_subject"][:80],
                    "target_type": target_type,
                    "target_id": target_id,
                    "due_date": due_date.isoformat(),
                    "status_code": e.status_code,
                    "hubspot_error": e.response_data,
                },
            )
            return None

    async def create_tasks_from_extraction(
        self,
        extraction: MemoExtraction,
        deal_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        hubspot_owner_id: Optional[str] = None,
        existing_subjects: Optional[set[str]] = None,
    ) -> TaskBatchResult:
        """
        Create HubSpot tasks from extraction nextSteps.
        Skips generic items like "Cerrar el trato" and subjects already on the deal.
        Associates to deal_id when present, else to contact_id (contact-first flow).

        Returns:
            TaskBatchResult with created ids and per-step skip reasons
        """
        result = TaskBatchResult()
        next_steps = extraction.nextSteps or []
        schedule_hints = _next_step_schedule_hints(extraction)
        seen = set(existing_subjects or set())

        for i, step in enumerate(next_steps):
            if not step or not isinstance(step, str):
                result.skipped.append(TaskSkip(reason="empty", step=str(step or "")))
                continue
            step = step.strip()
            if _should_skip_next_step(step):
                logger.info(
                    "Skipping generic next step for task",
                    extra={"step": step[:120], "reason": "generic"},
                )
                result.skipped.append(TaskSkip(reason="generic", step=step))
                continue
            hint = schedule_hints[i] if i < len(schedule_hints) else None
            formatted = format_next_step_task(
                step,
                contact_name=extraction.contactName,
                schedule_hint=hint or None,
            )
            norm = _normalize_task_subject(formatted.subject)
            if norm in seen:
                logger.info(
                    "Skipping duplicate task subject",
                    extra={"step": step[:120], "subject": formatted.subject[:80], "reason": "duplicate"},
                )
                result.skipped.append(
                    TaskSkip(reason="duplicate", step=step, subject=formatted.subject)
                )
                continue

            task_id = await self.create_task(
                subject=formatted.subject,
                due_date=formatted.due_date,
                deal_id=deal_id,
                contact_id=None if deal_id else contact_id,
                body=extraction.summary or "",
                hubspot_owner_id=hubspot_owner_id,
                task_type=formatted.task_type,
            )
            if task_id:
                result.created_ids.append(task_id)
                seen.add(norm)
            else:
                result.skipped.append(
                    TaskSkip(
                        reason="hubspot_error",
                        step=step,
                        subject=formatted.subject,
                        error="HubSpot API returned no task id",
                    )
                )

        if next_steps and not result.created_ids:
            logger.warning(
                "No HubSpot tasks created from nextSteps",
                extra={
                    "requested_count": len(next_steps),
                    "skipped_count": len(result.skipped),
                    "skip_reasons": [s.reason for s in result.skipped],
                    "deal_id": deal_id,
                    "contact_id": contact_id,
                },
            )
        elif result.skipped:
            logger.info(
                "HubSpot tasks partially created from nextSteps",
                extra={
                    "requested_count": len(next_steps),
                    "created_count": result.created_count,
                    "skipped_count": len(result.skipped),
                    "skip_reasons": [s.reason for s in result.skipped],
                },
            )

        return result

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
        return await self._list_tasks_for_object("deals", deal_id, properties)

    async def list_tasks_for_contact(
        self,
        contact_id: str,
        properties: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        List tasks associated with a contact. Mirrors list_tasks_for_deal -
        needed for the no-deal (contact-first / skip_deal) flow, where tasks
        are associated to the contact instead of a deal: without this,
        create_tasks_from_extraction's existing_subjects dedupe always sees
        an empty set for that flow (sync.py only ever populated it from
        list_tasks_for_deal, gated on `deal_id and not is_new_deal`), so a
        retry of the same memo with no deal can create duplicate tasks on
        the contact - the exact protection the deal flow already has.

        Args:
            contact_id: HubSpot contact ID
            properties: Optional list of properties to fetch (default: hs_task_subject, hs_timestamp)

        Returns:
            List of task dicts with id, subject, due_date (datetime or None)
        """
        return await self._list_tasks_for_object("contacts", contact_id, properties)

    async def _list_tasks_for_object(
        self,
        object_type: str,
        object_id: str,
        properties: Optional[list[str]] = None,
    ) -> list[dict]:
        """Shared implementation behind list_tasks_for_deal/list_tasks_for_contact."""
        props = properties or ["hs_task_subject", "hs_timestamp"]
        try:
            # Get task IDs associated with the object (v4 associations)
            resp = await self.client.get(
                f"/crm/v4/objects/{object_type}/{object_id}/associations/tasks"
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
            logger.warning("Failed to list tasks for %s %s: %s", object_type, object_id, e)
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
