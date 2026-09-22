"""F13: report email tick runs once per Madrid local date."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-report-tick-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-report-tick-32")

from app.services.reporting.due_sends import reset_report_tick_guard, tick_due_report_emails

MADRID = "Europe/Madrid"
PERSON = {
    "user_id": "99999999-9999-9999-9999-999999999999",
    "company_id": "88888888-8888-8888-8888-888888888888",
    "timezone": MADRID,
    "report_id": "report-daily-1",
    "revision": 1,
}


class FakeSender:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, key: str) -> None:
        self.sent.append(key)

    def reconcile(self, key: str):
        return None


def test_tick_sends_once_per_madrid_local_date():
    reset_report_tick_guard()
    at_cutoff = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
    sender = FakeSender()

    def load_people():
        return [PERSON]

    def load_existing():
        return []

    tick_due_report_emails(at_cutoff, load_people, load_existing, sender)
    assert sender.sent == ["report-daily-1:r1:email"]

    tick_due_report_emails(at_cutoff, load_people, load_existing, sender)
    assert sender.sent == ["report-daily-1:r1:email"]
