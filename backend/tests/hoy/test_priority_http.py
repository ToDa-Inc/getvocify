"""F04 list: the route selects context rows for the caller's company."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import MockTransport, Request, Response

from app.api import contact_priorities as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.assigned import connection_assigned_fetch, parse_assigned_page
from app.services.hoy.context import fold_context

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
COMPANY = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name: str):
        self._store = store
        self._name = name
        self._rows = store.tables.setdefault(name, [])
        self._filters = []
        self._pending_upsert = None
        self._on_conflict = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def upsert(self, payload, on_conflict=None):
        self._pending_upsert = payload if isinstance(payload, list) else [payload]
        self._on_conflict = on_conflict
        return self

    def execute(self):
        if self._pending_upsert is not None:
            key_fields = (self._on_conflict or "").split(",")
            table = self._store.tables.setdefault(self._name, [])
            for incoming in self._pending_upsert:
                match = None
                for index, existing in enumerate(table):
                    if all(existing.get(field) == incoming.get(field) for field in key_fields if field):
                        match = index
                        break
                if match is None:
                    table.append(dict(incoming))
                else:
                    table[match] = {**table[match], **incoming}
            self._pending_upsert = None
            return _Result([])
        rows = list(self._rows)
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        return _Result(rows)


class _Supabase:
    def __init__(self):
        self.tables = {"crm_connections": [], "contact_priority_context": []}

    def table(self, name):
        return _Query(self, name)


def _client(user_id: str, role: str = "member", company_id: str = "co-1") -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=company_id, user_id=user_id, role=role, status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: STORE
    return TestClient(app)


def _row(**overrides) -> dict:
    row = {
        "company_id": "co-1",
        "connection_id": "crm-A",
        "contact_id": "1",
        "deal_id": "",
        "owner_user_id": "user-a",
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": "2026-09-22T09:00:00Z",
        "payload": {},
    }
    row.update(overrides)
    return row


STORE = _Supabase()


def setup_function():
    STORE.tables = {"crm_connections": [], "contact_priority_context": []}
    api._CLOCK[0] = NOW
    api.set_assigned_fetch_factory(None)
    api.set_fold_members(lambda _supabase, _company_id: [
        {"user_id": "user-a", "email": "ana@vocify.test", "name": "Ana"},
    ])


def test_no_connection_is_not_an_empty_complete_list():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "expired"}]
    STORE.tables["contact_priority_context"] = [
        _row(payload={"pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"}),
    ]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert body["items"] == []
    assert body["coverage"] == "unavailable"
    assert body["title"] == "title_connect_crm"


def test_rows_drive_empty_partial_and_the_personal_list():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "connected", "provider": "hubspot"}]
    STORE.tables["contact_priority_context"] = [_row(
        contact_id="9",
        payload={"meeting_agreed": True, "pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"},
    )]
    empty = _client("user-a").get("/api/v1/contact-priorities").json()
    assert empty["items"] == []
    assert empty["title"] == "title_none_now"
    assert empty["action"] == "open_contacts"

    STORE.tables["contact_priority_context"] = [_row(
        contact_id="8",
        owner_user_id="user-b",
        coverage="partial",
        history_complete=False,
        payload={"last_call_at": None},
    )]
    partial = _client("user-a").get("/api/v1/contact-priorities").json()
    assert partial["items"] == []
    assert partial["title"] == "title_history_partial"
    assert partial["observed_at"] == "2026-09-22T09:00:00Z"

    STORE.tables["contact_priority_context"] = [
        _row(contact_id="1", owner_user_id="user-b", payload={"last_call_at": None}),
        _row(contact_id="2", owner_ambiguous=True, owner_user_id=None, payload={}),
        _row(
            contact_id="42",
            deal_id="deal-7",
            payload={
                "pain_confirmed": True,
                "pain_at": "2026-09-20T10:00:00Z",
                "evidence_refs": ["ev-1"],
                "meeting_agreed": False,
            },
        ),
        _row(company_id="co-2", contact_id="99", payload={"pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"}),
    ]
    page = _client("user-a").get("/api/v1/contact-priorities").json()
    assert [row["contact_id"] for row in page["items"]] == ["42"]
    assert page["items"][0]["reason"] == "pain_agree_next_step"
    assert "Tier" not in page["items"][0]["reason"]


def test_empty_cache_with_hubspot_token_fetches_once_and_cached_rows_skip_crm():
    calls: list[str] = []

    def handler(request: Request) -> Response:
        calls.append(str(request.url))
        return Response(
            200,
            json={
                "results": [{"id": "77", "properties": {"owner_email": "ana@vocify.test", "last_call_at": None}}],
            },
        )

    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "pat-test",
        "metadata": {"portal_id": "123"},
    }]
    http = _client("user-a")
    first = http.get("/api/v1/contact-priorities").json()
    assert len(calls) == 1
    assert "contacts/search" in calls[0]
    assert first["items"][0]["contact_id"] == "77"
    assert STORE.tables["contact_priority_context"]

    calls.clear()
    second = http.get("/api/v1/contact-priorities").json()
    assert calls == []
    assert second["items"][0]["contact_id"] == "77"


def test_forbidden_fetch_is_not_an_empty_complete_list():
    def handler(_request: Request) -> Response:
        return Response(403, json={"message": "denied"})

    client = httpx.Client(transport=MockTransport(handler))
    api.set_assigned_fetch_factory(lambda connection: connection_assigned_fetch(connection, client=client))
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "pat-test",
    }]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert body["items"] == []
    assert body["coverage"] == "forbidden"
    assert body["title"] == "title_history_partial"
    assert STORE.tables["contact_priority_context"] == []


def test_a_folded_unfinished_page_is_what_the_route_returns():
    page = parse_assigned_page(
        "hubspot",
        {
            "results": [{"id": "42", "properties": {"owner_email": "ana@vocify.test"}}],
            "paging": {"next": {"after": "100"}},
        },
        connection_id="crm-A",
        observed_at="2026-09-22T09:00:00Z",
    )
    STORE.tables["crm_connections"] = [{"company_id": COMPANY, "status": "connected"}]
    STORE.tables["contact_priority_context"] = fold_context(
        company_id=COMPANY,
        pages=[page],
        members=[{"user_id": "user-a", "email": "ana@vocify.test"}],
    )
    body = _client("user-a", company_id=COMPANY).get("/api/v1/contact-priorities").json()
    assert body["items"][0]["contact_id"] == "42"
    assert body["items"][0]["never_called"] is False
    assert body["coverage"] == "partial"
    assert body["title"] == "title_history_partial"
