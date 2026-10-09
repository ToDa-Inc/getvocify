"""F13 daily email: the email shows the stored numbers, respects the opt-out, and sends from inside the server loop."""

import asyncio
from datetime import datetime, timezone

import pytest

from app.services import feature_flags
from app.services.reporting.resend_sender import ResendReportSender
from app.services.reporting.tick_bindings import _load_daily_report_people
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
NOW = datetime(2026, 9, 22, 16, 30, tzinfo=UTC)
COMPANY = "88888888-8888-8888-8888-888888888888"
REP = "99999999-9999-9999-9999-999999999999"
QUIET = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SNAPSHOT = {"metrics": {"attempts": 4, "connected_calls": 3, "meetings_agreed": 1, "deals_won": None, "adherence": None}}


def _daily(report_id, user_id):
    return {
        "id": report_id,
        "company_id": COMPANY,
        "user_id": user_id,
        "scope": "self",
        "report_type": "daily",
        "period_start": "2026-09-21T22:00:00+00:00",
        "revision": 1,
        "snapshot": SNAPSHOT,
    }


DAILY_ON = [{"company_id": COMPANY, "flag": "REPORTING_DAILY_EMAIL_ENABLED", "enabled": True}]


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _db(prefs=(), flags=DAILY_ON):
    return FakeDB(
        {
            "reports": [_daily("r-rep", REP), _daily("r-quiet", QUIET)],
            "brief_preferences": [],
            "report_preferences": list(prefs),
            "company_feature_flags": list(flags),
        },
        emails={REP: "rep@example.com", QUIET: "quiet@example.com"},
    )


def test_each_person_carries_the_stored_snapshot_for_the_email():
    people = {person["report_id"]: person for person in _load_daily_report_people(_db(), NOW)}
    assert people["r-rep"]["snapshot"] == SNAPSHOT


def test_no_daily_email_for_a_company_without_the_flag():
    assert _load_daily_report_people(_db(flags=()), NOW) == []


def test_a_person_who_turned_the_daily_off_gets_no_email():
    db = _db(prefs=[{"user_id": QUIET, "daily_enabled": False, "weekly_enabled": True, "team_enabled": True}])
    assert [person["user_id"] for person in _load_daily_report_people(db, NOW)] == [REP]


class _AsyncResend:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, html, from_email=None, idempotency_key=None):
        self.sent.append((to, idempotency_key))
        return {"id": "re_1"}


def test_the_sender_works_when_called_from_inside_a_running_event_loop():
    client = _AsyncResend()
    sender = ResendReportSender(client, to="rep@example.com", subject="s", html="<p>h</p>")

    async def from_the_server_loop():
        sender.send("r-rep:r1:email")

    asyncio.run(from_the_server_loop())
    assert client.sent == [("rep@example.com", "r-rep:r1:email")]
    assert sender.reconcile("r-rep:r1:email") == "re_1"
