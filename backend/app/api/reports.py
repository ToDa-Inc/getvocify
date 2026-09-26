"""Report reads. A personal report stays with its owner. The stored snapshot is not recomputed."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.reporting.activity import load_vocify_activity
from app.services.reporting.preferences import TEAM_ROLES, read_preferences, write_preferences

router = APIRouter(prefix="/api/v1", tags=["reports"])

BELL_LIMIT = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def can_read_report(row: dict, *, user_id: str, company_id: str, role: str) -> bool:
    """Personal: only its owner. Team: only its recipient, and only while still owner/admin here."""
    if row.get("company_id") != company_id:
        return False
    if row.get("scope") == "self":
        return row.get("user_id") == user_id
    return row.get("user_id") == user_id and role in TEAM_ROLES


def public_report(row: dict) -> dict:
    return {
        "id": row["id"],
        "revision": row["revision"],
        "scope": row["scope"],
        "period_start": row["period_start"],
        "report_type": row["report_type"],
        "snapshot": row["snapshot"],
    }


@router.get("/me/report-preferences")
async def get_report_preferences(
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    return read_preferences(
        supabase, user_id=membership.user_id, company_id=membership.company_id, role=membership.role,
    )


@router.put("/me/report-preferences")
async def put_report_preferences(
    changes: dict = Body(...),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    try:
        return write_preferences(
            supabase,
            user_id=membership.user_id,
            company_id=membership.company_id,
            role=membership.role,
            changes=changes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    stored = supabase.table("reports").select("*").eq("id", report_id).execute()
    rows = stored.data or []
    if not rows or not can_read_report(
        rows[0],
        user_id=membership.user_id,
        company_id=membership.company_id,
        role=membership.role,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Informe no encontrado")
    return public_report(rows[0])


def bell_items(rows: list[dict], user_id: str) -> dict:
    """Unread rows for this person. A read row does not count. Another user's row is absent."""
    own = [row for row in rows if row.get("user_id") == user_id and not row.get("read_at")]
    return {
        "unread": len(own),
        "items": [{"id": row.get("id"), "report_id": row.get("report_id")} for row in own],
    }


def _period_key(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _visible_in_bell(report: dict, membership: Membership, flags: dict[str, bool]) -> bool:
    if not can_read_report(
        report, user_id=membership.user_id, company_id=membership.company_id, role=membership.role,
    ):
        return False
    if report.get("scope") == "team":
        return flags["REPORTING_TEAM_ENABLED"]
    if report.get("report_type") == "weekly":
        return flags["REPORTING_WEEKLY_ENABLED"]
    return True


def mark_notification_read(row: dict, *, user_id: str, now: datetime) -> dict:
    if row.get("user_id") != user_id:
        raise PermissionError("notificación ajena")
    if row.get("read_at"):
        return row
    return {**row, "read_at": now.isoformat()}


notifications = APIRouter(prefix="/api/v1", tags=["notifications"])


@notifications.get("/notifications")
async def list_notifications(
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """Reports this person may still read, newest first. What Vocify did rides along, outside the count."""
    flags = {
        name: is_enabled(supabase, membership.company_id, name)
        for name in ("REPORTING_WEEKLY_ENABLED", "REPORTING_TEAM_ENABLED", "NOTIFICATIONS_ACTIVITY_ENABLED")
    }
    body: dict = {"unread": None, "items": []}
    try:
        notes = (
            supabase.table("report_notifications")
            .select("id,report_id,user_id,read_at")
            .eq("user_id", membership.user_id)
            .execute()
        ).data or []
        report_ids = sorted({str(note["report_id"]) for note in notes if note.get("report_id")})
        reports: list[dict] = []
        if report_ids:
            reports = (
                supabase.table("reports")
                .select("id,company_id,user_id,scope,period_start,report_type")
                .in_("id", report_ids)
                .execute()
            ).data or []
    except Exception:
        notes = None
    if notes is not None:
        by_id = {str(report["id"]): report for report in reports}
        items = []
        for note in notes:
            report = by_id.get(str(note.get("report_id")))
            if note.get("user_id") != membership.user_id or not report:
                continue
            if not _visible_in_bell(report, membership, flags):
                continue
            items.append({
                "id": note.get("id"),
                "report_id": str(report["id"]),
                "report_type": report.get("report_type"),
                "scope": report.get("scope"),
                "period_start": _period_key(report.get("period_start")),
                "read_at": note.get("read_at"),
            })
        items.sort(key=lambda item: item["period_start"], reverse=True)
        body = {"unread": sum(1 for item in items if not item["read_at"]), "items": items[:BELL_LIMIT]}
    if flags["NOTIFICATIONS_ACTIVITY_ENABLED"]:
        body["activity"] = load_vocify_activity(
            supabase, user_id=membership.user_id, company_id=membership.company_id, now=_now(),
        )
    return body


@notifications.patch("/notifications/{notification_id}")
async def read_notification(
    notification_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    stored = supabase.table("report_notifications").select("*").eq("id", notification_id).execute()
    rows = stored.data or []
    if not rows or rows[0].get("user_id") != membership.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada")
    updated = mark_notification_read(rows[0], user_id=membership.user_id, now=datetime.now(timezone.utc))
    if updated.get("read_at") != rows[0].get("read_at"):
        saved = (
            supabase.table("report_notifications")
            .update({"read_at": updated["read_at"]})
            .eq("id", notification_id)
            .eq("user_id", membership.user_id)
            .execute()
        )
        if saved.data:
            updated = saved.data[0]
    return {"id": updated["id"], "read_at": updated.get("read_at")}
