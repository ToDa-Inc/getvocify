"""CRM tasks built from C04 commitments (COMMITMENT_TASKS_ENABLED).

The task says what Hoy says: the commitment text, due when Hoy shows it due.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.memo import MemoExtraction
from app.services.feature_flags import is_enabled

FLAG = "COMMITMENT_TASKS_ENABLED"
DEFAULT_TZ = "Europe/Madrid"
DAY_START = time(9, 0)
REVIEW_CRMS = frozenset({"hubspot", "pipedrive", "salesforce"})
# Salesforce has no task write path yet: its review shows the rows, its sync writes none.
WRITING_CRMS = frozenset({"hubspot", "pipedrive"})


@dataclass(frozen=True)
class CommitmentTask:
    commitment_id: str
    kind: str
    text: str
    due_at: Optional[datetime]

    @property
    def due_date(self) -> Optional[str]:
        return self.due_at.date().isoformat() if self.due_at else None


def _zone(name: Any) -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(str(name)) if name else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def rep_timezone(user_id: Any) -> str:
    """The zone Hoy uses for this rep."""
    if not user_id:
        return DEFAULT_TZ
    try:
        from app.services.coaching.brief_preferences import read_preference

        name = read_preference(str(user_id)).get("timezone")
    except Exception:
        return DEFAULT_TZ
    return str(name) if _zone(name) else DEFAULT_TZ


def task_due(commitment: dict, *, tz_name: str) -> Optional[datetime]:
    """A time is kept; a day alone starts at 9:00 for the rep; no day is no date."""
    raw = commitment.get("due_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        due = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if due.tzinfo is None:
        return None
    if commitment.get("temporal_precision") == "time":
        return due
    return datetime.combine(due.date(), DAY_START, tzinfo=_zone(tz_name) or ZoneInfo(DEFAULT_TZ))


def _display(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text[:1].upper() + text[1:]


def commitment_tasks(memo: dict, *, tz_name: str) -> Optional[list[CommitmentTask]]:
    """None when the memo has no current C04: the caller keeps nextSteps."""
    from app.services.intelligence.extract import is_current

    if not is_current(memo):
        return None
    block = memo["extraction"]["intelligence"]
    tasks = []
    for item in block.get("commitments") or []:
        if not isinstance(item, dict) or not item.get("id") or not str(item.get("text") or "").strip():
            continue
        tasks.append(CommitmentTask(
            commitment_id=str(item["id"]),
            kind=str(item.get("kind") or "other"),
            text=_display(item["text"]),
            due_at=task_due(item, tz_name=tz_name),
        ))
    return tasks


def _same_text(a: str, b: str) -> bool:
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


def _schedule_hints(extraction: MemoExtraction) -> tuple[Optional[str], list]:
    raw = extraction.raw_extraction or {}
    for key in ("nextStepSchedules", "next_step_schedules"):
        if isinstance(raw.get(key), list):
            return key, list(raw[key])
    return None, []


def _day(hint: Any) -> Optional[str]:
    text = str(hint or "").strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def split_reviewed(
    tasks: list[CommitmentTask], extraction: MemoExtraction
) -> tuple[list[CommitmentTask], MemoExtraction]:
    """Rows the rep kept as they were stay commitments; an edited or added row stays a nextStep."""
    key, hints = _schedule_hints(extraction)
    kept: list[CommitmentTask] = []
    left_steps: list[str] = []
    left_hints: list = []
    for i, step in enumerate(extraction.nextSteps or []):
        hint = hints[i] if i < len(hints) else ""
        match = next(
            (t for t in tasks if t not in kept and _same_text(t.text, step)),
            None,
        )
        day = _day(hint)
        if match is not None and (day is None or day == match.due_date):
            kept.append(match)
            continue
        left_steps.append(step)
        left_hints.append(hint)
    update: dict[str, Any] = {"nextSteps": left_steps}
    if key:
        update["raw_extraction"] = {**(extraction.raw_extraction or {}), key: left_hints}
    return kept, extraction.model_copy(update=update)


def _company(memo: dict, connection: Optional[dict]) -> Optional[str]:
    return memo.get("company_id") or (connection or {}).get("company_id")


def preview_kwargs(supabase: Any, *, memo: dict, connection: Optional[dict]) -> dict[str, Any]:
    provider = str((connection or {}).get("provider") or "").lower()
    if provider not in REVIEW_CRMS or not is_enabled(supabase, _company(memo, connection), FLAG):
        return {}
    tasks = commitment_tasks(memo, tz_name=rep_timezone(memo.get("user_id")))
    return {} if tasks is None else {"commitment_tasks": tasks}


def sync_plan(
    supabase: Any,
    *,
    memo: dict,
    connection: Optional[dict],
    extraction: MemoExtraction,
    reviewed: bool,
) -> Optional[tuple[list[CommitmentTask], MemoExtraction]]:
    """(tasks to write, extraction whose nextSteps are still written the old way), or None."""
    provider = str((connection or {}).get("provider") or "").lower()
    if provider not in WRITING_CRMS or not is_enabled(supabase, _company(memo, connection), FLAG):
        return None
    tasks = commitment_tasks(memo, tz_name=rep_timezone(memo.get("user_id")))
    if tasks is None:
        return None
    if reviewed:
        return split_reviewed(tasks, extraction)
    return tasks, extraction.model_copy(update={"nextSteps": []})


def with_task_ids(extraction_data: dict, memo: dict, task_ids: dict[str, str]) -> dict:
    """A copy whose commitments carry the id of the CRM task written for them."""
    if not task_ids:
        return extraction_data
    out = copy.deepcopy(extraction_data)
    block = out.get("intelligence")
    if not isinstance(block, dict) or not block.get("commitments"):
        stored = (memo.get("extraction") or {}).get("intelligence")
        if not isinstance(stored, dict):
            return extraction_data
        block = out["intelligence"] = copy.deepcopy(stored)
    for item in block.get("commitments") or []:
        if isinstance(item, dict) and str(item.get("id")) in task_ids:
            item["crm_task_id"] = task_ids[str(item["id"])]
    return out
