"""Big CRMs: every assigned contact is read, rate limits are waited out, and reassigned contacts leave the cache."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-scale-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-scale-32b")

import httpx
from httpx import MockTransport, Request, Response

from app.services.hoy import assigned
from app.services.hoy.assigned import collect_assigned, connection_assigned_fetch
from app.services.hoy.context import maybe_refresh_assigned_context

OBSERVED = "2026-09-26T09:00:00Z"
HUBSPOT_OWNERS = {"results": [{"id": "101", "email": "ana@vocify.test"}]}
PIPEDRIVE_USERS = {"data": [{"id": 4, "email": "ana@vocify.test"}]}
MEMBERS = [{"user_id": "user-a", "email": "ana@vocify.test", "name": "Ana"}]


def _gt_filter(body: dict) -> str | None:
    for flt in body["filterGroups"][0]["filters"]:
        if flt["propertyName"] == "hs_object_id" and flt["operator"] == "GT":
            return flt["value"]
    return None


def test_hubspot_reads_past_the_ten_thousand_search_cap():
    total = 12_000
    searches: list[dict] = []

    def fetch(request):
        if request["path"] == "/crm/v3/owners":
            return HUBSPOT_OWNERS
        body = request["json"]
        searches.append(body)
        assert "after" not in body
        start = int(_gt_filter(body) or 0)
        ids = range(start + 1, min(start + body["limit"], total) + 1)
        page = {"results": [{"id": str(i), "properties": {"hubspot_owner_id": "101"}} for i in ids]}
        if ids and ids[-1] < total:
            page["paging"] = {"next": {"after": str(len(searches) * body["limit"])}}
        return page

    collected = collect_assigned(
        "hubspot", fetch, connection_id="crm-A", observed_at=OBSERVED, member_emails={"ana@vocify.test"},
    )
    assert collected["coverage"] == "complete"
    assert len(collected["items"]) == total
    assert searches[0]["limit"] == 200
    assert searches[0]["sorts"] == [{"propertyName": "hs_object_id", "direction": "ASCENDING"}]
    assert _gt_filter(searches[1]) == "200"


def test_pipedrive_asks_for_its_largest_page():
    seen: list[dict] = []

    def fetch(request):
        if request["path"] == "/users":
            return PIPEDRIVE_USERS
        seen.append(request["params"])
        return {"data": [{"id": 7, "owner_id": 4}]}

    collect_assigned("pipedrive", fetch, connection_id="crm-B", observed_at=OBSERVED, member_emails={"ana@vocify.test"})
    assert seen[0]["limit"] == 500


def test_a_rate_limit_is_waited_out_then_read(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(assigned, "_sleep", waits.append)
    responses = [Response(429, headers={"Retry-After": "2"}), Response(200, json={"results": []})]
    client = httpx.Client(transport=MockTransport(lambda _request: responses.pop(0)))
    fetch = connection_assigned_fetch({"provider": "hubspot", "access_token": "t"}, client=client)
    assert fetch({"method": "GET", "path": "/crm/v3/owners"}) == {"results": []}
    assert waits == [2.0]


def test_a_rate_limit_that_never_clears_is_unavailable_not_empty(monkeypatch):
    monkeypatch.setattr(assigned, "_sleep", lambda _seconds: None)
    client = httpx.Client(transport=MockTransport(lambda _request: Response(429, headers={"Retry-After": "1"})))
    fetch = connection_assigned_fetch({"provider": "hubspot", "access_token": "t"}, client=client)
    result = collect_assigned("hubspot", fetch, connection_id="crm-A", observed_at=OBSERVED, member_emails={"ana@vocify.test"})
    assert result["coverage"] == "unavailable"
    assert result["reason"] == "rate_limited"
    assert result["items"] == []


class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.filters: list = []
        self.mode = "select"
        self.payload: list = []

    def upsert(self, payload, on_conflict=None):
        self.mode, self.payload, self.keys = "upsert", payload, on_conflict.split(",")
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: row.get(column) == value)
        return self

    def in_(self, column, values):
        allowed = set(values)
        self.filters.append(lambda row: row.get(column) in allowed)
        return self

    def execute(self):
        rows = self.store.setdefault(self.name, [])
        if self.mode == "upsert":
            for incoming in self.payload:
                for index, row in enumerate(rows):
                    if all(row.get(k) == incoming.get(k) for k in self.keys):
                        rows[index] = {**row, **incoming}
                        break
                else:
                    rows.append(dict(incoming))
            return _Result([])
        if self.mode == "delete":
            self.store[self.name] = [row for row in rows if not all(f(row) for f in self.filters)]
            return _Result([])
        return _Result([row for row in rows if all(f(row) for f in self.filters)])


class _Supabase:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return _Table(self.tables, name)


def _cached(contact_id: str, connection_id: str = "crm-A") -> dict:
    return {
        "company_id": "co-1", "connection_id": connection_id, "contact_id": contact_id, "deal_id": "",
        "owner_user_id": "user-a", "owner_ambiguous": False, "coverage": "complete", "history_complete": True,
        "observed_at": "2026-09-25T09:00:00Z", "payload": {"contacted": False},
    }


def _only_contact(contact_ids: list[str]):
    def factory(_connection):
        def fetch(request):
            if request["path"] == "/crm/v3/owners":
                return HUBSPOT_OWNERS
            if _gt_filter(request["json"]):
                return {"results": []}
            return {"results": [{"id": cid, "properties": {"hubspot_owner_id": "101"}} for cid in contact_ids]}
        return fetch
    return factory


def test_a_contact_reassigned_outside_vocify_leaves_the_cache():
    supabase = _Supabase()
    previous = [_cached("1"), _cached("2"), _cached("9", connection_id="crm-old")]
    supabase.tables["contact_priority_context"] = [dict(row) for row in previous]
    rows, hint = maybe_refresh_assigned_context(
        supabase, "co-1", {"id": "crm-A", "provider": "hubspot", "access_token": "t"}, previous, MEMBERS,
        observed_at=OBSERVED, fetch_factory=_only_contact(["1"]),
    )
    assert hint is None
    assert sorted((row["connection_id"], row["contact_id"]) for row in rows) == [("crm-A", "1"), ("crm-old", "9")]
    stored = supabase.tables["contact_priority_context"]
    assert sorted((row["connection_id"], row["contact_id"]) for row in stored) == [("crm-A", "1"), ("crm-old", "9")]


def test_when_every_contact_leaves_the_list_is_empty_not_the_old_cache():
    supabase = _Supabase()
    previous = [_cached("1")]
    supabase.tables["contact_priority_context"] = [dict(previous[0])]
    rows, hint = maybe_refresh_assigned_context(
        supabase, "co-1", {"id": "crm-A", "provider": "hubspot", "access_token": "t"}, previous, MEMBERS,
        observed_at=OBSERVED, fetch_factory=_only_contact([]),
    )
    assert rows == []
    assert hint is None
    assert supabase.tables["contact_priority_context"] == []


def test_an_unfinished_read_keeps_contacts_it_did_not_reach(monkeypatch):
    monkeypatch.setattr(assigned, "_MAX_PAGES", 1)
    supabase = _Supabase()
    previous = [_cached("1"), _cached("2")]
    supabase.tables["contact_priority_context"] = [dict(row) for row in previous]

    def factory(_connection):
        def fetch(request):
            if request["path"] == "/crm/v3/owners":
                return HUBSPOT_OWNERS
            return {"results": [{"id": "1", "properties": {"hubspot_owner_id": "101"}}], "paging": {"next": {"after": "1"}}}
        return fetch

    rows, _hint = maybe_refresh_assigned_context(
        supabase, "co-1", {"id": "crm-A", "provider": "hubspot", "access_token": "t"}, previous, MEMBERS,
        observed_at=OBSERVED, fetch_factory=factory,
    )
    assert sorted(row["contact_id"] for row in rows) == ["1", "2"]
    assert len(supabase.tables["contact_priority_context"]) == 2
