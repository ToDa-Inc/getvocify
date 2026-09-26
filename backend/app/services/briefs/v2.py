"""Pre-call brief v2. Deterministic lines from C04 intelligence. No model call."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.briefs.preparation import legacy_facts, prepare_brief
from app.services.followup_logic import pain_quote
from app.services.hoy.materialize import day_end
from app.services.hoy.reasons import CATEGORY, MONTH
from app.services.hoy.signals import Commitment, signals_for_contact, touch_from_intelligence
from app.services.intelligence.extract import is_current

DEFAULT_TZ = "Europe/Madrid"
MAX_LINES = 3


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def _as_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _day_label(value, tz_name: str) -> str | None:
    parsed = _as_dt(value)
    if parsed is None:
        return None
    local = parsed.astimezone(_zone(tz_name))
    return f"{local.day} {MONTH['es'][local.month - 1]}"


def _line(kind: str, text: str, *, source_ref=None, observed_at=None, source: str | None = None) -> dict:
    row = {"type": kind, "text": text, "source_ref": source_ref, "observed_at": observed_at}
    if source:
        row["source"] = source
    return row


def hook_line(*, memo: dict, intelligence: dict, tz_name: str) -> dict | None:
    when = next(
        (value for value in (memo.get("capture_started_at"), memo.get("created_at")) if _as_dt(value)),
        None,
    )
    day = _day_label(when, tz_name)
    if not day:
        return None
    quote = " ".join(str(pain_quote(intelligence) or "").split())
    if quote:
        text = f'{day}: «{quote}»'
    else:
        summary = " ".join(str((memo.get("extraction") or {}).get("summary") or "").split())
        if not summary:
            return None
        text = f"{day}: {summary}"
    return _line("hook", text, source_ref=memo.get("id"), observed_at=when)


def _commitment_why(commitment: Commitment, *, now: datetime, tz_name: str) -> str | None:
    local_now = now.astimezone(_zone(tz_name))
    due_local = commitment.due_at.astimezone(_zone(tz_name))
    if due_local.date() > local_now.date():
        return None
    if commitment.kind == "call":
        if due_local.date() == local_now.date():
            return "Pidió que la llamaras hoy." if commitment.origin == "prospect_request" else "Quedaste en llamarle hoy."
        return "Pidió que la llamaras." if commitment.origin == "prospect_request" else "Quedaste en llamarle."
    what = commitment.text[:1].lower() + commitment.text[1:] if commitment.text else commitment.text
    if due_local.date() == local_now.date():
        return f"Quedó pendiente para hoy: {what}."
    return f"Quedó pendiente: {what}."


def why_line(
    *,
    intelligence: dict,
    memo: dict,
    tz_name: str,
    now: datetime,
    no_reply: dict | None,
    crm_task: dict | None,
) -> dict | None:
    at = _as_dt(memo.get("capture_started_at")) or _as_dt(memo.get("created_at"))
    dated = [
        item for item in intelligence.get("commitments") or []
        if isinstance(item, dict) and _as_dt(item.get("due_at"))
    ]
    touch = touch_from_intelligence(
        memo_id=str(memo.get("id") or ""),
        contact_id=str(memo.get("hubspot_contact_id") or ""),
        deal_id=str(memo.get("hubspot_deal_id") or "") or None,
        at=at,
        intelligence={**intelligence, "commitments": dated},
        history_complete=True,
    )
    if touch:
        end = day_end(now, tz_name)
        for signal in signals_for_contact([touch], now=now, day_end=end):
            if signal.type != "commitment_due":
                continue
            commitment = Commitment(
                kind=signal.payload["kind"],
                origin=signal.payload["origin"],
                text=signal.payload["text"],
                due_at=signal.due_at or now,
            )
            text = _commitment_why(commitment, now=now, tz_name=tz_name)
            if text:
                return _line("why", text, source_ref=memo.get("id"), observed_at=signal.due_at)
    if no_reply and no_reply.get("text"):
        return _line(
            "why",
            str(no_reply["text"]),
            source_ref=no_reply.get("source_ref"),
            observed_at=no_reply.get("observed_at"),
        )
    if crm_task and crm_task.get("text"):
        return _line(
            "why",
            str(crm_task["text"]),
            source_ref=crm_task.get("source_ref"),
            observed_at=crm_task.get("observed_at"),
        )
    return None


def _open_objections(intelligence: dict) -> list[dict]:
    """C04 cannot always tell whether an objection was handled; «unknown» stays open."""
    items = []
    for item in intelligence.get("objections") or []:
        if not isinstance(item, dict):
            continue
        resolution = item.get("resolution") or item.get("state") or "unknown"
        if resolution not in {"open", "unknown"}:
            continue
        if not " ".join(str(item.get("quote") or item.get("text") or "").split()):
            continue
        items.append(item)
    return items


def _playbook_guidance(category: str, entries: list[dict]) -> str | None:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("category") or "").lower() != str(category or "other").lower():
            continue
        guidance = " ".join(str(entry.get("guidance") or entry.get("text") or "").split())
        if guidance:
            return guidance
    return None


def _category_heading(category: str) -> str:
    label = CATEGORY["es"].get(category, category)
    return label[:1].upper() + label[1:]


def say_line(*, intelligence: dict, playbook_entries: list[dict] | None) -> dict | None:
    for objection in _open_objections(intelligence):
        category = str(objection.get("category") or "other")
        guidance = _playbook_guidance(category, playbook_entries or [])
        if guidance:
            text = f"{_category_heading(category)}: {guidance}"
            return _line("say", text, source="playbook", source_ref=objection.get("id"))
    for item in intelligence.get("competitor_mentions") or []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or item.get("text") or "").split())
        if name:
            return _line("say", f"Usa {name}", source_ref=item.get("id"))
    return None


def progress_label(*, steps: list[dict], observations: list[dict]) -> str | None:
    if not steps or not observations:
        return None
    by_step = {
        str(item.get("step_id") or ""): item
        for item in observations
        if isinstance(item, dict) and item.get("step_id")
    }
    met: list[str] = []
    missed: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        label = " ".join(str(step.get("label") or step_id).split())
        if not label:
            continue
        obs = by_step.get(step_id)
        if not obs:
            continue
        status = str(obs.get("status") or "unknown")
        if status == "met":
            met.append(label if label.lower().endswith(" hecho") else f"{label} hecho")
        elif status == "missed":
            missed.append(label.lower())
    if not met and not missed:
        return None
    parts: list[str] = []
    if met:
        parts.append(" · ".join(met))
    if missed:
        parts.append(" · ".join(f"falta {label}" for label in missed))
    return " · ".join(parts)


def prepare_brief_v2(
    *,
    coverage: str,
    memos: list[dict],
    tz_name: str,
    now: datetime | None = None,
    no_reply: dict | None = None,
    crm_task: dict | None = None,
    playbook_steps: list[dict] | None = None,
    playbook_entries: list[dict] | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    failed = coverage in {"partial", "unavailable"}
    notice = "No se pudo cargar todo." if failed else None
    if coverage == "unavailable":
        return {"status": "unavailable", "text": notice, "lines": [], "notice": notice, "label": None}

    latest = max(memos, key=lambda row: str(row.get("created_at") or "")) if memos else None
    if latest is None:
        return {**prepare_brief(coverage=coverage, crm_task=crm_task), "label": None}

    if not is_current(latest):
        return prepare_brief(**legacy_facts(memos, coverage=coverage), crm_task=crm_task)

    extraction = latest.get("extraction") if isinstance(latest.get("extraction"), dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}

    lines: list[dict] = []
    hook = hook_line(memo=latest, intelligence=intelligence, tz_name=tz_name)
    if hook:
        lines.append(hook)
    why = why_line(
        intelligence=intelligence,
        memo=latest,
        tz_name=tz_name,
        now=now,
        no_reply=no_reply,
        crm_task=crm_task,
    )
    if why:
        lines.append(why)
    say = say_line(intelligence=intelligence, playbook_entries=playbook_entries)
    if say:
        lines.append(say)
    lines = lines[:MAX_LINES]

    label = progress_label(steps=playbook_steps or [], observations=intelligence.get("playbook_observations") or [])

    if coverage == "partial":
        return {"status": "partial", "text": notice, "lines": lines, "notice": notice, "label": label}

    if not lines:
        day = str(latest.get("created_at") or "")[:10]
        return {
            "status": "nothing_pending",
            "text": f"Última vez: {day}. No quedó nada pendiente.",
            "lines": [],
            "notice": None,
            "label": label,
        }

    return {"status": "ready", "text": None, "lines": lines, "notice": None, "label": label}
