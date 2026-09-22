"""F13: daily report email is due after 18:00 local; sent periods are not resent."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-due-sends-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-due-sends-32")

from app.services.reporting.delivery import period_bounds
from app.services.reporting.due_sends import due_report_sends, run_due_report_emails

MADRID = "Europe/Madrid"
PERSON = {
    "user_id": "99999999-9999-9999-9999-999999999999",
    "company_id": "88888888-8888-8888-8888-888888888888",
    "timezone": MADRID,
    "report_id": "report-daily-1",
    "revision": 1,
    "email": "rep@example.com",
}


class FakeSender:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, key: str) -> None:
        self.sent.append(key)

    def reconcile(self, key: str):
        return None


def test_madrid_before_1800_not_due_at_1800_due_sent_skips_failed_retries_once_per_local_day():
    before_cutoff = datetime(2026, 9, 22, 15, 59, tzinfo=timezone.utc)
    at_cutoff = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
    assert due_report_sends(before_cutoff, [PERSON], []) == []
    assert due_report_sends(at_cutoff, [PERSON], []) == [PERSON]

    period_start, _ = period_bounds(at_cutoff, MADRID)
    ps = period_start.isoformat()
    already_sent = [{"user_id": PERSON["user_id"], "period_start": ps, "delivery_status": "sent"}]
    assert due_report_sends(at_cutoff, [PERSON], already_sent) == []

    uncertain = [{"user_id": PERSON["user_id"], "period_start": ps, "delivery_status": "uncertain"}]
    assert due_report_sends(at_cutoff, [PERSON], uncertain) == []

    fail_at_1810 = datetime(2026, 9, 22, 16, 10, tzinfo=timezone.utc)
    failed_same_day = [
        {
            "user_id": PERSON["user_id"],
            "period_start": ps,
            "delivery_status": "failed",
            "last_attempt_at": fail_at_1810.isoformat(),
        }
    ]
    tick_same_day_1820 = datetime(2026, 9, 22, 16, 20, tzinfo=timezone.utc)
    assert due_report_sends(tick_same_day_1820, [PERSON], failed_same_day) == []

    tick_next_day_1810 = datetime(2026, 9, 23, 16, 10, tzinfo=timezone.utc)
    assert due_report_sends(tick_next_day_1810, [PERSON], failed_same_day) == [PERSON]

    failed_no_timestamp = [{"user_id": PERSON["user_id"], "period_start": ps, "delivery_status": "failed"}]
    assert due_report_sends(at_cutoff, [PERSON], failed_no_timestamp) == [PERSON]

    sender = FakeSender()
    run_due_report_emails(at_cutoff, [PERSON], already_sent, sender)
    assert sender.sent == []

    sender = FakeSender()
    run_due_report_emails(at_cutoff, [PERSON], uncertain, sender)
    assert sender.sent == []

    sender = FakeSender()
    run_due_report_emails(tick_same_day_1820, [PERSON], failed_same_day, sender)
    assert sender.sent == []

    sender = FakeSender()
    run_due_report_emails(tick_next_day_1810, [PERSON], failed_same_day, sender)
    assert sender.sent == ["report-daily-1:r1:email"]

    sender = FakeSender()
    run_due_report_emails(at_cutoff, [PERSON], [], sender)
    assert sender.sent == ["report-daily-1:r1:email"]
