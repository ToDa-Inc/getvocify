"""Pre-call brief v2. Deterministic lines from C04 intelligence. No model call."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.briefs.preparation import legacy_facts, plain_sentence, prepare_brief
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
        summary = plain_sentence((memo.get("extraction") or {}).get("summary"))
        if not summary:
            return None
        text = f"{day}: {summary}"
    return _line("hook", text, source_ref=memo.get("id"), observed_at=when)


def _commitment_why(commitment: Commitment, *, now: datetime, tz_name: str, timed: bool = False) -> str | None:
    """`timed`: the prospect or rep said a clock time, so the call line carries it («a las 12:30»)."""
    local_now = now.astimezone(_zone(tz_name))
    due_local = commitment.due_at.astimezone(_zone(tz_name))
    if due_local.date() > local_now.date():
        return None
    if commitment.kind == "call":
        when = " hoy" if due_local.date() == local_now.date() else f" el {_day_label(due_local, tz_name)}"
        if timed:
            when = f"{when} a las {due_local:%H:%M}"
        if commitment.origin == "prospect_request":
            return f"Pidió que le llamaras{when}."
        return f"Quedaste en llamarle{when}."
    what = commitment.text[:1].lower() + commitment.text[1:] if commitment.text else commitment.text
    if due_local.date() == local_now.date():
        return f"Quedó pendiente para hoy: {what}."
    return f"Quedó pendiente: {what}."


def _timed(intelligence: dict, commitment: Commitment) -> bool:
    """Whether C04 read a clock time for this commitment. The Hoy signal drops `temporal_precision`."""
    for item in intelligence.get("commitments") or []:
        if not isinstance(item, dict) or item.get("kind") != commitment.kind or item.get("text") != commitment.text:
            continue
        if _as_dt(item.get("due_at")) == commitment.due_at:
            return item.get("temporal_precision") == "time"
    return False


def _bad_moment(intelligence: dict) -> str | None:
    """The prospect's own words when the whole call was a bad moment: they could not talk and
    nothing else happened. A "me pillas en una reunión" halfway through a real conversation, or
    before booking a meeting, is not that call."""
    call = intelligence.get("call") if isinstance(intelligence.get("call"), dict) else None
    if call is not None and call.get("call_type") != "bad_moment":
        return None
    if call is None and (intelligence.get("meeting") or {}).get("agreed") is True:
        return None
    for item in intelligence.get("objections") or []:
        if not isinstance(item, dict) or item.get("kind") != "obstacle" or item.get("category") != "bad_moment":
            continue
        quote = " ".join(str(item.get("quote") or "").split())
        if quote:
            return quote
    return None


def _due_commitment(*, memo: dict, intelligence: dict, now: datetime, tz_name: str) -> Commitment | None:
    """The same `commitment_due` Hoy signal `why_line` and the T7 SDR two-line format read:
    the nearest commitment already due, whatever its kind. None if nothing is due yet."""
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
    if not touch:
        return None
    end = day_end(now, tz_name)
    for signal in signals_for_contact([touch], now=now, day_end=end):
        if signal.type != "commitment_due":
            continue
        return Commitment(
            kind=signal.payload["kind"],
            origin=signal.payload["origin"],
            text=signal.payload["text"],
            due_at=signal.due_at or now,
        )
    return None


def why_line(
    *,
    intelligence: dict,
    memo: dict,
    tz_name: str,
    now: datetime,
    no_reply: dict | None,
    crm_task: dict | None,
) -> dict | None:
    commitment = _due_commitment(memo=memo, intelligence=intelligence, now=now, tz_name=tz_name)
    if commitment is not None:
        text = _commitment_why(commitment, now=now, tz_name=tz_name, timed=_timed(intelligence, commitment))
        if text:
            return _line("why", text, source_ref=memo.get("id"), observed_at=commitment.due_at)
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


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _strip_final_period(text: str) -> str:
    text = text.strip()
    return text[:-1] if text.endswith(".") else text


def sdr_hook_line(*, memo: dict, intelligence: dict, tz_name: str, now: datetime) -> dict | None:
    """T7: SDR/general two-line format, L1 - «{fecha}: {qué se habló}. Pendiente: {pendiente}.»
    Only C04 facts; a missing summary or pending action just drops that clause. When the
    prospect could not talk (bad_moment), the summary only recaps the rep's opener, so the
    line is just «Llamada el {fecha}» and `sdr_obstacle_line` says why."""
    when = next(
        (value for value in (memo.get("capture_started_at"), memo.get("created_at")) if _as_dt(value)),
        None,
    )
    day = _day_label(when, tz_name)
    if not day:
        return None
    bad_moment = _bad_moment(intelligence) is not None
    summary = None if bad_moment else plain_sentence((memo.get("extraction") or {}).get("summary"))
    commitment = _due_commitment(memo=memo, intelligence=intelligence, now=now, tz_name=tz_name)
    pending = None
    if commitment is not None and commitment.kind != "call" and commitment.text:
        pending = _lower_first(commitment.text)
    if bad_moment:
        text = f"Llamada el {day}." if pending else f"Llamada el {day}"
    elif not summary and not pending:
        return None
    elif summary:
        text = f"{day}: {summary}"
    else:
        text = f"{day}."
    if pending:
        text = f"{text} Pendiente: {pending}."
    return _line("hook", text, source_ref=memo.get("id"), observed_at=when)


def _when_label(value, precision: str | None, *, now: datetime, tz_name: str) -> str | None:
    due = _as_dt(value)
    if due is None:
        return None
    local = due.astimezone(_zone(tz_name))
    day = "hoy" if local.date() == now.astimezone(_zone(tz_name)).date() else f"el {_day_label(local, tz_name)}"
    return f"{day} a las {local:%H:%M}" if precision == "time" else day


def _said_in(text: str | None, name: str | None) -> bool:
    """Whether a line already names this person: the brief never repeats itself."""
    return bool(text and name and name.split()[0].lower() in text.lower())


def sdr_next_lines(*, memo: dict, intelligence: dict, tz_name: str, now: datetime) -> list[dict]:
    """v8 SDR brief, from the call's own `next` block: what happened, what is owed, and the
    callback with its reason (or the hook to open with). Every line is a fact of that call."""
    nxt = intelligence.get("next") if isinstance(intelligence.get("next"), dict) else {}
    when = next(
        (value for value in (memo.get("capture_started_at"), memo.get("created_at")) if _as_dt(value)),
        None,
    )
    day = _day_label(when, tz_name)
    ref = memo.get("id")
    lines: list[dict] = []
    outcome = (nxt.get("outcome") or {}).get("text") if isinstance(nxt.get("outcome"), dict) else None
    # The outcome already says, cleanly, that they could not talk; the raw quote is only a
    # fallback when there is no outcome (ASR quotes stutter: "estoy estoy en una…").
    obstacle = None if outcome else _bad_moment(intelligence)
    if day:
        lines.append(_line("hook", f"Llamada el {day}: {outcome}" if outcome else f"Llamada el {day}",
                           source_ref=ref, observed_at=when))
    if obstacle:
        lines.append(_line("obstacle", f"No pudo atenderte: «{obstacle}»", source_ref=ref))
    email = nxt.get("followup_email") if isinstance(nxt.get("followup_email"), dict) else {}
    referral = nxt.get("referral") if isinstance(nxt.get("referral"), dict) else None
    if email.get("needed") and email.get("kind") != "calendar_invite" and email.get("content"):
        to = f" a {email['to']}" if email.get("to") else ""
        lines.append(_line("pending", f"Le debes un correo{to}: {_lower_first(_strip_final_period(email['content']))}.", source_ref=ref))
    elif referral and (referral.get("name") or referral.get("role")) and not _said_in(outcome, referral.get("name")):
        who = " ".join(x for x in (referral.get("name"), f"({referral['role']})" if referral.get("role") and referral.get("name") else referral.get("role")) if x)
        lines.append(_line("pending", f"Te derivó a {who}.", source_ref=ref))
    callback = nxt.get("callback") if isinstance(nxt.get("callback"), dict) else {}
    hook = nxt.get("hook")
    if callback.get("needed"):
        label = _when_label(callback.get("when"), callback.get("temporal_precision"), now=now, tz_name=tz_name)
        label = f" {label}" if label else (f" {callback['when_text']}" if callback.get("when_text") else "")
        head = f"Te pidió que le llamaras{label}" if callback.get("who_asked") == "prospect" else f"Quedaste en llamarle{label}"
        reason = _strip_final_period(str(callback.get("reason") or ""))
        lines.append(_line("why", f"{head}: {_lower_first(reason)}." if reason else f"{head}.", source_ref=ref,
                           observed_at=callback.get("when")))
    elif hook:
        lines.append(_line("why", f"Para abrir: {_lower_first(_strip_final_period(hook))}.", source_ref=ref))
    return lines[:MAX_LINES]


def sdr_why_line(
    *,
    intelligence: dict,
    memo: dict,
    tz_name: str,
    now: datetime,
    no_reply: dict | None,
    crm_task: dict | None,
) -> dict | None:
    """T7: SDR/general two-line format, L2 - «{porqué}. Gancho: "{cita}".»
    `porqué` is the same reason `why_line` uses (a due call commitment, with its time when
    one was said, then no_reply, then a CRM task); `cita` is the pain quote `hook_line`
    shows the AE. Either half can be missing on its own; both missing drops the line."""
    porque = None
    source_ref = None
    observed_at = None
    commitment = _due_commitment(memo=memo, intelligence=intelligence, now=now, tz_name=tz_name)
    if commitment is not None and commitment.kind == "call":
        reason = _commitment_why(commitment, now=now, tz_name=tz_name, timed=_timed(intelligence, commitment))
        if reason:
            porque = _strip_final_period(reason)
            source_ref, observed_at = memo.get("id"), commitment.due_at
    if porque is None and no_reply and no_reply.get("text"):
        porque = _strip_final_period(str(no_reply["text"]))
        source_ref, observed_at = no_reply.get("source_ref"), no_reply.get("observed_at")
    if porque is None and crm_task and crm_task.get("text"):
        porque = _strip_final_period(str(crm_task["text"]))
        source_ref, observed_at = crm_task.get("source_ref"), crm_task.get("observed_at")

    quote = " ".join(str(pain_quote(intelligence) or "").split())

    if not porque and not quote:
        return None
    parts = []
    if porque:
        parts.append(f"{porque[:1].upper()}{porque[1:]}.")
    if quote:
        parts.append(f'Gancho: "{quote}"')
        if source_ref is None:
            source_ref = memo.get("id")
    return _line("why", " ".join(parts), source_ref=source_ref, observed_at=observed_at)


def sdr_obstacle_line(*, memo: dict, intelligence: dict) -> dict | None:
    """T7: when the prospect could not talk, why, in their own words. It is the opener for
    the callback, so it sits between the date and the reason to call."""
    quote = _bad_moment(intelligence)
    if not quote:
        return None
    return _line("obstacle", f"No pudo atenderte: «{quote}»", source_ref=memo.get("id"))


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


def _custom_entry(objection_id: str | None, entries: list[dict]) -> dict | None:
    """C04 v7: the company's own objection entry a read objection was matched to, or None."""
    slug = str(objection_id or "").strip()
    if not slug:
        return None
    wanted = f"objection:custom:{slug}"
    for entry in entries or []:
        if isinstance(entry, dict) and str(entry.get("entry_id") or "") == wanted:
            return entry
    return None


