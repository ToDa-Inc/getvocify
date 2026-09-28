"""T3: POST/GET /handoffs. Flag off -> 404. An AE cannot call it (403). needs_ae/self_owned/
invalid_ae as 409. Idempotent create. The CRM owner effect only runs behind its own flag.
An unknown connection_id is 404, an empty contact_id is 422, and omitting connection_id
resolves the company's single connected CRM (like F14's accept.py)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-handoffs-32c")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-handoffs-32c")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import handoffs as api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership

COMPANY = "co-handoff"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._filters = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            row = {"id": f"row-{len(rows) + 1}", **self._payload}
            rows.append(row)
            return _Result([row])
        if self._mode == "update":
            updated = []
            for row in rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
                    updated.append(dict(row))
            return _Result(updated)
        filtered = list(rows)
        for c, v in self._filters:
            filtered = [row for row in filtered if row.get(c) == v]
        return _Result(filtered)


class _Supabase:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return _Query(self.tables, name)


def _membership(*, sales_role=None, handoff_ae_user_id=None, user_id="sdr-1"):
    return Membership(
        id="member-1",
        company_id=COMPANY,
        user_id=user_id,
        role="member",
        status="active",
        sales_role=sales_role,
        handoff_ae_user_id=handoff_ae_user_id,
    )


STORE = _Supabase()
MEMBERSHIP = _membership(sales_role="sdr", handoff_ae_user_id="ae-1")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_supabase] = lambda: STORE
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    return TestClient(app)


def setup_function():
    global MEMBERSHIP
    STORE.tables = {
        "company_members": [
            {"user_id": "ae-1", "company_id": COMPANY, "sales_role": "ae", "status": "active"},
            {"user_id": "sdr-2", "company_id": COMPANY, "sales_role": "sdr", "status": "active"},
        ],
        "crm_connections": [
            # No access_token: found (not 404), but the CRM-owner-effect writer can't be
            # built from it - proves "skipped" is "no usable connection", not "no row".
            {"id": "conn-1", "company_id": COMPANY, "provider": "hubspot", "status": "connected", "access_token": ""},
        ],
    }
    MEMBERSHIP = _membership(sales_role="sdr", handoff_ae_user_id="ae-1")
    feature_flags.clear_cache()
    settings.HANDOFF_ENABLED = True
    settings.HANDOFF_CRM_OWNER_ENABLED = False


def teardown_function():
    settings.HANDOFF_ENABLED = False
    settings.HANDOFF_CRM_OWNER_ENABLED = False


def test_flag_off_is_404():
    settings.HANDOFF_ENABLED = False
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1"})
    assert response.status_code == 404


def test_an_ae_cannot_hand_off():
    global MEMBERSHIP
    MEMBERSHIP = _membership(sales_role="ae")
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1"})
    assert response.status_code == 403


def test_sdr_without_an_ae_auto_picks_the_sole_active_ae():
    """Lista 3: setup_function's fixture company has exactly one active AE ('ae-1'), so
    an unrouted SDR with no explicit choice still gets a handoff."""
    global MEMBERSHIP
    MEMBERSHIP = _membership(sales_role="sdr", handoff_ae_user_id=None)
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1"})
    assert response.status_code == 200
    assert response.json()["ae_user_id"] == "ae-1"


def test_sdr_without_an_ae_still_gets_needs_ae_with_two_active_aes():
    global MEMBERSHIP
    MEMBERSHIP = _membership(sales_role="sdr", handoff_ae_user_id=None)
    STORE.tables["company_members"].append(
        {"user_id": "ae-3", "company_id": COMPANY, "sales_role": "ae", "status": "active"}
    )
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "needs_ae"


def test_general_without_a_route_is_self_owned():
    global MEMBERSHIP
    MEMBERSHIP = _membership(sales_role="general", handoff_ae_user_id=None)
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_owned"


def test_unknown_connection_is_404():
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-missing"})
    assert response.status_code == 404


def test_empty_contact_id_is_422():
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "", "connection_id": "conn-1"})
    assert response.status_code == 422


def test_connection_id_omitted_resolves_the_companys_connected_crm():
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1"})
    assert response.status_code == 200
    assert response.json()["created"] is True
    assert STORE.tables["deal_handoffs"][0]["connection_id"] == "conn-1"


def test_general_naming_themselves_is_self_owned():
    global MEMBERSHIP
    MEMBERSHIP = _membership(sales_role="general", handoff_ae_user_id=None, user_id="gen-1")
    client = _client()
    response = client.post(
        "/api/v1/handoffs",
        json={"contact_id": "c1", "connection_id": "conn-1", "ae_user_id": "gen-1"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_owned"


def test_invalid_ae_is_409():
    client = _client()
    response = client.post(
        "/api/v1/handoffs",
        json={"contact_id": "c1", "connection_id": "conn-1", "ae_user_id": "sdr-2"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_ae"


def test_create_is_idempotent():
    client = _client()
    first = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1", "deal_id": "d1"})
    assert first.status_code == 200
    body = first.json()
    assert body["created"] is True
    assert body["ae_user_id"] == "ae-1"

    replay = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1", "deal_id": "d1"})
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["id"] == body["id"]


def test_crm_owner_effect_only_runs_behind_its_own_flag():
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1", "deal_id": "d1"})
    assert response.json()["crm_owner_status"] is None
    assert STORE.tables["deal_handoffs"][0].get("crm_owner_status") is None


def test_crm_owner_effect_skipped_without_a_connected_crm():
    settings.HANDOFF_CRM_OWNER_ENABLED = True
    client = _client()
    response = client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1", "deal_id": "d1"})
    assert response.json()["crm_owner_status"] == "skipped"


def test_get_handoffs_lists_active_rows_for_the_caller():
    client = _client()
    client.post("/api/v1/handoffs", json={"contact_id": "c1", "connection_id": "conn-1"})

    global MEMBERSHIP
    ae_membership = _membership(sales_role="ae", user_id="ae-1")
    MEMBERSHIP = ae_membership
    ae_client = _client()
    response = ae_client.get("/api/v1/handoffs", params={"role": "ae"})
    assert response.status_code == 200
    assert len(response.json()["handoffs"]) == 1

    response = ae_client.get("/api/v1/handoffs", params={"role": "sdr"})
    assert response.json()["handoffs"] == []
