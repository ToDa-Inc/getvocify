"""F04 against the payloads HubSpot and Pipedrive actually return, not invented properties."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-shapes-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-shapes-32b")

import json
from datetime import datetime, timedelta, timezone

import httpx
from httpx import MockTransport, Request, Response

from app.services.hoy.assigned import collect_assigned, connection_assigned_fetch
from app.services.hoy.context import (
    build_priority_page,
    fold_context,
    maybe_refresh_assigned_context,
    snapshot_from_rows,
)

COMPANY = "co-1"
ANA = "user-ana"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
OBSERVED = "2026-09-22T10:00:00Z"
MEMBERS = [{"user_id": ANA, "email": "Ana@Vocify.test", "name": "Ana"}]


def _hubspot_connection() -> dict:
    return {"id": "crm-A", "provider": "hubspot", "access_token": "tok", "status": "connected"}


def _pipedrive_connection() -> dict:
    return {
        "id": "crm-B",
        "provider": "pipedrive",
        "access_token": "tok",
        "status": "connected",
        "metadata": {"api_domain": "https://acme.pipedrive.com"},
    }


def _fetch(connection: dict, handler) -> callable:
    return connection_assigned_fetch(connection, client=httpx.Client(transport=MockTransport(handler)))


def _page_for_ana(page: dict) -> dict:
    rows = fold_context(company_id=COMPANY, pages=[page], members=MEMBERS)
    return build_priority_page(
        snapshot=snapshot_from_rows(rows, connected=True),
        user_id=ANA,
        role="member",
        now=NOW,
    )


def test_hubspot_owner_and_last_contact_come_from_real_properties():
    searches: list[dict] = []

    def handler(request: Request) -> Response:
        if request.url.path == "/crm/v3/owners":
            return Response(200, json={"results": [
                {"id": "101", "email": "ana@vocify.test"},
                {"id": "202", "email": "someone@else.test"},
            ]})
        body = json.loads(request.content)
        searches.append(body)
        return Response(200, json={"results": [
            {"id": "42", "properties": {
                "hubspot_owner_id": "101",
                "notes_last_contacted": "2026-09-10T08:00:00.000Z",
                "firstname": "Marta",
                "lastname": "Ruiz",
            }},
            {"id": "43", "properties": {"hubspot_owner_id": "101", "notes_last_contacted": None}},
        ]})

    page = collect_assigned(
        "hubspot",
        _fetch(_hubspot_connection(), handler),
        connection_id="crm-A",
        observed_at=OBSERVED,
        member_emails={"ana@vocify.test"},
    )
    owner_filter = searches[0]["filterGroups"][0]["filters"][0]
    assert owner_filter == {"propertyName": "hubspot_owner_id", "operator": "IN", "values": ["101"]}
    assert "notes_last_contacted" in searches[0]["properties"]
    assert page["coverage"] == "complete"

    listed = _page_for_ana(page)
    by_id = {item["contact_id"]: item for item in listed["items"]}
    assert by_id["42"]["contact_name"] == "Marta Ruiz"
    assert by_id["42"]["never_called"] is False
    assert by_id["43"]["never_called"] is True
    assert by_id["43"]["reason"] == "no_calls_logged"


def test_hubspot_with_no_member_among_owners_is_an_empty_assignment_without_searching():
    paths: list[str] = []

    def handler(request: Request) -> Response:
        paths.append(request.url.path)
        return Response(200, json={"results": [{"id": "202", "email": "someone@else.test"}]})

    page = collect_assigned(
        "hubspot",
        _fetch(_hubspot_connection(), handler),
        connection_id="crm-A",
        observed_at=OBSERVED,
        member_emails={"ana@vocify.test"},
    )
    assert paths == ["/crm/v3/owners"]
    assert page["items"] == []
    assert page["coverage"] == "complete"


def test_pipedrive_integer_owner_resolves_through_users_and_done_activities_mean_contacted():
    persons_params: list[dict] = []

    def handler(request: Request) -> Response:
        if request.url.path == "/api/v1/users":
            return Response(200, json={"success": True, "data": [
                {"id": 4, "email": "ana@vocify.test", "active_flag": True},
                {"id": 5, "email": "someone@else.test", "active_flag": True},
            ]})
        persons_params.append(dict(request.url.params))
        return Response(200, json={"success": True, "data": [
            {"id": 7, "name": "Luis Gil", "owner_id": 4, "done_activities_count": 0},
            {"id": 8, "name": "Eva Sanz", "owner_id": 4, "done_activities_count": 3},
        ], "additional_data": {"next_cursor": None}})

    page = collect_assigned(
        "pipedrive",
        _fetch(_pipedrive_connection(), handler),
        connection_id="crm-B",
        observed_at=OBSERVED,
        member_emails={"ana@vocify.test"},
    )
    assert persons_params[0]["owner_id"] == "4"
    assert "done_activities_count" in persons_params[0]["include_fields"]

    listed = _page_for_ana(page)
    by_id = {item["contact_id"]: item for item in listed["items"]}
    assert by_id["7"]["never_called"] is True
    assert by_id["8"]["never_called"] is False


def test_a_contact_without_owner_is_in_nobodys_personal_list():
    rows = [{
        "company_id": COMPANY,
        "connection_id": "crm-A",
        "contact_id": "42",
        "deal_id": "",
        "owner_user_id": None,
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": OBSERVED,
        "payload": {"last_call_at": None, "contacted": False},
    }]
    for role in ("member", "admin"):
        page = build_priority_page(
            snapshot=snapshot_from_rows(rows, connected=True),
            user_id=ANA,
            role=role,
            now=NOW,
        )
        assert page["items"] == []


def test_an_expired_token_is_not_a_missing_scope():
    def expired(_request: Request) -> Response:
        return Response(401, json={"message": "expired"})

    def denied(_request: Request) -> Response:
        return Response(403, json={"message": "missing scopes"})

    for handler, coverage, reason in ((expired, "unavailable", "auth_expired"), (denied, "forbidden", "email_scope_missing")):
        page = collect_assigned(
            "hubspot",
            _fetch(_hubspot_connection(), handler),
            connection_id="crm-A",
            observed_at=OBSERVED,
            member_emails={"ana@vocify.test"},
        )
        assert page["coverage"] == coverage
        assert page["reason"] == reason


class _Table:
    def __init__(self):
        self.upserts: list = []

    def upsert(self, payload, on_conflict=None):
        self.upserts.append(payload)
        return self

    def execute(self):
        return None


class _Supabase:
    def __init__(self):
        self.context = _Table()

    def table(self, _name):
        return self.context


def _cached_row(observed_at: str) -> dict:
    return {
        "company_id": COMPANY,
        "connection_id": "crm-A",
        "contact_id": "42",
        "deal_id": "",
        "owner_user_id": ANA,
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": observed_at,
        "payload": {"last_call_at": None, "contacted": False},
    }


def _stamp(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_a_stale_cache_is_read_again_and_a_fresh_one_is_not():
    calls: list[str] = []

    def handler(request: Request) -> Response:
        calls.append(request.url.path)
        if request.url.path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        return Response(200, json={"results": [
            {"id": "42", "properties": {"hubspot_owner_id": "101", "notes_last_contacted": "2026-09-22T09:30:00Z"}},
        ]})

    def factory(connection):
        return _fetch(connection, handler)

    fresh = [_cached_row(_stamp(NOW - timedelta(minutes=5)))]
    rows, _hint = maybe_refresh_assigned_context(
        _Supabase(), COMPANY, _hubspot_connection(), fresh, MEMBERS,
        observed_at=_stamp(NOW), fetch_factory=factory,
    )
    assert calls == []
    assert rows == fresh

    stale = [_cached_row(_stamp(NOW - timedelta(hours=2)))]
    rows, _hint = maybe_refresh_assigned_context(
        _Supabase(), COMPANY, _hubspot_connection(), stale, MEMBERS,
        observed_at=_stamp(NOW), fetch_factory=factory,
    )
    assert "/crm/v3/objects/contacts/search" in calls
    assert rows[0]["payload"]["last_call_at"] == "2026-09-22T09:30:00Z"
    assert rows[0]["observed_at"] == _stamp(NOW)
