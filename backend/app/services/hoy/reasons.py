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


# Lista 4 T2: the stopper behind a followup_due, as a short clause ("frenó por precio").
STOPPER = {
    "es": {
        "price": "frenó por precio",
        "timing": "frenó por el momento",
        "authority": "frenó por el decisor",
        "competitor": "frenó por la competencia",
        "status_quo": "frenó por el statu quo",
        "trust": "frenó por confianza",
        "other": "quedó una objeción abierta",
        "interest_high": "interés alto, sin siguiente paso",
        "interest_medium": "interés medio, sin siguiente paso",
        "interest_low": "interés bajo",
    },
    "en": {
        "price": "stalled on price",
        "timing": "stalled on timing",
        "authority": "stalled on the decision-maker",
        "competitor": "stalled on a competitor",
        "status_quo": "stalled on the status quo",
        "trust": "stalled on trust",
        "other": "an objection stayed open",
        "interest_high": "high interest, no next step",
        "interest_medium": "medium interest, no next step",
        "interest_low": "low interest",
    },
}
FOLLOWUP_LABEL = {"es": "Seguimiento", "en": "Follow-up"}


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
    if signal.type == "followup_due":
        return _followup_due(payload, lang, now or datetime.now(timezone.utc))
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


def followup_upcoming_text(stopper: str | None, lang: str = "es") -> str:
    """Próximos' line for a follow-up not due yet: «Seguimiento · frenó por precio»."""
    lang = _lang(lang)
    clause = STOPPER[lang].get(stopper or "")
    return f"{FOLLOWUP_LABEL[lang]} · {clause}" if clause else FOLLOWUP_LABEL[lang]


def _ago(days: int, lang: str) -> str:
    if lang == "es":
        return "hace 1 día" if days == 1 else f"hace {days} días"
    return "1 day ago" if days == 1 else f"{days} days ago"


def _followup_due(payload: dict, lang: str, now: datetime) -> str:
    """Worded by the stopper; the day count is read off `touch_at` at render time."""
    at = _as_dt(payload.get("touch_at"))
    days = max(0, (now.date() - at.date()).days) if at else int(payload.get("days_since") or 0)
    ago = _ago(days, lang)
    interest = payload.get("interest")
    stopper = payload.get("stopper") or ""
    if interest not in ("high", "medium", "low"):
        # Only a date the rep picked brings back a contact of unknown or no interest.
        return "Quedaste en volver a llamarle." if lang == "es" else "You planned to call them back."
    if stopper.startswith("interest_") or stopper not in STOPPER[lang]:
        if lang == "es":
            lead = {"high": "Mostró mucho interés", "medium": "Mostró interés", "low": "Mostró poco interés"}[interest]
            return f"{lead} {ago}, sin siguiente paso."
        lead = {"high": "Showed strong interest", "medium": "Showed interest", "low": "Showed little interest"}[interest]
        return f"{lead} {ago}, no next step."
    if lang == "es":
        lead = {"high": "Le interesó", "medium": "Le interesó", "low": "Mostró poco interés"}[interest]
    else:
        lead = {"high": "Was interested", "medium": "Was interested", "low": "Showed little interest"}[interest]
    return f"{lead}; {STOPPER[lang][stopper]} ({ago})."


def _callback_no_answer(payload: dict, lang: str, now: datetime) -> str:
    """`outcome` "voicemail" is how the call ended (the voicemail picked up), not a message the
    rep left: Vocify does not know that, so it never says it."""
    at = _as_dt(payload.get("at"))
    days = max(0, (now.date() - at.date()).days) if at else 0
    voicemail = payload.get("outcome") == "voicemail"
    bad_moment = payload.get("outcome") == "bad_moment"
    cut_off = payload.get("outcome") == "cut_off"
    if lang == "es":
        when = "hoy" if days == 0 else "ayer" if days == 1 else f"hace {days} días"
        if cut_off:
            return f"Se cortó la llamada {when}. Vuelve a llamar."
        if bad_moment:
            return f"Le llamaste {when} y no podía hablar. Vuelve a intentarlo."
        if voicemail:
            return f"Saltó el buzón de voz {when}. Vuelve a llamar."
        return f"Le llamaste {when} y no contestó."
    when = "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
    if cut_off:
        return f"The call dropped {when}. Call again."
    if bad_moment:
        return f"You called {when} and they could not talk. Try again."
    if voicemail:
        return f"It went to voicemail {when}. Call again."
    return f"You called {when} and they did not pick up."


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
