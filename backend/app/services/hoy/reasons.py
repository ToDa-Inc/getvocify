"""The most-read sentence in the product, written once, server-side."""
from __future__ import annotations

from datetime import datetime

from app.services.hoy.signals import Signal

CATEGORY = {
    "es": {
        "price": "precio",
        "timing": "momento",
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
