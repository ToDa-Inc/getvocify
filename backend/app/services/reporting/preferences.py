"""Report opt-outs. A report nobody offers this person is not a preference they can see or set."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.services.feature_flags import is_enabled

logger = logging.getLogger(__name__)

COLUMNS = {"daily": "daily_enabled", "weekly": "weekly_enabled", "team": "team_enabled"}
TEAM_ROLES = frozenset({"owner", "admin"})


def applicable_keys(supabase, *, company_id: str, role: str) -> list[str]:
    keys = ["daily"]
    if is_enabled(supabase, company_id, "REPORTING_WEEKLY_ENABLED"):
        keys.append("weekly")
    if role in TEAM_ROLES and is_enabled(supabase, company_id, "REPORTING_TEAM_ENABLED"):
        keys.append("team")
    return keys


def load_preference_rows(supabase, user_ids: list[str]) -> dict[str, dict]:
    """A failed read means defaults (everything on), the same as a person who never changed anything."""
    ids = sorted({str(uid) for uid in user_ids if uid})
    if not ids:
        return {}
    try:
        result = (
            supabase.table("report_preferences")
            .select("user_id,daily_enabled,weekly_enabled,team_enabled")
            .in_("user_id", ids)
            .execute()
        )
    except Exception:
        logger.exception("report preferences: read failed")
        return {}
    return {str(row["user_id"]): row for row in (result.data or []) if row.get("user_id")}


def is_opted_in(rows: dict[str, dict], user_id: str, key: str) -> bool:
    value = (rows.get(str(user_id)) or {}).get(COLUMNS[key])
    return True if value is None else bool(value)


def read_preferences(supabase, *, user_id: str, company_id: str, role: str) -> dict[str, bool]:
    rows = load_preference_rows(supabase, [user_id])
    return {key: is_opted_in(rows, user_id, key) for key in applicable_keys(supabase, company_id=company_id, role=role)}


def write_preferences(supabase, *, user_id: str, company_id: str, role: str, changes: dict) -> dict[str, bool]:
    keys = applicable_keys(supabase, company_id=company_id, role=role)
    unknown = [key for key in changes if key not in keys]
    if unknown:
        raise ValueError(f"preferencia no disponible: {unknown[0]}")
    if any(not isinstance(value, bool) for value in changes.values()):
        raise ValueError("las preferencias son sí o no")
    current = {key: is_opted_in(load_preference_rows(supabase, [user_id]), user_id, key) for key in COLUMNS}
    current.update(changes)
    supabase.table("report_preferences").upsert(
        {
            "user_id": user_id,
            **{COLUMNS[key]: value for key, value in current.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id",
    ).execute()
    return read_preferences(supabase, user_id=user_id, company_id=company_id, role=role)
