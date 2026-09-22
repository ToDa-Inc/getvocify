"""Scope a priority snapshot to one person. Another owner's row never becomes an empty list."""

from __future__ import annotations

import json
from datetime import datetime

from app.services.hoy.priority import empty_priority_copy, rank_candidates


def build_priority_page(
    *,
    snapshot: dict,
    user_id: str,
    role: str,
    now: datetime,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    connected = bool(snapshot.get("connected"))
    coverage = snapshot.get("coverage") or "unavailable"
    observed_at = snapshot.get("observed_at")
    if not connected:
        copy = empty_priority_copy(connected=False, coverage=coverage, role=role)
        return {
            "items": [],
            "coverage": "unavailable",
            "observed_at": None,
            "next_cursor": None,
            "stale": False,
            **copy,
        }

    visible = []
    for row in snapshot.get("candidates") or []:
        if row.get("owner_ambiguous"):
            continue
        owner = row.get("owner_user_id")
        if owner and owner != user_id:
            continue
        visible.append(row)

    ranked = rank_candidates(visible, now)
    if cursor:
        ranked = [row for row in ranked if row["id"] > cursor]
    page = ranked[:limit]
    next_cursor = page[-1]["id"] if len(ranked) > limit else None
    if page and coverage != "complete":
        copy = {"title": "Falta parte del historial", "action": "Reintentar"}
    elif page:
        copy = {"title": None, "action": None}
    else:
        copy = empty_priority_copy(
            connected=True,
            coverage=coverage,
            role=role,
            assigned=snapshot.get("assigned", True),
        )
    return {
        "items": page,
        "coverage": coverage,
        "observed_at": observed_at,
        "next_cursor": next_cursor,
        "stale": False,
        **copy,
    }


def resolve_owner(email: str | None, members: list[dict]) -> tuple[str | None, bool]:
    """Exact email only. Two members with the same email stay unresolved. A matching name does not count."""
    if not email:
        return None, False
    needle = email.strip().lower()
    matches = [member for member in members if str(member.get("email") or "").strip().lower() == needle]
    if len(matches) == 1:
        return str(matches[0]["user_id"]), False
    if len(matches) > 1:
        return None, True
    return None, False


def fold_context(*, company_id: str, pages: list[dict], members: list[dict], previous: list[dict] | None = None) -> list[dict]:
    stored = { _row_key(row): dict(row) for row in previous or [] }
    for page in pages:
        connection_id = page["connection_id"]
        if page.get("coverage") in {"forbidden", "unavailable"} and not page.get("items"):
            for key, row in list(stored.items()):
                if row["connection_id"] == connection_id:
                    stored[key] = {**row, "coverage": page["coverage"], "history_complete": False}
            continue
        history_complete = page.get("coverage") == "complete" and not page.get("next_cursor")
        for item in page.get("items") or []:
            owner_id, ambiguous = resolve_owner(item.get("owner_email"), members)
            deal_id = item.get("deal_id") or ""
            payload = {
                key: value
                for key, value in item.items()
                if key not in {"connection_id", "object_type"}
            }
            stored[(connection_id, str(item["contact_id"]), deal_id)] = {
                "company_id": company_id,
                "connection_id": connection_id,
                "contact_id": str(item["contact_id"]),
                "deal_id": deal_id,
                "owner_user_id": owner_id,
                "owner_ambiguous": ambiguous,
                "coverage": page["coverage"],
                "history_complete": history_complete,
                "observed_at": page.get("observed_at"),
                "payload": payload,
            }
    return list(stored.values())


def invalidate_context(rows: list[dict], reason: str) -> list[dict]:
    updated = []
    for row in rows:
        payload = dict(row.get("payload") or {})
        payload["stale_reason"] = reason
        coverage = "partial" if row.get("coverage") == "complete" else row.get("coverage")
        updated.append({**row, "coverage": coverage, "history_complete": False, "payload": payload})
    return updated


def snapshot_from_rows(rows: list[dict], *, connected: bool) -> dict:
    if not connected:
        return {"connected": False, "coverage": "unavailable", "candidates": [], "observed_at": None}
    if not rows:
        return {"connected": True, "coverage": "complete", "assigned": False, "candidates": [], "observed_at": None}
    coverages = {row.get("coverage") for row in rows}
    if coverages == {"complete"} and all(row.get("history_complete") for row in rows):
        coverage = "complete"
    elif coverages <= {"unavailable"}:
        coverage = "unavailable"
    elif coverages <= {"forbidden"}:
        coverage = "forbidden"
    else:
        coverage = "partial"
    candidates = []
    for row in rows:
        deal_id = row.get("deal_id") or None
        candidates.append({
            **(row.get("payload") or {}),
            "connection_id": row["connection_id"],
            "contact_id": row["contact_id"],
            "deal_id": deal_id,
            "owner_user_id": row.get("owner_user_id"),
            "owner_ambiguous": row.get("owner_ambiguous"),
            "coverage": "partial" if not row.get("history_complete") and row.get("coverage") == "complete" else row.get("coverage"),
            "observed_at": row.get("observed_at"),
        })
    observed = [row.get("observed_at") for row in rows if row.get("observed_at")]
    return {
        "connected": True,
        "coverage": coverage,
        "assigned": any(row.get("owner_user_id") or row.get("owner_ambiguous") for row in rows),
        "candidates": candidates,
        "observed_at": max(observed) if observed else None,
    }


def _row_key(row: dict) -> tuple[str, str, str]:
    return (row["connection_id"], str(row["contact_id"]), row.get("deal_id") or "")


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def load_context(supabase, company_id: str) -> tuple[bool, list[dict]]:
    """A company is connected only when a CRM row is status=connected. Expired tokens are not an empty list."""
    connections = (
        supabase.table("crm_connections")
        .select("id,status,company_id")
        .eq("company_id", company_id)
        .execute()
    )
    connected = any(row.get("status") == "connected" for row in (connections.data or []))
    if not connected:
        return False, []
    stored = (
        supabase.table("contact_priority_context")
        .select("*")
        .eq("company_id", company_id)
        .execute()
    )
    return True, list(stored.data or [])


def upsert_statements(rows: list[dict]) -> str:
    if not rows:
        return ""
    values = []
    for row in rows:
        values.append(
            "("
            + ", ".join(
                [
                    _sql_literal(row["company_id"]),
                    _sql_literal(row["connection_id"]),
                    _sql_literal(row["contact_id"]),
                    _sql_literal(row.get("deal_id") or ""),
                    _sql_literal(row.get("owner_user_id")),
                    _sql_literal(bool(row.get("owner_ambiguous"))),
                    _sql_literal(row["coverage"]),
                    _sql_literal(bool(row.get("history_complete"))),
                    _sql_literal(row.get("observed_at")),
                    _sql_literal(row.get("payload") or {}),
                ]
            )
            + ")"
        )
    return (
        "INSERT INTO contact_priority_context "
        "(company_id, connection_id, contact_id, deal_id, owner_user_id, owner_ambiguous, coverage, history_complete, observed_at, payload) "
        "VALUES "
        + ", ".join(values)
        + " ON CONFLICT (company_id, connection_id, contact_id, deal_id) DO UPDATE SET "
        "owner_user_id = EXCLUDED.owner_user_id, "
        "owner_ambiguous = EXCLUDED.owner_ambiguous, "
        "coverage = EXCLUDED.coverage, "
        "history_complete = EXCLUDED.history_complete, "
        "observed_at = EXCLUDED.observed_at, "
        "payload = EXCLUDED.payload;"
    )
