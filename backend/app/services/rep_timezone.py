"""The rep's zone: their brief preference, Madrid when they have none or it cannot be read."""

from __future__ import annotations

from typing import Any

from app.services.coaching.brief_preferences import read_preference

DEFAULT_TZ = "Europe/Madrid"


def rep_timezone(user_id: Any) -> str:
    if not user_id:
        return DEFAULT_TZ
    try:
        tz = read_preference(str(user_id)).get("timezone")
    except Exception:
        return DEFAULT_TZ
    return str(tz) if tz else DEFAULT_TZ
