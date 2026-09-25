"""Brief highlight preference HTTP: per-user storage and validation."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-brief-pref-http-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-brief-pref-http-32")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import brief_preferences as api
from app.deps import get_membership
from app.services.company import Membership
from app.services.coaching import brief_preferences as store


def _client(user_id: str, company_id: str = "co-1") -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m",
        company_id=company_id,
        user_id=user_id,
        role="member",
        status="active",
    )
    return TestClient(app)


def setup_function():
    store._STORE.clear()
    store.set_supabase(None)


def test_member_saves_deferred_and_reads_it_back():
    client = _client("user-1")
    put = client.put(
        "/api/v1/brief-preferences",
        json={"highlight_mode": "deferred"},
    )
    assert put.status_code == 200
    assert put.json() == {
        "highlight_mode": "deferred",
        "delay_minutes": 30,
        "end_of_day": None,
        "timezone": "Europe/Madrid",
    }
    got = client.get("/api/v1/brief-preferences")
    assert got.status_code == 200
    assert got.json() == put.json()


def test_bad_mode_returns_422():
    response = _client("user-2").put(
        "/api/v1/brief-preferences",
        json={"highlight_mode": "later_never"},
    )
    assert response.status_code == 422
