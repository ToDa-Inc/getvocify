"""Resolve spoken follow-up timing against the call date, not the model calendar."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Optional

_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_MONTHS = {
    "enero": 1, "january": 1,
    "febrero": 2, "february": 2,
    "marzo": 3, "march": 3,
    "abril": 4, "april": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "june": 6,
    "julio": 7, "july": 7,
    "agosto": 8, "august": 8,
    "septiembre": 9, "setiembre": 9, "sept": 9, "sep": 9, "september": 9,
    "octubre": 10, "october": 10,
    "noviembre": 11, "november": 11,
    "diciembre": 12, "december": 12,
}
_WEEKDAY = {
    "lunes": 0, "monday": 0,
    "martes": 1, "tuesday": 1,
    "miercoles": 2, "miércoles": 2, "wednesday": 2,
    "jueves": 3, "thursday": 3,
    "viernes": 4, "friday": 4,
    "sabado": 5, "sábado": 5, "saturday": 5,
    "domingo": 6, "sunday": 6,
}


def _fold(text: str) -> str:
    raw = (text or "").strip().lower()
    repl = str.maketrans("áéíóúü", "aeiouu")
    return raw.translate(repl)


def _add_months(ref: date, months: int) -> date:
    month = ref.month - 1 + months
    year = ref.year + month // 12
    month = month % 12 + 1
    day = min(ref.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_day_of_month(ref: date, day: int) -> date:
    """The day-of-month on or after `ref`, allowing the current week to go slightly backward."""
    day = max(1, min(31, int(day)))
    this = date(ref.year, ref.month, min(day, calendar.monthrange(ref.year, ref.month)[1]))
    if this >= ref - timedelta(days=3):
        return this
    nxt = _add_months(ref.replace(day=1), 1)
    return nxt.replace(day=min(day, calendar.monthrange(nxt.year, nxt.month)[1]))


def _date_for_month_day(ref: date, month: int, day: int) -> date:
    last = calendar.monthrange(ref.year, month)[1]
    candidate = date(ref.year, month, min(day, last))
    if candidate + timedelta(days=3) < ref:
        last_n = calendar.monthrange(ref.year + 1, month)[1]
        return date(ref.year + 1, month, min(day, last_n))
    return candidate


def resolve_schedule(text: str, ref: date) -> Optional[str]:
    """ISO YYYY-MM-DD from a spoken schedule, or None if nothing resolvable.

    Day-of-month wins over weekday. Weekday never changes an explicit day.
    """
    if ref is None:
        return None
    raw = (text or "").strip()
    if not raw:
        return None
    iso = _ISO.match(raw)
    if iso:
        return iso.group(1)
    blob = _fold(raw)

    named = re.search(
        r"(\d{1,2})(?:\s+y pico)?\s+(?:de\s+)?([a-z]+)",
        blob,
    )
    if named and named.group(2) in _MONTHS:
        month = _MONTHS[named.group(2)]
        day = int(named.group(1))
        return _date_for_month_day(ref, month, day).isoformat()

    week = re.search(r"semana del\s+(\d{1,2})", blob)
    day_only = re.search(r"\b(?:el|dia|día)\s+(\d{1,2})\b", blob)
    if not day_only:
        day_only = re.search(r"\b(\d{1,2})\s+en adelante\b", blob)
    if week:
        week_start = next_day_of_month(ref, int(week.group(1)))
        if day_only:
            day = int(day_only.group(1))
            return week_start.replace(day=min(day, calendar.monthrange(week_start.year, week_start.month)[1])).isoformat()
        return week_start.isoformat()
    if day_only:
        return next_day_of_month(ref, int(day_only.group(1))).isoformat()

    if re.search(r"\ben un mes\b|\bin a month\b|\bmes que viene\b|\bnext month\b", blob):
        return _add_months(ref, 1).isoformat()
    if re.search(r"\ben una semana\b|\bin a week\b|\bsemana que viene\b|\bnext week\b", blob):
        return (ref + timedelta(days=7)).isoformat()

    for name, wd in _WEEKDAY.items():
        if re.search(rf"\b(?:proximo|proxima|next)\s+{name}\b", blob) or re.search(
            rf"\b{name}\s+que viene\b", blob
        ):
            delta = (wd - ref.weekday()) % 7
            if delta == 0:
                delta = 7
            return (ref + timedelta(days=delta)).isoformat()
    return None


def resolve_schedules(items: list, ref: Optional[date]) -> list:
    """Map nextStepSchedules in place; leave unresolvable phrases as-is."""
    if not items or ref is None:
        return list(items or [])
    out = []
    for item in items:
        if not isinstance(item, str):
            out.append(item)
            continue
        resolved = resolve_schedule(item, ref)
        out.append(resolved if resolved else item)
    return out


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    m = _ISO.match(str(value).strip())
    if not m:
        return None
    y, mo, d = m.group(1).split("-")
    try:
        return date(int(y), int(mo), int(d))
    except ValueError:
        return None


def call_date_header(call_date: Optional[date], today: Optional[date] = None) -> str:
    if call_date is None:
        return ""
    today = today or date.today()
    weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[
        call_date.weekday()
    ]
    return (
        f"### CALL DATE\n"
        f"This call happened on {call_date.isoformat()} ({weekday}). "
        f"Today is {today.isoformat()}. "
        f"Resolve relative dates (semana del 24, el 26, en un mes, 20 y pico de septiembre) "
        f"against the CALL DATE. A weekday must never override an explicit day-of-month.\n"
    )
