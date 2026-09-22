"""F04 list: the route selects context rows for the caller's company."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import contact_priorities as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.assigned import parse_assigned_page
from app.services.hoy.context import fold_context

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
COMPANY = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def execute(self):
        rows = self._rows
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        return _Result(rows)


class _Supabase:
    def __init__(self):
        self.tables = {"crm_connections": [], "contact_priority_context": []}

    def table(self, name):
        return _Query(self.tables.setdefault(name, []))


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


def test_no_connection_is_not_an_empty_complete_list():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "expired"}]
    STORE.tables["contact_priority_context"] = [
        _row(payload={"pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"}),
    ]
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert body["items"] == []
    assert body["coverage"] == "unavailable"
    assert body["title"] == "Conecta tu CRM para ver a quién contactar"


def test_rows_drive_empty_partial_and_the_personal_list():
    STORE.tables["crm_connections"] = [{"company_id": "co-1", "status": "connected", "provider": "hubspot"}]
    STORE.tables["contact_priority_context"] = [_row(
        contact_id="9",
        payload={"meeting_agreed": True, "pain_confirmed": True, "pain_at": "2026-09-20T10:00:00Z"},
    )]
    empty = _client("user-a").get("/api/v1/contact-priorities").json()
    assert empty["items"] == []
    assert empty["title"].startswith("No hay contactos prioritarios ahora")
    assert empty["action"] == "Abrir contactos en CRM"

    STORE.tables["contact_priority_context"] = [_row(
        contact_id="8",
        owner_user_id="user-b",
        coverage="partial",
        history_complete=False,
        payload={"last_call_at": None},
    )]
    partial = _client("user-a").get("/api/v1/contact-priorities").json()
    assert partial["items"] == []
    assert partial["title"] == "Falta parte del historial"
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
    assert page["items"][0]["reason"].startswith("Confirmó el problema")
    assert "Tier" not in page["items"][0]["reason"]


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
    assert body["title"] == "Falta parte del historial"