def _category_heading(category: str) -> str:
    label = CATEGORY["es"].get(category, category)
    return label[:1].upper() + label[1:]


def say_line(*, intelligence: dict, playbook_entries: list[dict] | None) -> dict | None:
    for objection in _open_objections(intelligence):
        category = str(objection.get("category") or "other")
        custom = _custom_entry(objection.get("objection_id"), playbook_entries or [])
        custom_guidance = " ".join(str((custom or {}).get("guidance") or "").split())
        if custom_guidance:
            # The company's own answer to this exact objection wins over the generic category one.
            label = " ".join(str(custom.get("label") or "").split()) or _category_heading(category)
            return _line("say", f"{label}: {custom_guidance}", source="playbook", source_ref=objection.get("id"))
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


def missing_steps(*, steps: list[dict], observations: list[dict]) -> list[str]:
    """The steps `progress_label` calls «falta …», as a list."""
    missed = {
        str(item.get("step_id") or "")
        for item in observations or []
        if isinstance(item, dict) and item.get("step_id") and item.get("status") == "missed"
    }
    labels: list[str] = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        label = " ".join(str(step.get("label") or step_id).split())
        if label and step_id in missed:
            labels.append(label.lower())
    return labels


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
    cold_profile: dict | None = None,
    hoy_priority: dict | None = None,
    sdr_two_line: bool = False,
) -> dict:
    now = now or datetime.now(timezone.utc)
    failed = coverage in {"partial", "unavailable"}
    notice = "No se pudo cargar todo." if failed else None
    if coverage == "unavailable":
        return {"status": "unavailable", "text": notice, "lines": [], "notice": notice, "label": None}

    latest = max(memos, key=lambda row: str(row.get("created_at") or "")) if memos else None
    if latest is None:
        from app.services.briefs.cold_call import prepare_cold_brief_v2

        return prepare_cold_brief_v2(
            coverage=coverage,
            profile=cold_profile,
            tz_name=tz_name,
            crm_task=crm_task,
            hoy_priority=hoy_priority,
        )

    if not is_current(latest):
        return prepare_brief(**legacy_facts(memos, coverage=coverage), crm_task=crm_task)

    extraction = latest.get("extraction") if isinstance(latest.get("extraction"), dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}

    lines: list[dict] = []
    if sdr_two_line and isinstance(intelligence.get("next"), dict):
        lines = sdr_next_lines(memo=latest, intelligence=intelligence, tz_name=tz_name, now=now)
    elif sdr_two_line:
        # T7: SDR/general, brief for a call - two lines, no playbook `say` line.
        hook = sdr_hook_line(memo=latest, intelligence=intelligence, tz_name=tz_name, now=now)
        if hook:
            lines.append(hook)
        obstacle = sdr_obstacle_line(memo=latest, intelligence=intelligence)
        if obstacle:
            lines.append(obstacle)
        why = sdr_why_line(
            intelligence=intelligence,
            memo=latest,
            tz_name=tz_name,
            now=now,
            no_reply=no_reply,
            crm_task=crm_task,
        )
        if why:
            lines.append(why)
    else:
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
    missing = missing_steps(steps=playbook_steps or [], observations=intelligence.get("playbook_observations") or [])

    if coverage == "partial":
        return {"status": "partial", "text": notice, "lines": lines, "notice": notice, "label": label, "missing_steps": missing}

    if not lines:
        day = str(latest.get("created_at") or "")[:10]
        return {
            "status": "nothing_pending",
            "text": f"Última vez: {day}. No quedó nada pendiente.",
            "lines": [],
            "notice": None,
            "label": label,
            "missing_steps": missing,
        }

    return {"status": "ready", "text": None, "lines": lines, "notice": None, "label": label, "missing_steps": missing}
