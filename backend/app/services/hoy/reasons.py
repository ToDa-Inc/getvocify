"""The most-read sentence in the product, written once, server-side."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.hoy.signals import Signal

CATEGORY = {
    "es": {
        "price": "precio",
        "timing": "plazo",
        "authority": "decisor",
        "competitor": "competencia",
        "status_quo": "statu quo",
        "trust": "confianza",
        "other": "otra",
    },
    "en": {
        "price": "price",
        "timing": "timing",
        "authority": "decision-maker",
        "competitor": "competitor",
        "status_quo": "status quo",
        "trust": "trust",
        "other": "other",
    },
}


MONTH = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
SUBJECT_MAX = 60


def _lang(lang: str) -> str:
    return "en" if (lang or "").lower().startswith("en") else "es"


def _clause(text: str) -> str:
    cleaned = " ".join((text or "").split()).rstrip(".")
    return cleaned[:1].lower() + cleaned[1:] if cleaned else cleaned


def due_label(due_at: datetime, *, now: datetime, lang: str = "es") -> str:
    lang = _lang(lang)
    days = (now.date() - due_at.date()).days
    if days <= 0:
        if due_at > now:
            return f"Hoy a las {due_at:%H:%M}" if lang == "es" else f"Today at {due_at:%H:%M}"
        return "Hoy" if lang == "es" else "Today"
    if days == 1:
        return "Vencía ayer" if lang == "es" else "Due yesterday"
    return f"Vencía hace {days} días" if lang == "es" else f"Due {days} days ago"


def reason(signal: Signal, *, lang: str = "es") -> str:
    lang = _lang(lang)
    payload = signal.payload
    if signal.type == "commitment_due":
        kind, origin, what = payload["kind"], payload["origin"], _clause(payload["text"])
        if lang == "es":
            if kind == "call":
                return "Pidió que le llamaras." if origin == "prospect_request" else "Quedaste en llamarle."
            if origin == "rep_promise":
                return f"Le prometiste {what}."
            return f"Te pidió: {what}."
        if kind == "call":
            return "They asked you to call." if origin == "prospect_request" else "You said you'd call."
        if origin == "rep_promise":
            return f"You promised to {what}."
        return f"They asked: {what}."
    if signal.type == "no_reply":
        return _no_reply(payload, lang)
    if signal.type == "going_cold":
        days = payload["days_silent"]
        if lang == "es":
            lead = "Mostró mucho interés" if payload["interest"] == "high" else "Mostró interés"
            return f"{lead} y lleváis {days} días sin hablar."
        lead = "Showed strong interest" if payload["interest"] == "high" else "Showed interest"
        return f"{lead}; {days} days without talking."
    label = CATEGORY[lang].get(payload["category"], payload["category"])
    if lang == "es":
        return f"Quedó una objeción de {label} sin cerrar."
    return f"An open {label} objection."


def priority_reason_text(
    reason: str,
    *,
    created_at,
    tz_name: str = "Europe/Madrid",
    lang: str = "es",
) -> str | None:
    """Priority-card copy for the brief. Same wording Hoy will reuse server-side."""
    lang = _lang(lang)
    if reason == "no_calls_logged":
        if created_at:
            day = _priority_day_label(created_at, tz_name)
            if day:
                return f"Nuevo, sin llamar desde el {day}" if lang == "es" else f"New, not called since {day}"
        return "Sin llamar" if lang == "es" else "Not called yet"
    if reason == "pain_agree_next_step":
        return "Confirmó el problema y falta el siguiente paso." if lang == "es" else "Confirmed the problem; next step pending."
    if reason == "followup_pending":
        return "Quedó un seguimiento pendiente." if lang == "es" else "Follow-up still pending."
    return None


def _priority_day_label(value, tz_name: str) -> str | None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        zone = ZoneInfo(str(tz_name or "Europe/Madrid"))
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("Europe/Madrid")
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
    local = parsed.astimezone(zone)
    return f"{local.day} {MONTH['es'][local.month - 1]}"


def _no_reply(payload: dict, lang: str) -> str:
    sent = date.fromisoformat(payload["email_date"])
    subject = " ".join(str(payload.get("subject") or "").split())
    if len(subject) > SUBJECT_MAX:
        subject = subject[:SUBJECT_MAX - 1].rstrip() + "…"
    if lang == "es":
        when = f"{sent.day} {MONTH['es'][sent.month - 1]}"
        quoted = f" («{subject}»)" if subject else ""
        return f"Le escribiste el {when}{quoted} y no ha respondido."
    when = f"{MONTH['en'][sent.month - 1]} {sent.day}"
    quoted = f' ("{subject}")' if subject else ""
    return f"You emailed on {when}{quoted} and got no reply."
