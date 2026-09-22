"""Supabase loaders and sender wiring for the report email tick."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.config import settings
from app.services.reporting.delivery import persist_report_delivery
from app.services.reporting.due_sends import MADRID
from app.services.reporting.resend_sender import report_resend_sender


@dataclass(frozen=True)
class ReportEmailTickBindings:
    load_people: Callable[[], list[dict]]
    load_existing: Callable[[], list[dict]]
    sender: Any | None
    persist_delivery: Callable[[dict, dict], None] | None


def report_email_tick_bindings(supabase) -> ReportEmailTickBindings:
    """Production bindings. No Resend key → sender is None (tick skips send)."""
    return ReportEmailTickBindings(
        load_people=lambda: _load_daily_report_people(supabase),
        load_existing=lambda: _load_report_delivery_existing(supabase),
        sender=_build_sender(supabase),
        persist_delivery=lambda result, person, now=None: _persist_delivery_row(supabase, result, person, now=now),
    )


def _build_sender(supabase):
    if not (settings.RESEND_API_KEY or "").strip():
        return None
    from app.integrations.resend_client import ResendClient

    client = ResendClient()
    return _ReportIdSender(client)


class _ReportIdSender:
    """Routes each idempotency key to a per-recipient Resend sender."""

    def __init__(self, resend_client):
        self._client = resend_client
        self._by_report: dict[str, Any] = {}
        self._email_by_report: dict[str, str] = {}

    def set_recipients(self, people: list[dict]) -> None:
        self._email_by_report = {
            str(person["report_id"]): str(person["email"]).strip()
            for person in people
            if person.get("email") and str(person["email"]).strip()
        }

    def _sender_for(self, report_id: str):
        if report_id in self._by_report:
            return self._by_report[report_id]
        email = self._email_by_report.get(report_id)
        if not email:
            return None
        wrapped = report_resend_sender(
            self._client,
            to=email,
            subject="Tu resumen de actividad",
            html="<p>Consulta el informe en Vocify.</p>",
        )
        if wrapped is None:
            return None
        self._by_report[report_id] = wrapped
        return wrapped

    def send(self, key: str) -> None:
        report_id = key.split(":", 1)[0]
        sender = self._sender_for(report_id)
        if sender is None:
            raise RuntimeError(f"no recipient sender for report {report_id}")
        sender.send(key)

    def reconcile(self, key: str):
        report_id = key.split(":", 1)[0]
        sender = self._sender_for(report_id)
        if sender is None:
            return None
        return sender.reconcile(key)


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
    email_by_user = _emails_for_user_ids(supabase, user_ids)
    people: list[dict] = []
    for row in rows:
        uid = row["user_id"]
        person = {
            "user_id": uid,
            "company_id": row["company_id"],
            "timezone": tz_by_user.get(uid, MADRID),
            "report_id": row["id"],
            "revision": row.get("revision") or 1,
        }
        email = email_by_user.get(str(uid)) or email_by_user.get(uid)
        if email:
            person["email"] = email
        people.append(person)
    return people


def _emails_for_user_ids(supabase, user_ids: list) -> dict[str, str]:
    if not user_ids:
        return {}
    try:
        result = (
            supabase.postgrest.schema("auth")
            .from_("users")
            .select("id,email")
            .in_("id", [str(uid) for uid in user_ids])
            .execute()
        )
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in result.data or []:
        email = (row.get("email") or "").strip()
        if email:
            out[str(row["id"])] = email
    return out


def _persist_delivery_row(supabase, result: dict, person: dict, *, now: datetime | None = None) -> None:
    key = result.get("idempotency_key")
    if not key:
        return
    persist_report_delivery(
        supabase,
        idempotency_key=key,
        report_id=str(person["report_id"]),
        channel="email",
        delivery_status=str(result.get("delivery_status") or "sent"),
        attempt_at=now,
    )


def _load_report_delivery_existing(supabase) -> list[dict]:
    stored = (
        supabase.table("report_deliveries")
        .select("idempotency_key,report_id,delivery_status,channel,created_at")
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
                "created_at": delivery.get("created_at"),
            }
        )
    return existing
