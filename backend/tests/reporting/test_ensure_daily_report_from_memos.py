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
OTHER_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMPANY = "88888888-8888-8888-8888-888888888888"
AT_CUTOFF = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
MEMO_COLUMNS = {
    "id", "company_id", "user_id", "screening_outcome", "extraction", "capture_started_at", "created_at",
}


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
        self._insert_payload: dict | list | None = None
        self._limit: int | None = None

    def select(self, columns: str):
        if self._table == "memos":
            missing = {c.strip() for c in columns.split(",")} - MEMO_COLUMNS
            if missing:
                raise RuntimeError(f"column memos.{sorted(missing)[0]} does not exist")
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

    def insert(self, payload: dict | list):
        self._insert_payload = payload
        return self

    def execute(self):
        rows = list(self._store.get(self._table, []))
        if self._insert_payload is not None:
            to_add = (
                self._insert_payload
                if isinstance(self._insert_payload, list)
                else [dict(self._insert_payload)]
            )
            rows.extend(to_add)
            self._store[self._table] = rows
            return SimpleNamespace(data=to_add)
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
            "report_notifications": [],
            "company_feature_flags": [
                {"company_id": COMPANY, "flag": "REPORTING_DAILY_EMAIL_ENABLED", "enabled": True},
            ],
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
        "extraction": {"intelligence": intel},
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


def test_tick_includes_memo_when_capture_falls_in_local_period_not_created_at():
    row_created = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc).isoformat()
    captured_today = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc).isoformat()
    memo = {
        "id": "memo-captured-today",
        "company_id": COMPANY,
        "user_id": USER,
        "screening_outcome": "connected",
        "created_at": row_created,
        "capture_started_at": captured_today,
        "extraction": {},
        "intelligence": {},
    }
    fake = FakeSupabase(memos=[memo])
    ensure_self_daily_reports_for_due_tick(fake, AT_CUTOFF)
    assert len(fake.tables["reports"]) == 1
    snap = fake.tables["reports"][0]["snapshot"]
    assert snap["metrics"]["attempts"] == 1
    assert snap["metrics"]["deals_won"] is None


def test_tick_skips_memo_captured_yesterday_empty_period_attempts_zero():
    captured_yesterday = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc).isoformat()
    memo = {
        "id": "memo-yesterday",
        "company_id": COMPANY,
        "user_id": USER,
        "screening_outcome": "connected",
        "created_at": captured_yesterday,
        "capture_started_at": captured_yesterday,
        "extraction": {},
        "intelligence": {},
    }
    fake = FakeSupabase(memos=[memo])
    ensure_self_daily_reports_for_due_tick(fake, AT_CUTOFF)
    assert fake.tables["reports"] == []


def test_ensure_self_daily_report_uses_capture_started_at_over_stale_created_at():
    row_created = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc).isoformat()
    captured_today = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc).isoformat()
    memo = {
        "id": "memo-1",
        "company_id": COMPANY,
        "user_id": USER,
        "screening_outcome": "connected",
        "created_at": row_created,
        "capture_started_at": captured_today,
        "extraction": {},
        "intelligence": {},
    }
    fake = FakeSupabase(memos=[memo])
    ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert len(fake.tables["reports"]) == 1
    assert fake.tables["reports"][0]["snapshot"]["metrics"]["attempts"] == 1
    assert fake.tables["reports"][0]["snapshot"]["metrics"]["deals_won"] is None


def test_tick_ensures_report_from_memos_before_email_send():
    fake = FakeSupabase(memos=[_memo_in_period()])
    sender = FakeSender()

    def ensure_daily(now):
        ensure_self_daily_reports_for_due_tick(fake, now)

    def load_people():
        return _load_daily_report_people(fake, AT_CUTOFF)

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


def _notifications_for_user(fake: FakeSupabase, user_id: str) -> list[dict]:
    return [n for n in fake.tables["report_notifications"] if str(n.get("user_id")) == user_id]


def test_ensure_self_daily_report_creates_one_notification_with_read_at_null():
    fake = FakeSupabase(memos=[_memo_in_period()])
    report_id = ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert report_id
    notes = _notifications_for_user(fake, USER)
    assert len(notes) == 1
    assert notes[0]["report_id"] == report_id
    assert notes[0]["read_at"] is None


def test_second_ensure_same_day_does_not_duplicate_notification():
    fake = FakeSupabase(memos=[_memo_in_period()])
    ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert len(_notifications_for_user(fake, USER)) == 1


def test_ensure_notification_is_not_visible_to_another_user():
    fake = FakeSupabase(memos=[_memo_in_period()])
    ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert _notifications_for_user(fake, OTHER_USER) == []
    assert len(_notifications_for_user(fake, USER)) == 1


def test_failed_email_retry_next_day_does_not_duplicate_notification():
    fake = FakeSupabase(memos=[_memo_in_period()])
    ensure_self_daily_reports_for_due_tick(fake, AT_CUTOFF)
    assert len(_notifications_for_user(fake, USER)) == 1

    class BadSender(FakeSender):
        def send(self, key: str) -> None:
            raise RuntimeError("smtp down")

    sender_fail = BadSender()
    tick_clock: list[datetime] = []

    def ensure_daily(now):
        tick_clock.append(now)
        ensure_self_daily_reports_for_due_tick(fake, now)

    def load_people():
        return _load_daily_report_people(fake, tick_clock[-1])

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
        sender_fail,
        persist_delivery,
        ensure_daily=ensure_daily,
    )
    assert len(_notifications_for_user(fake, USER)) == 1

    next_day = datetime(2026, 9, 23, 16, 10, tzinfo=timezone.utc)
    sender_ok = FakeSender()
    tick_due_report_emails(
        next_day,
        load_people,
        load_existing,
        sender_ok,
        persist_delivery,
        ensure_daily=ensure_daily,
    )
    assert len(_notifications_for_user(fake, USER)) == 1


def test_ensure_does_not_create_notification_when_report_not_built():
    captured_yesterday = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc).isoformat()
    memo = {
        "id": "memo-yesterday",
        "company_id": COMPANY,
        "user_id": USER,
        "screening_outcome": "connected",
        "created_at": captured_yesterday,
        "capture_started_at": captured_yesterday,
        "extraction": {},
        "intelligence": {},
    }
    fake = FakeSupabase(memos=[memo])
    result = ensure_self_daily_report(
        fake,
        company_id=COMPANY,
        user_id=USER,
        timezone=MADRID,
        now=AT_CUTOFF,
    )
    assert result is None
    assert fake.tables["report_notifications"] == []
