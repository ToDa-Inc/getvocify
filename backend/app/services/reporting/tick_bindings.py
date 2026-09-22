"""Supabase loaders and sender wiring for the report email tick."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.config import settings
from app.services.reporting.due_sends import MADRID
from app.services.reporting.resend_sender import report_resend_sender


@dataclass(frozen=True)
class ReportEmailTickBindings:
    load_people: Callable[[], list[dict]]
    load_existing: Callable[[], list[dict]]
    sender: Any | None


def report_email_tick_bindings(supabase) -> ReportEmailTickBindings:
    """Production bindings. No Resend key → sender is None (tick skips send)."""
    return ReportEmailTickBindings(
        load_people=lambda: _load_daily_report_people(supabase),
        load_existing=lambda: _load_report_delivery_existing(supabase),
        sender=_build_sender(supabase),
    )


def _build_sender(supabase):
    if not (settings.RESEND_API_KEY or "").strip():
        return None
    from app.integrations.resend_client import ResendClient

    client = ResendClient()
    return _ReportIdSender(client, supabase)


class _ReportIdSender:
    """Routes each idempotency key to a per-recipient Resend sender."""

    def __init__(self, resend_client, supabase):
        self._client = resend_client
        self._supabase = supabase
        self._by_report: dict[str, Any] = {}

    def _sender_for(self, report_id: str):
        if report_id in self._by_report:
            return self._by_report[report_id]
        row = (
            self._supabase.table("reports")
            .select("id,user_id")
            .eq("id", report_id)
            .limit(1)
            .execute()
        )
        rows = row.data or []
        if not rows:
            raise RuntimeError(f"report {report_id} missing for delivery")
        user_id = rows[0]["user_id"]
        profile = (
            self._supabase.table("user_profiles")
            .select("id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if not profile.data:
            raise RuntimeError(f"profile missing for report recipient {user_id}")
        auth = self._supabase.auth.admin.get_user_by_id(str(user_id))
        email = getattr(getattr(auth, "user", None), "email", None) if auth else None
        if not email:
            raise RuntimeError(f"email missing for report recipient {user_id}")
        wrapped = report_resend_sender(
            self._client,
            to=email,
            subject="Tu resumen de actividad",
            html="<p>Consulta el informe en Vocify.</p>",
        )
        if wrapped is None:
            raise RuntimeError("report_resend_sender unavailable")
        self._by_report[report_id] = wrapped
        return wrapped

    def send(self, key: str) -> None:
        report_id = key.split(":", 1)[0]
        self._sender_for(report_id).send(key)

    def reconcile(self, key: str):
        report_id = key.split(":", 1)[0]
        try:
            return self._sender_for(report_id).reconcile(key)
        except RuntimeError:
            return None


def _load_daily_report_people(supabase) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    stored = (
        supabase.table("reports")
        .select("id,user_id,company_id,revision,period_start")
        .eq("report_type", "daily")
        .eq("scope", "self")
        .gte("period_start", since)
        .execute()
    )
    rows = stored.data or []
    if not rows:
        return []
    user_ids = list({row["user_id"] for row in rows})
    prefs = (
        supabase.table("brief_preferences")
        .select("user_id,timezone")
        .in_("user_id", user_ids)
        .execute()
    )
    tz_by_user = {row["user_id"]: row.get("timezone") or MADRID for row in (prefs.data or [])}
    people: list[dict] = []
    for row in rows:
        people.append(
            {
                "user_id": row["user_id"],
                "company_id": row["company_id"],
                "timezone": tz_by_user.get(row["user_id"], MADRID),
                "report_id": row["id"],
                "revision": row.get("revision") or 1,
            }
        )
    return people


def _load_report_delivery_existing(supabase) -> list[dict]:
    stored = (
        supabase.table("report_deliveries")
        .select("idempotency_key,report_id,delivery_status,channel")
        .eq("channel", "email")
        .execute()
    )
    deliveries = stored.data or []
    if not deliveries:
        return []
    report_ids = list({row["report_id"] for row in deliveries})
    reports = (
        supabase.table("reports")
        .select("id,user_id,period_start")
        .in_("id", report_ids)
        .execute()
    )
    by_id = {row["id"]: row for row in (reports.data or [])}
    existing: list[dict] = []
    for delivery in deliveries:
        report = by_id.get(delivery["report_id"])
        if not report:
            continue
        period_start = report.get("period_start")
        if hasattr(period_start, "isoformat"):
            period_start = period_start.isoformat()
        existing.append(
            {
                "user_id": report["user_id"],
                "period_start": period_start,
                "delivery_status": delivery.get("delivery_status"),
                "idempotency_key": delivery.get("idempotency_key"),
            }
        )
    return existing
