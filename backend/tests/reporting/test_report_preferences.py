"""F13.04: preferences only expose the reports that apply to this person and company."""

import os

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
from tests.reporting.fake_db import FakeDB

COMPANY = "88888888-8888-8888-8888-888888888888"
USER = "99999999-9999-9999-9999-999999999999"


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _db(**flags) -> FakeDB:
    return FakeDB({
        "report_preferences": [],
        "company_feature_flags": [
            {"company_id": COMPANY, "flag": name, "enabled": value} for name, value in flags.items()
        ],
    })


def _client(db: FakeDB, role: str = "member") -> TestClient:
    app = FastAPI()
    app.include_router(reports_api.router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER, role=role, status="active",
    )
    return TestClient(app)


def test_flags_off_only_offer_the_daily_summary_on_by_default():
    body = _client(_db()).get("/api/v1/me/report-preferences").json()
    assert body == {"daily": True}


def test_weekly_flag_adds_the_weekly_summary():
    body = _client(_db(REPORTING_WEEKLY_ENABLED=True)).get("/api/v1/me/report-preferences").json()
    assert body == {"daily": True, "weekly": True}


def test_team_report_preference_is_only_for_owner_or_admin():
    db = _db(REPORTING_TEAM_ENABLED=True)
    assert _client(db, "admin").get("/api/v1/me/report-preferences").json() == {"daily": True, "team": True}
    assert _client(db, "owner").get("/api/v1/me/report-preferences").json() == {"daily": True, "team": True}
    assert _client(db, "member").get("/api/v1/me/report-preferences").json() == {"daily": True}


def test_put_stores_the_change_and_returns_the_applicable_keys():
    db = _db(REPORTING_WEEKLY_ENABLED=True)
    client = _client(db)
    body = client.put("/api/v1/me/report-preferences", json={"weekly": False}).json()
    assert body == {"daily": True, "weekly": False}
    assert db.tables["report_preferences"][0]["user_id"] == USER
    assert db.tables["report_preferences"][0]["weekly_enabled"] is False
    assert client.get("/api/v1/me/report-preferences").json() == {"daily": True, "weekly": False}


def test_put_keeps_values_it_does_not_mention():
    db = _db(REPORTING_WEEKLY_ENABLED=True)
    client = _client(db)
    client.put("/api/v1/me/report-preferences", json={"daily": False})
    client.put("/api/v1/me/report-preferences", json={"weekly": False})
    assert client.get("/api/v1/me/report-preferences").json() == {"daily": False, "weekly": False}


def test_put_rejects_a_report_that_does_not_apply():
    assert _client(_db(REPORTING_TEAM_ENABLED=True), "member").put(
        "/api/v1/me/report-preferences", json={"team": False},
    ).status_code == 422
    assert _client(_db()).put("/api/v1/me/report-preferences", json={"weekly": False}).status_code == 422


def test_put_rejects_unknown_keys_and_non_booleans():
    client = _client(_db())
    assert client.put("/api/v1/me/report-preferences", json={"hour": 9}).status_code == 422
    assert client.put("/api/v1/me/report-preferences", json={"daily": "yes"}).status_code == 422
