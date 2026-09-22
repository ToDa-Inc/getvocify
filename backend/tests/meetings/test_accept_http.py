"""POST meeting-proposal/accept: one CRM create, replay is idempotent, omit skips create."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meetings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meetings-32")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import meetings as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership

MEMO = "66666666-6666-6666-6666-666666666666"
COMPANY = "co-accept"
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
    def __init__(self, store, table: str):
        self._store = store
        self._table = table
        self._filters: list[tuple[str, object]] = []
        self._payload = None
        self._mode = "select"

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n: int):
        return self

    def update(self, payload: dict):
        self._mode = "update"
        self._payload = payload
        return self

    def upsert(self, payload: dict, on_conflict: str | None = None):
        del on_conflict
        self._mode = "upsert"
        self._payload = payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "update":
            updated = []
            for row in rows:
                if all(row.get(col) == val for col, val in self._filters):
                    row.update(self._payload or {})
                    updated.append(dict(row))
            return _Result(updated)
        if self._mode == "upsert":
            key = (self._payload or {}).get("operation_key")
            replaced = False
            for row in rows:
                if row.get("operation_key") == key:
                    row.update(self._payload or {})
                    replaced = True
            if not replaced:
                rows.append(dict(self._payload or {}))
            return _Result([self._payload])
        filtered = list(rows)
        for col, val in self._filters:
            filtered = [row for row in filtered if row.get(col) == val]
        return _Result(filtered)


class _Supabase:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name: str):
        return _Query(self.tables, name)


class FakeWriter:
    def __init__(self):
        self.created: list[str] = []
        self.reconcile_result: str | None = None

    def create(self, operation_key: str, proposal: dict) -> str:
        del proposal
        self.created.append(operation_key)
        return "act-fake-1"

    def reconcile(self, _operation_key: str):
        return self.reconcile_result

    def change_stage(self, _mapping: str) -> None:
        return None


WRITER = FakeWriter()
STORE = _Supabase()


def setup_function():
    WRITER.created.clear()
    WRITER.reconcile_result = None
    STORE.tables = {
        "memos": [
            {
                "id": MEMO,
                "company_id": COMPANY,
                "hubspot_contact_id": "42",
                "hubspot_deal_id": None,
                "matched_deal_id": None,
            }
        ],
        "meeting_proposals": [dict(PROPOSAL_ROW)],
        "meeting_writes": [],
        "crm_connections": [
            {
                "company_id": COMPANY,
                "provider": "hubspot",
                "status": "connected",
                "access_token": "pat-test",
            }
        ],
    }
    api.set_meeting_writer_factory(lambda _conn, _memo, _row: WRITER)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m",
        company_id=COMPANY,
        user_id="user-1",
        role="member",
        status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: STORE
    return TestClient(app)


def test_get_returns_the_stored_proposal_for_memo_review():
    client = _client()
    response = client.get(f"/api/v1/memos/{MEMO}/meeting-proposal")
    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["proposal_id"] == "meet-1"
    assert body["proposal"]["decision"] == "pending"
    assert body["proposal"]["crm_status"] == "not_requested"


def test_get_returns_null_when_no_proposal_row():
    STORE.tables["meeting_proposals"] = []
    client = _client()
    response = client.get(f"/api/v1/memos/{MEMO}/meeting-proposal")
    assert response.status_code == 200
    assert response.json()["proposal"] is None


def test_accept_once_replay_does_not_create_second_remote_id():
    client = _client()
    body = {"decision": "accept", "proposal_id": "meet-1"}
    first = client.post(f"/api/v1/memos/{MEMO}/meeting-proposal/accept", json=body)
    assert first.status_code == 200
    assert first.json()["crm_status"] == "succeeded"
    assert first.json()["remote_id"] == "act-fake-1"
    assert WRITER.created == [f"{MEMO}:meet-1:rev-1"]

    second = client.post(f"/api/v1/memos/{MEMO}/meeting-proposal/accept", json=body)
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["remote_id"] == "act-fake-1"
    assert len(WRITER.created) == 1


def test_omit_does_not_call_create():
    client = _client()
    response = client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/accept",
        json={"decision": "omit", "proposal_id": "meet-1"},
    )
    assert response.status_code == 200
    assert response.json()["crm_status"] == "not_requested"
    assert WRITER.created == []
    assert response.json()["proposal"]["decision"] == "omitted"


def _seed_uncertain_write() -> str:
    op_key = f"{MEMO}:meet-1:rev-1"
    STORE.tables["meeting_proposals"] = [
        {**PROPOSAL_ROW, "decision": "accepted", "crm_status": "uncertain", "remote_id": None}
    ]
    STORE.tables["meeting_writes"] = [
        {
            "operation_key": op_key,
            "memo_id": MEMO,
            "proposal_id": "meet-1",
            "remote_id": None,
            "crm_status": "uncertain",
        }
    ]
    return op_key


def test_reconcile_uncertain_finds_remote_id_without_create():
    _seed_uncertain_write()
    WRITER.reconcile_result = "act-recovered"
    client = _client()
    response = client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/reconcile",
        json={"proposal_id": "meet-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["crm_status"] == "succeeded"
    assert body["remote_id"] == "act-recovered"
    assert WRITER.created == []
    assert STORE.tables["meeting_writes"][0]["remote_id"] == "act-recovered"


def test_reconcile_uncertain_stays_uncertain_without_create():
    _seed_uncertain_write()
    client = _client()
    response = client.post(
        f"/api/v1/memos/{MEMO}/meeting-proposal/reconcile",
        json={"proposal_id": "meet-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["crm_status"] == "uncertain"
    assert body["remote_id"] is None
    assert WRITER.created == []
