"""confirm_pending card text, rendered from the stored parts in the rep's language and zone."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Madrid"

MONTH = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
WEEKDAY = {
    "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
_COPY = {
    "es": {"prefix": "Confirma:", "meeting": "reunión {when} con {who}", "someone": "el contacto",
           "stage": "etapa → {label}", "failed": "No se pudo guardar en el CRM. Vuelve a confirmar o revísala."},
    "en": {"prefix": "Confirm:", "meeting": "meeting {when} with {who}", "someone": "the contact",
           "stage": "stage → {label}", "failed": "Could not save to the CRM. Confirm again or review it."},
}


def _lang(lang: Optional[str]) -> str:
    return "en" if (lang or "").lower().startswith("en") else "es"


def _when(starts_at: str, *, lang: str, tz_name: str) -> Optional[str]:
    try:
        parsed = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        local = parsed.astimezone(ZoneInfo(tz_name or DEFAULT_TZ))
    except (ValueError, KeyError):
        return None
    return f"{WEEKDAY[lang][local.weekday()]} {local.day} {MONTH[lang][local.month - 1]}, {local:%H:%M}"


def confirm_reason(payload: dict[str, Any], *, lang: str = "es", tz_name: str = DEFAULT_TZ) -> str:
    """«Confirma: reunión jue 1 oct, 11:00 con Marina · etapa → Meeting booked», only the parts present."""
    lang = _lang(lang)
    copy = _COPY[lang]
    parts: list[str] = []
    meeting = payload.get("meeting") if isinstance(payload.get("meeting"), dict) else None
    starts_at = (meeting or {}).get("starts_at")
    when = _when(starts_at, lang=lang, tz_name=tz_name) if isinstance(starts_at, str) and starts_at else None
    if when:
        who = str(payload.get("contact_name") or "").strip() or copy["someone"]
        parts.append(copy["meeting"].format(when=when, who=who))
    stage = payload.get("stage") if isinstance(payload.get("stage"), dict) else None
    label = str((stage or {}).get("stage_label") or (stage or {}).get("stage_id") or "").strip()
    if label:
        parts.append(copy["stage"].format(label=label))
    return " ".join([copy["prefix"], " · ".join(parts)]) if parts else copy["prefix"]


def failed_detail(lang: str = "es") -> str:
    return _COPY[_lang(lang)]["failed"]
