"""F13: daily report email is due after 18:00 local; sent periods are not resent."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-due-sends-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-due-sends-32")

from app.services.reporting.delivery import period_bounds
from app.services.reporting.due_sends import due_report_sends, run_due_reports

MADRID = "Europe/Madrid"
PERSON = {"user_id": "99999999-9999-9999-9999-999999999999", "company_id": "88888888-8888-8888-8888-888888888888", "timezone": MADRID}


def test_madrid_before_1800_not_due_at_1800_due_sent_skips_failed_retries():
    before_cutoff = datetime(2026, 9, 22, 15, 59, tzinfo=timezone.utc)
    at_cutoff = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
    assert due_report_sends(before_cutoff, [PERSON], []) == []
    assert due_report_sends(at_cutoff, [PERSON], []) == [PERSON]

    period_start, _ = period_bounds(at_cutoff, MADRID)
    ps = period_start.isoformat()
    already_sent = [{"user_id": PERSON["user_id"], "period_start": ps, "delivery_status": "sent"}]
    assert due_report_sends(at_cutoff, [PERSON], already_sent) == []

    failed = [{"user_id": PERSON["user_id"], "period_start": ps, "delivery_status": "failed"}]
    assert due_report_sends(at_cutoff, [PERSON], failed) == [PERSON]

    uncertain = [{"user_id": PERSON["user_id"], "period_start": ps, "delivery_status": "uncertain"}]
    assert due_report_sends(at_cutoff, [PERSON], uncertain) == []

    calls: list[dict] = []

    def send(person: dict) -> None:
        calls.append(person)

    run_due_reports(at_cutoff, [PERSON], already_sent, send)
    assert calls == []

    calls.clear()
    run_due_reports(at_cutoff, [PERSON], uncertain, send)
    assert calls == []

    calls.clear()
    run_due_reports(at_cutoff, [PERSON], failed, send)
    assert calls == [PERSON]
