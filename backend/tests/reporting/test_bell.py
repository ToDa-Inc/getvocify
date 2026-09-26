"""F13.04 / F15.05: the bell lists reports the person may still read and what Vocify did, from existing audit rows."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import reports as reports_api
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.reporting.activity import vocify_activity
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)
COMPANY = "88888888-8888-8888-8888-888888888888"
OTHER_COMPANY = "77777777-7777-7777-7777-777777777777"
USER = "99999999-9999-9999-9999-999999999999"
OTHER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def fresh_flags(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(reports_api, "_now", lambda: NOW)
    yield
    feature_flags.clear_cache()


def _update(memo_id, resource, *, status="success", user_id=USER, at="2026-09-25T10:00:00+00:00", action="update_deal"):
    return {
        "memo_id": memo_id,
        "user_id": user_id,
        "action_type": action,
        "resource_type": resource,
        "status": status,
        "created_at": at,
        "completed_at": at,
    }


def _memo(memo_id, *, user_id=USER, company_id=COMPANY, contact="Ana Pérez", company_name="Acme"):
    return {
        "id": memo_id,
        "user_id": user_id,
        "company_id": company_id,
        "extraction": {"contactName": contact, "companyName": company_name},
    }


MEMOS = {
    "m-1": _memo("m-1"),
    "m-2": _memo("m-2", contact=None, company_name="Globex"),
    "m-other-user": _memo("m-other-user", user_id=OTHER),
    "m-other-company": _memo("m-other-company", company_id=OTHER_COMPANY),
    "m-legacy": _memo("m-legacy", company_id=None),
}


def _activity(updates=(), writes=()):
    return vocify_activity(
        list(updates), list(writes), MEMOS, user_id=USER, company_id=COMPANY, now=NOW,
    )


def test_successful_crm_writes_group_by_conversation_with_the_reason():
    items = _activity([
        _update("m-1", "deal", at="2026-09-25T10:00:00+00:00"),
        _update("m-1", "contact", action="upsert_contact", at="2026-09-25T10:00:01+00:00"),
        _update("m-1", "task", action="create_tasks", at="2026-09-25T10:00:02+00:00"),
        _update("m-1", "task", action="create_tasks", at="2026-09-25T10:00:03+00:00"),
    ])
    assert items == [{
        "kind": "crm_updated",
        "memo_id": "m-1",
        "subject": "Ana Pérez",
        "resources": ["deal", "contact", "task"],
        "at": "2026-09-25T10:00:03+00:00",
    }]


def test_failed_pending_and_other_peoples_writes_are_not_listed():
    items = _activity([
        _update("m-1", "deal", status="failed"),
        _update("m-1", "contact", status="pending"),
        _update("m-other-user", "deal", user_id=OTHER),
        _update("m-other-user", "deal"),
        _update("m-other-company", "deal"),
    ])
    assert items == []


def test_legacy_memo_without_company_still_belongs_to_its_author():
    items = _activity([_update("m-legacy", "note", action="create_note")])
    assert [item["memo_id"] for item in items] == ["m-legacy"]


def test_writes_older_than_seven_days_are_not_listed():
    assert _activity([_update("m-1", "deal", at="2026-09-18T15:59:00+00:00")]) == []


def test_subject_falls_back_to_the_company_name():
    items = _activity([_update("m-2", "deal")])
    assert items[0]["subject"] == "Globex"


def test_meeting_stage_move_is_listed_only_with_a_date_and_a_real_change():
    writes = [
        {"memo_id": "m-1", "stage_changed": True, "crm_status": "succeeded", "created_at": "2026-09-24T09:00:00+00:00"},
        {"memo_id": "m-2", "stage_changed": False, "crm_status": "succeeded", "created_at": "2026-09-24T09:00:00+00:00"},
        {"memo_id": "m-1", "stage_changed": True, "crm_status": "succeeded", "created_at": None},
        {"memo_id": "m-other-user", "stage_changed": True, "crm_status": "succeeded", "created_at": "2026-09-24T09:00:00+00:00"},
    ]
    items = _activity(writes=writes)
    assert items == [{
        "kind": "meeting_stage",
        "memo_id": "m-1",
        "subject": "Ana Pérez",
        "resources": [],
        "at": "2026-09-24T09:00:00+00:00",
    }]


def test_most_recent_first_and_at_most_eight():
    updates = [
        _update(f"m-{i}", "deal", at=f"2026-09-2{i % 5}T10:00:00+00:00")
        for i in range(12)
    ]
    memos = {f"m-{i}": _memo(f"m-{i}") for i in range(12)}
    items = vocify_activity(updates, [], memos, user_id=USER, company_id=COMPANY, now=NOW)
    assert len(items) == 8
    stamps = [item["at"] for item in items]
    assert stamps == sorted(stamps, reverse=True)


# ---------- endpoint ----------


def _report(report_id, *, user_id=USER, scope="self", report_type="daily", period="2026-09-24T22:00:00+00:00", company_id=COMPANY):
    return {
        "id": report_id,
        "company_id": company_id,
        "user_id": user_id,
        "scope": scope,
        "report_type": report_type,
        "period_start": period,
        "revision": 1,
        "snapshot": {"metrics": {"attempts": 1, "connected_calls": 1, "meetings_agreed": 0,
                                 "deals_won": None, "adherence": None},
                     "coverage": {"crm_outcomes": "unavailable"}, "coaching": None},
    }


def _note(report_id, *, user_id=USER, read_at=None):
    return {"id": f"n:{report_id}", "report_id": report_id, "user_id": user_id, "read_at": read_at}


def _db(*, flags=(), fail_tables=(), extra_reports=(), extra_notes=()):
    reports = [
        _report("daily-1", period="2026-09-23T22:00:00+00:00"),
        _report("weekly-1", report_type="weekly", period="2026-09-20T22:00:00+00:00"),
        _report("team-1", scope="team", report_type="weekly", period="2026-09-20T22:01:00+00:00"),
        *extra_reports,
    ]
    notes = [
        _note("daily-1"),
        _note("weekly-1", read_at="2026-09-25T17:00:00+00:00"),
        _note("team-1"),
        _note("daily-other", user_id=OTHER),
        *extra_notes,
    ]
    return FakeDB(
        {
            "reports": reports,
            "report_notifications": notes,
            "crm_updates": [_update("m-1", "deal", at="2026-09-25T10:00:00+00:00")],
            "meeting_writes": [],
            "memos": list(MEMOS.values()),
            "company_feature_flags": [
                {"company_id": COMPANY, "flag": name, "enabled": True} for name in flags
            ],
        },
        fail_tables=fail_tables,
    )


def _client(db, role="admin", user_id=USER, company_id=COMPANY):
    app = FastAPI()
    app.include_router(reports_api.router)
    app.include_router(reports_api.notifications)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=company_id, user_id=user_id, role=role, status="active",
    )
    return TestClient(app)


ALL_FLAGS = ("REPORTING_WEEKLY_ENABLED", "REPORTING_TEAM_ENABLED", "NOTIFICATIONS_ACTIVITY_ENABLED")


def test_bell_lists_readable_reports_newest_first_with_type_and_read_state():
    body = _client(_db(flags=ALL_FLAGS)).get("/api/v1/notifications").json()
    assert [item["report_id"] for item in body["items"]] == ["daily-1", "team-1", "weekly-1"]
    first = body["items"][0]
    assert first == {
        "id": "n:daily-1",
        "report_id": "daily-1",
        "report_type": "daily",
        "scope": "self",
        "period_start": "2026-09-23T22:00:00+00:00",
        "read_at": None,
    }
    assert body["unread"] == 2


def test_flags_off_keep_the_bell_as_it_was():
    body = _client(_db()).get("/api/v1/notifications").json()
    assert [item["report_id"] for item in body["items"]] == ["daily-1"]
    assert body["unread"] == 1
    assert "activity" not in body


def test_team_reports_disappear_from_the_bell_when_the_role_is_gone():
    body = _client(_db(flags=ALL_FLAGS), role="member").get("/api/v1/notifications").json()
    assert "team-1" not in [item["report_id"] for item in body["items"]]
    assert body["unread"] == 1


def test_activity_appears_only_with_its_flag():
    body = _client(_db(flags=ALL_FLAGS)).get("/api/v1/notifications").json()
    assert [item["memo_id"] for item in body["activity"]] == ["m-1"]


def test_unreadable_activity_is_null_not_empty():
    body = _client(_db(flags=ALL_FLAGS, fail_tables=("crm_updates",))).get("/api/v1/notifications").json()
    assert body["activity"] is None
    assert body["items"]


# ---------- team report reads ----------


def _team_db():
    return FakeDB({
        "reports": [_report("team-1", user_id=USER, scope="team", report_type="weekly")],
        "report_notifications": [],
    })


def test_the_admin_recipient_reads_the_team_report():
    response = _client(_team_db(), role="admin").get("/api/v1/reports/team-1")
    assert response.status_code == 200
    assert response.json()["scope"] == "team"


def test_a_demoted_recipient_cannot_read_the_team_report():
    response = _client(_team_db(), role="member").get("/api/v1/reports/team-1")
    assert response.status_code == 404
    assert "metrics" not in response.text


def test_another_admin_of_the_company_is_not_the_recipient():
    assert _client(_team_db(), role="admin", user_id=OTHER).get("/api/v1/reports/team-1").status_code == 404


def test_an_admin_of_another_company_cannot_read_it():
    response = _client(_team_db(), role="admin", company_id=OTHER_COMPANY).get("/api/v1/reports/team-1")
    assert response.status_code == 404
