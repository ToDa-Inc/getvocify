"""F13.04 / F15.05: weekly emails use the durable delivery key; a lost role or a failed email never loses the report."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")

import pytest

from app.services import feature_flags
from app.services.reporting.periodic import deliver_weekly_reports_for_tick
from app.services.reporting.weekly import week_bounds
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
MADRID = "Europe/Madrid"
FRIDAY_1805 = datetime(2026, 9, 25, 16, 5, tzinfo=UTC)
FRIDAY_2000 = datetime(2026, 9, 25, 18, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
COMPANY = "88888888-8888-8888-8888-888888888888"
REP = "99999999-9999-9999-9999-999999999999"
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

WEEK_START = week_bounds(FRIDAY_1805, MADRID)[0].isoformat()

SNAPSHOT = {
    "scope": "self",
    "report_type": "weekly",
    "metrics": {"attempts": 3, "connected_calls": 2, "meetings_agreed": 1, "deals_won": None, "adherence": None},
    "coverage": {"crm_outcomes": "unavailable", "objections": "complete"},
    "series": [],
    "objections": [],
    "coaching": None,
}


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


class RecordingSender:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[str] = []
        self.built: list[tuple[str, str, str]] = []

    def factory(self, report: dict, email: str, subject: str, html: str):
        self.built.append((report["id"], email, subject))
        outer = self

        class _One:
            def send(self, key):
                if outer.fail:
                    raise RuntimeError("resend down")
                outer.sent.append(key)

            def reconcile(self, _key):
                return None

        return _One()


def _report(report_id: str, *, user_id: str, scope: str, report_type: str = "weekly") -> dict:
    return {
        "id": report_id,
        "company_id": COMPANY,
        "user_id": user_id,
        "scope": scope,
        "period_start": WEEK_START,
        "report_type": report_type,
        "revision": 1,
        "snapshot": {**SNAPSHOT, "scope": scope},
    }


def _db(*, admin_role: str = "admin", flags=None, emails=None, reports=None) -> FakeDB:
    return FakeDB(
        {
            "reports": reports if reports is not None else [
                _report("weekly-rep", user_id=REP, scope="self"),
                _report("team-admin", user_id=ADMIN, scope="team"),
            ],
            "report_deliveries": [],
            "report_notifications": [
                {"id": "n:weekly-rep", "report_id": "weekly-rep", "user_id": REP, "read_at": None},
                {"id": "n:team-admin", "report_id": "team-admin", "user_id": ADMIN, "read_at": None},
            ],
            "report_preferences": [],
            "brief_preferences": [],
            "company_members": [
                {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
                {"company_id": COMPANY, "user_id": ADMIN, "role": admin_role, "status": "active"},
            ],
            "company_feature_flags": flags if flags is not None else [
                {"company_id": COMPANY, "flag": "REPORTING_WEEKLY_ENABLED", "enabled": True},
                {"company_id": COMPANY, "flag": "REPORTING_TEAM_ENABLED", "enabled": True},
            ],
        },
        emails=emails if emails is not None else {REP: "rep@example.com", ADMIN: "boss@example.com"},
    )


def test_each_weekly_report_is_sent_once_with_its_durable_key():
    db = _db()
    sender = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=sender.factory)
    deliver_weekly_reports_for_tick(db, FRIDAY_2000, sender_factory=sender.factory)
    assert sorted(sender.sent) == ["team-admin:r1:email", "weekly-rep:r1:email"]
    statuses = {row["idempotency_key"]: row["delivery_status"] for row in db.tables["report_deliveries"]}
    assert statuses == {"team-admin:r1:email": "sent", "weekly-rep:r1:email": "sent"}
    subjects = {report_id: subject for report_id, _email, subject in sender.built}
    assert subjects == {"weekly-rep": "Tu semana en Vocify", "team-admin": "Tu equipo esta semana"}


def test_admin_who_lost_the_role_before_sending_gets_no_team_email():
    db = _db(admin_role="member")
    sender = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=sender.factory)
    assert sender.sent == ["weekly-rep:r1:email"]
    assert all(row["report_id"] != "team-admin" for row in db.tables["report_deliveries"])


def test_failed_email_keeps_report_and_notification_and_retries_next_day_with_the_same_key():
    db = _db(reports=[_report("weekly-rep", user_id=REP, scope="self")])
    failing = RecordingSender(fail=True)
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=failing.factory)
    assert db.tables["report_deliveries"][0]["delivery_status"] == "failed"
    assert len(db.tables["reports"]) == 1
    assert len(db.tables["report_notifications"]) == 2

    same_day = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_2000, sender_factory=same_day.factory)
    assert same_day.sent == []

    next_day = RecordingSender()
    deliver_weekly_reports_for_tick(db, SATURDAY, sender_factory=next_day.factory)
    assert next_day.sent == ["weekly-rep:r1:email"]
    assert db.tables["report_deliveries"][0]["delivery_status"] == "sent"


def test_flag_turned_off_before_sending_sends_nothing():
    db = _db(flags=[])
    sender = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=sender.factory)
    assert sender.sent == []
    assert db.tables["report_deliveries"] == []


def test_preference_turned_off_before_sending_sends_nothing():
    db = _db(reports=[_report("weekly-rep", user_id=REP, scope="self")])
    db.tables["report_preferences"] = [
        {"user_id": REP, "daily_enabled": True, "weekly_enabled": False, "team_enabled": True},
    ]
    sender = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=sender.factory)
    assert sender.sent == []


def test_without_an_email_address_nothing_is_sent_or_recorded():
    db = _db(emails={})
    sender = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=sender.factory)
    assert sender.sent == []
    assert db.tables["report_deliveries"] == []


def test_daily_reports_are_left_to_the_daily_tick():
    db = _db(reports=[_report("daily-rep", user_id=REP, scope="self", report_type="daily")])
    sender = RecordingSender()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=sender.factory)
    assert sender.sent == []


def test_no_sender_configured_means_no_send_and_no_record():
    db = _db()
    deliver_weekly_reports_for_tick(db, FRIDAY_1805, sender_factory=None)
    assert db.tables["report_deliveries"] == []
