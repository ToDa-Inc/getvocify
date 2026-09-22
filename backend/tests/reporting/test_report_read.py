"""F13 reads: another person's report is hidden, and marking read twice keeps the same time."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-report-read")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-report-read")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import reports as reports_api
from app.deps import get_membership
from app.services.company import Membership

SNAPSHOT = {
    "metrics": {
        "attempts": 2,
        "connected_calls": 1,
        "meetings_agreed": 1,
        "deals_won": None,
        "adherence": None,
    },
    "coverage": {"crm_outcomes": "unavailable"},
    "coaching": None,
}


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name, payload=None):
        self.store = store
        self.name = name
        self.payload = payload
        self.filters = []

    def select(self, *_args, **_kwargs):
        return self

    def update(self, payload):
        return _Query(self.store, self.name, payload)

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        rows = self.store.tables[self.name]
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        if self.payload is None:
            return _Result(rows)
        for row in rows:
            row.update(self.payload)
        return _Result(rows)


class _Store:
    def __init__(self):
        self.tables = {
            "reports": [{
                "id": "report-1",
                "company_id": "co-1",
                "user_id": "user-a",
                "scope": "self",
                "period_start": "2026-09-21T22:00:00Z",
                "report_type": "daily",
                "revision": 1,
                "snapshot": SNAPSHOT,
            }],
            "report_notifications": [{
                "id": "note-1",
                "report_id": "report-1",
                "user_id": "user-a",
                "read_at": None,
            }],
        }

    def table(self, name):
        return _Query(self, name)


STORE = _Store()


def _client(user_id: str, role: str = "member") -> TestClient:
    app = FastAPI()
    app.include_router(reports_api.router)
    app.include_router(reports_api.notifications)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id=user_id, role=role, status="active",
    )
    app.dependency_overrides[__import__("app.deps", fromlist=["get_supabase"]).get_supabase] = lambda: STORE
    return TestClient(app)


def setup_function():
    STORE.tables["report_notifications"][0]["read_at"] = None


def test_a_teammate_cannot_read_a_personal_report_and_the_snapshot_is_unchanged():
    from app.deps import get_supabase

    app = FastAPI()
    app.include_router(reports_api.router)
    app.include_router(reports_api.notifications)
    app.dependency_overrides[get_supabase] = lambda: STORE

    def as_user(user_id, role="member"):
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id=user_id, role=role, status="active",
        )
        return TestClient(app)

    owner = as_user("user-a")
    body = owner.get("/api/v1/reports/report-1").json()
    assert body["snapshot"]["metrics"]["deals_won"] is None
    assert body["snapshot"]["metrics"]["meetings_agreed"] == 1
    assert body["revision"] == 1
    hidden = as_user("user-b", "admin").get("/api/v1/reports/report-1")
    assert hidden.status_code == 404


def test_marking_a_notification_read_twice_keeps_the_first_time():
    from app.deps import get_supabase

    app = FastAPI()
    app.include_router(reports_api.notifications)
    app.dependency_overrides[get_supabase] = lambda: STORE
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    client = TestClient(app)
    reports_api.notifications
    first = client.patch("/api/v1/notifications/note-1")
    second = client.patch("/api/v1/notifications/note-1")
    assert first.status_code == 200
    assert second.json()["read_at"] == first.json()["read_at"]
    stranger = FastAPI()
    stranger.include_router(reports_api.notifications)
    stranger.dependency_overrides[get_supabase] = lambda: STORE
    stranger.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-b", role="member", status="active",
    )
    assert TestClient(stranger).patch("/api/v1/notifications/note-1").status_code == 404
