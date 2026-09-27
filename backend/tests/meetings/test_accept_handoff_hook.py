"""T3/D6: accepting an F14 meeting proposal creates the SDR->AE handoff when HANDOFF_ENABLED,
and only for an SDR with a usable AE - never for other roles, and never if it fails."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meetings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meetings-32")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import meetings as api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership

MEMO = "77777777-7777-7777-7777-777777777777"
COMPANY = "co-handoff-hook"
PROPOSAL_ROW = {
    "proposal_id": "meet-1",
    "memo_id": MEMO,
    "input_revision": "rev-1",
    "agreement": "agreed",
    "starts_at": "2026-09-29T15:00:00+00:00",
    "timezone": "Europe/Madrid",
    "precision": "exact",
    "decision": "pending",
    "crm_status": "not_requested",
    "remote_id": None,
    "created_at": "2026-09-22T10:00:00Z",
}


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

    def upsert(self, payload, on_conflict=None):
        del on_conflict
        self._mode = "upsert"
        self._payload = payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            row = {"id": f"row-{len(rows) + 1}", **self._payload}
            rows.append(row)
            return _Result([row])
        if self._mode == "upsert":
            key = (self._payload or {}).get("operation_key")
            for row in rows:
                if row.get("operation_key") == key:
                    row.update(self._payload or {})
                    return _Result([self._payload])
            rows.append(dict(self._payload or {}))
            return _Result([self._payload])
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


class FakeWriter:
    def create(self, operation_key, proposal):
        del proposal
        return "act-fake-1"

    def reconcile(self, _operation_key):
        return None

    def change_stage(self, _mapping):
        return False


STORE = _Supabase()
MEMBERSHIP = Membership(
    id="m", company_id=COMPANY, user_id="sdr-1", role="member", status="active",
    sales_role="sdr", handoff_ae_user_id="ae-1",
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    app.dependency_overrides[get_supabase] = lambda: STORE
    return TestClient(app)


def setup_function():
    STORE.tables = {
        "memos": [
            {
                "id": MEMO,
                "company_id": COMPANY,
                "connection_id": "conn-1",
                "hubspot_contact_id": "contact-42",
                "hubspot_deal_id": "deal-9",
                "matched_deal_id": None,
            }
        ],
        "meeting_proposals": [dict(PROPOSAL_ROW)],
        "meeting_writes": [],
        "company_members": [
            {"user_id": "ae-1", "company_id": COMPANY, "sales_role": "ae", "status": "active"},
        ],
        "crm_connections": [],
    }
    api.set_meeting_writer_factory(lambda _conn, _memo, _row: FakeWriter())
    feature_flags.clear_cache()
    settings.HANDOFF_ENABLED = True


def teardown_function():
    settings.HANDOFF_ENABLED = False
    api.set_meeting_writer_factory(None)


def test_accepting_creates_the_handoff_for_an_sdr():
    client = _client()
    response = client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/accept",
        json={"decision": "accept", "proposal_id": "meet-1"},
    )
    assert response.status_code == 200
    handoffs = STORE.tables.get("deal_handoffs") or []
    assert len(handoffs) == 1
    assert handoffs[0]["ae_user_id"] == "ae-1"
    assert handoffs[0]["contact_id"] == "contact-42"
    assert handoffs[0]["deal_id"] == "deal-9"


def test_accepting_twice_does_not_duplicate_the_handoff():
    client = _client()
    body = {"decision": "accept", "proposal_id": "meet-1"}
    client.post(f"/api/v1/memos/{MEMO}/meeting-proposal/accept", json=body)
    client.post(f"/api/v1/memos/{MEMO}/meeting-proposal/accept", json=body)
    assert len(STORE.tables.get("deal_handoffs") or []) == 1


def test_no_handoff_when_the_flag_is_off():
    settings.HANDOFF_ENABLED = False
    client = _client()
    client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/accept",
        json={"decision": "accept", "proposal_id": "meet-1"},
    )
    assert STORE.tables.get("deal_handoffs", []) == []


def test_no_handoff_for_a_non_sdr():
    global MEMBERSHIP
    MEMBERSHIP = Membership(
        id="m", company_id=COMPANY, user_id="ae-2", role="member", status="active",
        sales_role="ae",
    )
    client = _client()
    client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/accept",
        json={"decision": "accept", "proposal_id": "meet-1"},
    )
    assert STORE.tables.get("deal_handoffs", []) == []


def test_no_handoff_when_the_sdr_has_no_ae_routed():
    global MEMBERSHIP
    MEMBERSHIP = Membership(
        id="m", company_id=COMPANY, user_id="sdr-1", role="member", status="active",
        sales_role="sdr", handoff_ae_user_id=None,
    )
    client = _client()
    response = client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/accept",
        json={"decision": "accept", "proposal_id": "meet-1"},
    )
    assert response.status_code == 200
    assert STORE.tables.get("deal_handoffs", []) == []


def test_omit_does_not_create_a_handoff():
    client = _client()
    client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/accept",
        json={"decision": "omit", "proposal_id": "meet-1"},
    )
    assert STORE.tables.get("deal_handoffs", []) == []
