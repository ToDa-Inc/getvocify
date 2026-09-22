"""F13: report email tick persists sent deliveries; restart-safe same local day."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-report-tick-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-report-tick-32")

from app.services.reporting.delivery import period_bounds, persist_report_delivery
from app.services.reporting.due_sends import tick_due_report_emails
from app.services.reporting.tick_bindings import _load_report_delivery_existing

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
    def __init__(self, *, fail: Exception | None = None):
        self.sent: list[str] = []
        self._fail = fail

    def send(self, key: str) -> None:
        if self._fail is not None:
            raise self._fail
        self.sent.append(key)

    def reconcile(self, key: str):
        return None


class _FakeQuery:
    def __init__(self, store, table: str):
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str]] = []
        self._in_filters: dict[str, list] = {}
        self._upsert_payload: dict | None = None
        self._on_conflict: str | None = None

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value: str):
        self._filters.append((column, value))
        return self

    def in_(self, column: str, values: list):
        self._in_filters[column] = values
        return self

    def upsert(self, payload: dict, on_conflict: str):
        self._upsert_payload = payload
        self._on_conflict = on_conflict
        return self

    def execute(self):
        rows = list(self._store.get(self._table, []))
        if self._upsert_payload is not None:
            key = self._upsert_payload["idempotency_key"]
            rows = [r for r in rows if r.get("idempotency_key") != key]
            rows.append(dict(self._upsert_payload))
            self._store[self._table] = rows
            return SimpleNamespace(data=[self._upsert_payload])
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        for column, values in self._in_filters.items():
            rows = [r for r in rows if r.get(column) in values or r.get("id") in values]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "report_deliveries": [],
            "reports": [
                {
                    "id": PERSON["report_id"],
                    "user_id": PERSON["user_id"],
                    "period_start": period_bounds(
                        datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc), MADRID
                    )[0].isoformat(),
                }
            ],
        }

    def table(self, name: str):
        return _FakeQuery(self.tables, name)


def test_tick_persists_sent_and_second_tick_does_not_resend():
    at_cutoff = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
    fake = FakeSupabase()
    sender = FakeSender()

    def load_people():
        return [PERSON]

    def load_existing():
        return _load_report_delivery_existing(fake)

    def persist_delivery(result, person):
        persist_report_delivery(
            fake,
            idempotency_key=result["idempotency_key"],
            report_id=person["report_id"],
            channel="email",
            delivery_status=result["delivery_status"],
        )

    tick_due_report_emails(at_cutoff, load_people, load_existing, sender, persist_delivery)
    assert sender.sent == ["report-daily-1:r1:email"]
    assert len(fake.tables["report_deliveries"]) == 1
    assert fake.tables["report_deliveries"][0]["delivery_status"] == "sent"

    sender2 = FakeSender()
    tick_due_report_emails(at_cutoff, load_people, load_existing, sender2, persist_delivery)
    assert sender2.sent == []


def test_tick_persists_failed_then_second_tick_retries_once():
    at_cutoff = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
    fake = FakeSupabase()
    sender = FakeSender(fail=RuntimeError("smtp down"))

    def load_people():
        return [PERSON]

    def load_existing():
        return _load_report_delivery_existing(fake)

    def persist_delivery(result, person):
        persist_report_delivery(
            fake,
            idempotency_key=result["idempotency_key"],
            report_id=person["report_id"],
            channel="email",
            delivery_status=result["delivery_status"],
        )

    tick_due_report_emails(at_cutoff, load_people, load_existing, sender, persist_delivery)
    assert sender.sent == []
    assert len(fake.tables["report_deliveries"]) == 1
    assert fake.tables["report_deliveries"][0]["delivery_status"] == "failed"

    sender2 = FakeSender()
    tick_due_report_emails(at_cutoff, load_people, load_existing, sender2, persist_delivery)
    assert sender2.sent == ["report-daily-1:r1:email"]
    assert fake.tables["report_deliveries"][0]["delivery_status"] == "sent"


def test_tick_persists_uncertain_and_second_tick_does_not_resend():
    at_cutoff = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
    fake = FakeSupabase()
    sender = FakeSender(fail=TimeoutError("resend timeout"))

    def load_people():
        return [PERSON]

    def load_existing():
        return _load_report_delivery_existing(fake)

    def persist_delivery(result, person):
        persist_report_delivery(
            fake,
            idempotency_key=result["idempotency_key"],
            report_id=person["report_id"],
            channel="email",
            delivery_status=result["delivery_status"],
        )

    tick_due_report_emails(at_cutoff, load_people, load_existing, sender, persist_delivery)
    assert sender.sent == []
    assert len(fake.tables["report_deliveries"]) == 1
    assert fake.tables["report_deliveries"][0]["delivery_status"] == "uncertain"

    sender2 = FakeSender()
    tick_due_report_emails(at_cutoff, load_people, load_existing, sender2, persist_delivery)
    assert sender2.sent == []
