"""The most-read sentence in the product, written once, server-side."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services.hoy.signals import Signal

DEFAULT_TZ = "Europe/Madrid"

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


def reason(signal: Signal, *, lang: str = "es", lead_tiers: bool = False, now: datetime | None = None) -> str:
    """`lead_tiers` (HOY_LEAD_TIERS_ENABLED, T5) only changes going_cold's wording
    ("stale_hot" in the plan - the persisted signal.type stays going_cold). Off, the
    sentence is byte-identical to before. `now` is only read by callback_no_answer
    (review: its day count is computed at render time from the stored `at`, never
    frozen at signal-creation time) and defaults to the wall clock if omitted."""
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
    if signal.type == "meeting_today":
        # «Reunión hoy 11:00 · Marina (Acme)» is composed once in the UI (meetingCardLine) from
        # due_at, timezone and the stamped names, which are not known here.
        return ""
    if signal.type == "no_reply":
        return _no_reply(payload, lang)
    if signal.type == "callback_no_answer":
        return _callback_no_answer(payload, lang, now or datetime.now(timezone.utc))
    if signal.type == "never_contacted":
        return "Nunca has hablado con este contacto." if lang == "es" else "You have never spoken with this contact."
    if signal.type == "going_cold":
        days = payload["days_silent"]
        if lang == "es":
            lead = "Mostró mucho interés" if payload["interest"] == "high" else "Mostró interés"
            joiner = "y lleva" if lead_tiers else "y lleváis"
            return f"{lead} {joiner} {days} días sin hablar."
        lead = "Showed strong interest" if payload["interest"] == "high" else "Showed interest"
        return f"{lead}; {days} days without talking."
    if payload.get("category") == "other":
        return "Quedó una objeción sin cerrar." if lang == "es" else "An open objection."
    label = CATEGORY[lang].get(payload["category"], payload["category"])
    if lang == "es":
        return f"Quedó una objeción de {label} sin cerrar."
    return f"An open {label} objection."


def meeting_detail(payload: dict, *, lang: str = "es", tz_name: str | None = None) -> str | None:
    """When the meeting was accepted, on the rep's calendar, not when it starts. We do not know CRM moves."""
    raw = payload.get("accepted_at")
    if not raw:
        return None
    try:
        accepted = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if accepted.tzinfo is None:
        accepted = accepted.replace(tzinfo=timezone.utc)
    local = accepted.astimezone(ZoneInfo(tz_name or DEFAULT_TZ))
    lang = _lang(lang)
    if lang == "es":
        return f"acordada el {local.day} {MONTH['es'][local.month - 1]}"
    return f"agreed on {MONTH['en'][local.month - 1]} {local.day}"


def _callback_no_answer(payload: dict, lang: str, now: datetime) -> str:
    at = _as_dt(payload.get("at"))
    days = max(0, (now.date() - at.date()).days) if at else 0
    voicemail = payload.get("outcome") == "voicemail"
    if lang == "es":
        verb = "Le dejaste un mensaje de voz" if voicemail else "Le llamaste"
        return f"{verb} hace {days} días y no contestó."
    verb = "You left a voicemail" if voicemail else "You called"
    return f"{verb} {days} days ago and they did not pick up."


def _as_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
