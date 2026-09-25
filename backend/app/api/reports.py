"""Report reads. A personal report stays with its owner. The stored snapshot is not recomputed."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_membership, get_supabase
from app.services.company import Membership

router = APIRouter(prefix="/api/v1", tags=["reports"])


def can_read_report(row: dict, *, user_id: str, company_id: str, role: str) -> bool:
    if row.get("company_id") != company_id:
        return False
    if row.get("scope") == "self":
        return row.get("user_id") == user_id
    return role in {"owner", "admin"}


def public_report(row: dict) -> dict:
    return {
        "id": row["id"],
        "revision": row["revision"],
        "scope": row["scope"],
        "period_start": row["period_start"],
        "report_type": row["report_type"],
        "snapshot": row["snapshot"],
    }


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
    try:
        stored = (
            supabase.table("report_notifications")
            .select("id,report_id,user_id,read_at")
            .eq("user_id", membership.user_id)
            .execute()
        )
    except Exception:
        return {"unread": None, "items": []}
    return bell_items(stored.data or [], membership.user_id)


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
