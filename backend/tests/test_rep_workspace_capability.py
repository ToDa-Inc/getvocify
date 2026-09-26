"""F16 · T1: REP_WORKSPACE_ENABLED reaches the frontend as a company capability, per company."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-rep-workspace-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-rep-workspace-32")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import auth as auth_api  # noqa: E402
from app.api import company as company_api  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import get_supabase, get_user_id  # noqa: E402
from app.services import feature_flags  # noqa: E402

FLAG = "REP_WORKSPACE_ENABLED"
COMPANY = "co-rep-1"
OTHER_COMPANY = "co-rep-2"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, tables, name):
        self._tables = tables
        self._name = name
        self._eq: list[tuple[str, object]] = []
        self._single = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._eq.append((column, value))
        return self

    def is_(self, *_args):
        return self

    def gt(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = list(self._tables.get(self._name, []))
        for column, value in self._eq:
            rows = [row for row in rows if row.get(column) == value]
        if self._single:
            return _Result(rows[0] if rows else None)
        return _Result(rows, count=len(rows))


class _Supabase:
    def __init__(self, flag_rows=()):
        self.tables = {
            "user_profiles": [
                {"id": USER, "full_name": "Marina Ortiz", "created_at": "2026-01-01T00:00:00Z"}
            ],
            "company_members": [
                {
                    "id": "m-1",
                    "company_id": COMPANY,
                    "user_id": USER,
                    "role": "member",
                    "status": "active",
                }
            ],
            "companies": [{"id": COMPANY, "name": "Kinetic Software", "seat_limit": 5}],
            "company_invitations": [],
            "company_billing": [],
            "company_feature_flags": list(flag_rows),
        }

    def table(self, name):
        return _Query(self.tables, name)


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _client(store: _Supabase) -> TestClient:
    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(company_api.router)
    app.dependency_overrides[get_user_id] = lambda: USER
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def _me_company(store: _Supabase) -> dict:
    response = _client(store).get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    return response.json()["company"]


def _company(store: _Supabase) -> dict:
    response = _client(store).get("/api/v1/company")
    assert response.status_code == 200, response.text
    return response.json()


def _row(company_id: str, enabled: bool) -> dict:
    return {"company_id": company_id, "flag": FLAG, "enabled": enabled}


def test_flag_is_off_globally_by_default():
    assert settings.REP_WORKSPACE_ENABLED is False


@pytest.mark.parametrize("global_value", [True, False])
def test_company_row_on_turns_the_capability_on(monkeypatch, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    store = _Supabase([_row(COMPANY, True)])
    assert _me_company(store)["rep_workspace_enabled"] is True
    assert _company(store)["rep_workspace_enabled"] is True


@pytest.mark.parametrize("global_value", [True, False])
def test_company_row_off_turns_the_capability_off(monkeypatch, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    store = _Supabase([_row(COMPANY, False)])
    assert _me_company(store)["rep_workspace_enabled"] is False
    assert _company(store)["rep_workspace_enabled"] is False


def test_global_default_without_a_company_row_is_off():
    store = _Supabase([_row(OTHER_COMPANY, True)])
    assert _me_company(store)["rep_workspace_enabled"] is False
    assert _company(store)["rep_workspace_enabled"] is False


def test_flag_off_leaves_the_rest_of_the_summary_as_it_was():
    store = _Supabase()
    assert _me_company(store) == {
        "id": COMPANY,
        "name": "Kinetic Software",
        "role": "member",
        "seat_limit": 5,
        "seats_used": 1,
        "seats_pending": 0,
        "access_mode": "open",
        "billing_status": "none",
        "plan_type": None,
        "paywalled": False,
        "can_use_dialer": True,
        "rep_workspace_enabled": False,
    }
    assert _company(store) == {
        "id": COMPANY,
        "name": "Kinetic Software",
        "seat_limit": 5,
        "seats_used": 1,
        "seats_pending": 0,
        "seats_active": 1,
        "seats_available": 4,
        "role": "member",
        "access_mode": "open",
        "billing_status": "none",
        "plan_type": None,
        "billing_interval": None,
        "paywalled": False,
        "can_use_dialer": True,
        "rep_workspace_enabled": False,
    }


def test_turning_the_flag_off_mid_session_shows_on_a_later_auth_me(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(feature_flags, "_now", lambda: now[0])
    store = _Supabase([_row(COMPANY, True)])
    assert _me_company(store)["rep_workspace_enabled"] is True
    store.tables["company_feature_flags"] = [_row(COMPANY, False)]
    now[0] += feature_flags.TTL_SECONDS + 1
    assert _me_company(store)["rep_workspace_enabled"] is False
