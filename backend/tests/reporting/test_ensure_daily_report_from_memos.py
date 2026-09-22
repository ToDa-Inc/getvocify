"""F13: the email tick materializes today's daily report from memos before due sends."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ensure-daily-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ensure-daily-32")

from app.services.reporting.daily_snapshot import ensure_self_daily_report, ensure_self_daily_reports_for_due_tick
from app.services.reporting.delivery import period_bounds, persist_report_delivery
from app.services.reporting.due_sends import tick_due_report_emails
from app.services.reporting.tick_bindings import _load_daily_report_people, _load_report_delivery_existing

MADRID = "Europe/Madrid"
USER = "99999999-9999-9999-9999-999999999999"
COMPANY = "88888888-8888-8888-8888-888888888888"
AT_CUTOFF = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)


class FakeSender:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, key: str) -> None:
        self.sent.append(key)

    def reconcile(self, key: str):
        return None


class _FakeQuery:
    def __init__(self, store, table: str):
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str]] = []
        self._gte_filters: list[tuple[str, str]] = []
        self._in_filters: dict[str, list] = {}
        self._upsert_payload: dict | None = None
        self._on_conflict: str | None = None
        self._limit: int | None = None

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value: str):
        self._filters.append((column, value))
        return self

    def gte(self, column: str, value: str):
        self._gte_filters.append((column, value))
        return self

    def in_(self, column: str, values: list):
        self._in_filters[column] = values
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def upsert(self, payload: dict, on_conflict: str):
        self._upsert_payload = payload
        self._on_conflict = on_conflict
        return self

    def execute(self):
        rows = list(self._store.get(self._table, []))
        if self._upsert_payload is not None:
            conflict_cols = (self._on_conflict or "").split(",")
            rows = [
                r
                for r in rows
                if not all(r.get(col) == self._upsert_payload.get(col) for col in conflict_cols if col)
            ]
            rows.append(dict(self._upsert_payload))
            self._store[self._table] = rows
            return SimpleNamespace(data=[self._upsert_payload])
        for column, value in self._filters:
            rows = [r for r in rows if str(r.get(column)) == str(value)]
        for column, value in self._gte_filters:
            rows = [r for r in rows if str(r.get(column) or "") >= str(value)]
        for column, values in self._in_filters.items():
            rows = [r for r in rows if r.get(column) in values or r.get("id") in values or str(r.get(column)) in values]
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self, *, memos: list[dict]):
        period_start, _ = period_bounds(AT_CUTOFF, MADRID)
        self.tables: dict[str, list[dict]] = {
            "reports": [],
            "report_deliveries": [],
            "memos": memos,
            "brief_preferences": [{"user_id": USER, "timezone": MADRID}],
            "team_outcome_observations": [],
        }
        self._period_start = period_start.isoformat()

    def table(self, name: str):
        return _FakeQuery(self.tables, name)

    @property
    def postgrest(self):
        return self

    def schema(self, _name: str):
        return self

    def from_(self, _name: str):
        class _AuthQuery:
            def select(self, _cols):
                return self

            def in_(self, _col, _vals):
                return self

            def execute(self):
                return SimpleNamespace(data=[{"id": USER, "email": "rep@example.com"}])

        return _AuthQuery()


def _memo_in_period(*, screening: str = "connected", meeting: bool = False) -> dict:
    captured = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc).isoformat()
    intel = {"meeting": {"agreed": True}} if meeting else {}
    return {
        "id": "memo-1",
        "company_id": COMPANY,
        "user_id": USER,
        "screening_outcome": screening,
        "capture_started_at": captured,
        "created_at": captured,
        "extraction": {},
        "intelligence": intel,
    }


def test_ensure_self_daily_report_upserts_once_and_build_snapshot_from_memos():
    fake = FakeSupabase(memos=[_memo_in_period(meeting=True)])
    ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert len(fake.tables["reports"]) == 1
    row = fake.tables["reports"][0]
    assert row["report_type"] == "daily"
    assert row["scope"] == "self"
    assert row["period_start"] == fake._period_start
    snap = row["snapshot"]
    assert snap["metrics"]["attempts"] == 1
    assert snap["metrics"]["connected_calls"] == 1
    assert snap["metrics"]["meetings_agreed"] == 1
    assert snap["metrics"]["deals_won"] is None

    ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert len(fake.tables["reports"]) == 1


def test_tick_ensures_report_from_memos_before_email_send():
    fake = FakeSupabase(memos=[_memo_in_period()])
    sender = FakeSender()

    def ensure_daily(now):
        ensure_self_daily_reports_for_due_tick(fake, now)

    def load_people():
        return _load_daily_report_people(fake)

    def load_existing():
        return _load_report_delivery_existing(fake)

    def persist_delivery(result, person, now=None):
        persist_report_delivery(
            fake,
            idempotency_key=result["idempotency_key"],
            report_id=person["report_id"],
            channel="email",
            delivery_status=result["delivery_status"],
            attempt_at=now,
        )

    tick_due_report_emails(
        AT_CUTOFF,
        load_people,
        load_existing,
        sender,
        persist_delivery,
        ensure_daily=ensure_daily,
    )
    assert len(fake.tables["reports"]) == 1
    report_id = fake.tables["reports"][0]["id"]
    assert sender.sent == [f"{report_id}:r1:email"]
