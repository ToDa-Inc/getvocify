"""One report per person and period. A failed email keeps the notification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def period_bounds(now: datetime, tz_name: str) -> tuple[datetime, datetime]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(tz_name))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def claim_report_statement(*, company_id: str, user_id: str, scope: str, period_start: str, report_type: str) -> str:
    return (
        "INSERT INTO reports (id, company_id, user_id, scope, period_start, report_type, revision, snapshot) "
        f"VALUES (gen_random_uuid()::text, '{company_id}', '{user_id}', '{scope}', '{period_start}', '{report_type}', 1, '{{}}'::jsonb) "
        "ON CONFLICT (company_id, user_id, scope, period_start, report_type) DO NOTHING;"
    )


def send_report_email(report: dict, sender, *, existing: dict | None = None) -> dict:
    """Production email path: deliver_report with channel email and delivery allowed."""
    return deliver_report(report=report, channel="email", existing=existing, sender=sender, allowed=True)


def persist_report_delivery(
    supabase,
    *,
    idempotency_key: str,
    report_id: str,
    channel: str,
    delivery_status: str,
    last_attempt_at: datetime | None = None,
) -> None:
    """Upsert one row in report_deliveries (survives process restarts)."""
    attempt = last_attempt_at or datetime.now(timezone.utc)
    if attempt.tzinfo is None:
        attempt = attempt.replace(tzinfo=timezone.utc)
    supabase.table("report_deliveries").upsert(
        {
            "idempotency_key": idempotency_key,
            "report_id": report_id,
            "channel": channel,
            "delivery_status": delivery_status,
            "last_attempt_at": attempt.isoformat(),
        },
        on_conflict="idempotency_key",
    ).execute()


def deliver_report(*, report: dict, channel: str, existing: dict | None, sender, allowed: bool) -> dict:
    key = f"{report['id']}:r{report['revision']}:{channel}"
    notification = {"report_id": report["id"], "kept": True}
    if not allowed:
        return {"delivery_status": "skipped", "idempotency_key": key, "notification": notification, "sent": False}
    if existing and existing.get("idempotency_key") == key and existing.get("delivery_status") == "sent":
        return {**existing, "notification": notification, "replayed": True, "sent": False}
    if existing and existing.get("delivery_status") == "uncertain":
        found = sender.reconcile(key)
        if found:
            return {"delivery_status": "sent", "idempotency_key": key, "notification": notification, "replayed": True, "sent": False}
    try:
        sender.send(key)
    except TimeoutError:
        return {"delivery_status": "uncertain", "idempotency_key": key, "notification": notification, "replayed": False, "sent": False}
    except Exception:
        return {"delivery_status": "failed", "idempotency_key": key, "notification": notification, "replayed": False, "sent": False}
    return {"delivery_status": "sent", "idempotency_key": key, "notification": notification, "replayed": False, "sent": True}
