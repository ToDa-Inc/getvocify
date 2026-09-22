"""F13: _ReportIdSender routes recipients; missing email must not look like sent."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-tick-bindings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-tick-bindings-32")

from app.services.reporting.delivery import deliver_report
from app.services.reporting.tick_bindings import _ReportIdSender


class FakeResendClient:
    def __init__(self):
        self.calls: list[str] = []

    async def send_email(self, to, subject, html, from_email=None, idempotency_key=None):
        self.calls.append(idempotency_key or "")
        return {"id": "msg-1"}


def test_report_id_sender_without_recipient_records_failed_not_sent():
    client = FakeResendClient()
    sender = _ReportIdSender(client)
    sender.set_recipients([{"report_id": "other-report", "email": "rep@example.com"}])
    report = {"id": "report-1", "revision": 1}
    result = deliver_report(report=report, channel="email", existing=None, sender=sender, allowed=True)
    assert result["delivery_status"] == "failed"
    assert result["sent"] is False
    assert client.calls == []


def test_report_id_sender_with_recipient_records_sent():
    client = FakeResendClient()
    sender = _ReportIdSender(client)
    sender.set_recipients([{"report_id": "report-1", "email": "rep@example.com"}])
    report = {"id": "report-1", "revision": 1}
    result = deliver_report(report=report, channel="email", existing=None, sender=sender, allowed=True)
    assert result["delivery_status"] == "sent"
    assert result["sent"] is True
    assert client.calls == ["report-1:r1:email"]
