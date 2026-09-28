"""GET /today `sections` (T6): AE deals, role split, and the lazy handoff close."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-today-sections")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-today-sections")

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.deps import get_membership, get_supabase
from app.services import feature_flags as feature_flags_mod
from app.services.company import Membership

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.eqs, self.ins = [], []
        self._update, self._select = None, None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.eqs.append((column, value))
        return self

    def in_(self, column, values):
        self.ins.append((column, set(values)))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def update(self, payload):
        self._update = payload
        return self

    def _matching(self):
        rows = self.db.tables.get(self.name, [])
        rows = [row for row in rows if all(row.get(c) == v for c, v in self.eqs)]
        return [row for row in rows if all(row.get(c) in v for c, v in self.ins)]

    def execute(self):
        matched = self._matching()
        if self._update is not None:
            for row in matched:
                row.update(self._update)
            return _Result(matched)
        return _Result(matched)


class _Supabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "action_signals": [], "crm_connections": [], "company_feature_flags": [],
            "deal_handoffs": [], "memos": [],
        }

    def table(self, name):
        return _Query(self, name.split("(")[0])


def _client(store, *, user_id="ae-1", sales_role="ae"):
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id=user_id, role="member", status="active", sales_role=sales_role,
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def _flags(**flags):
    return [{"company_id": "co-1", "flag": name, "enabled": value} for name, value in flags.items()]


def _isolate():
    feature_flags_mod.clear_cache()
    today_api.set_today_tasks(None)
    today_api.set_today_fetch(None)


def test_flag_off_never_adds_a_sections_key():
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_AE_DEALS_ENABLED=False)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _client(store).get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        feature_flags_mod.clear_cache()
    assert "sections" not in body


def test_ae_sections_have_no_calls_bucket_and_include_the_active_handoff():
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_AE_DEALS_ENABLED=True, HANDOFF_ENABLED=True)
    store.tables["deal_handoffs"] = [{
        "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42", "deal_id": "d1",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
    }]
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _client(store).get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        feature_flags_mod.clear_cache()
    assert set(body["sections"]) == {"meetings", "deals"}
    assert [item["deal_id"] for item in body["sections"]["deals"]] == ["d1"]
    assert body["sections"]["deals"][0]["reason"] == "Traspasado a ti"


def test_general_sections_have_all_three_buckets():
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_AE_DEALS_ENABLED=True)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _client(store, user_id="gen-1", sales_role=None).get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        feature_flags_mod.clear_cache()
    assert set(body["sections"]) == {"calls", "meetings", "deals"}


def test_sdr_sections_only_have_calls():
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_AE_DEALS_ENABLED=True)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _client(store, user_id="sdr-1", sales_role="sdr").get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        feature_flags_mod.clear_cache()
    assert set(body["sections"]) == {"calls"}


def test_a_handoff_deal_observed_closed_won_leaves_the_section_and_closes_the_handoff():
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_AE_DEALS_ENABLED=True, HANDOFF_ENABLED=True)
    store.tables["deal_handoffs"] = [{
        "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42", "deal_id": "d1",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
    }]
    store.tables["crm_connections"] = [{
        "id": "crm-A", "company_id": "co-1", "status": "connected", "provider": "hubspot",
        "access_token": "tok", "metadata": {},
    }]

    def fake_fetch(request):
        if request["path"] == "/crm/v3/objects/tasks/search":
            return {"results": []}
        assert request["path"] == "/crm/v3/objects/deals/batch/read"
        return {"results": [{"id": "d1", "properties": {"dealstage": "closedwon"}}]}

    today_api.set_today_fetch(fake_fetch)
    try:
        body = _client(store).get("/api/v1/today").json()
    finally:
        today_api.set_today_fetch(None)
        feature_flags_mod.clear_cache()
    assert body["sections"]["deals"] == []
    assert store.tables["deal_handoffs"][0]["status"] == "closed"


def test_an_open_deal_stage_is_never_closed():
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_AE_DEALS_ENABLED=True, HANDOFF_ENABLED=True)
    store.tables["deal_handoffs"] = [{
        "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42", "deal_id": "d1",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
    }]
    store.tables["crm_connections"] = [{
        "id": "crm-A", "company_id": "co-1", "status": "connected", "provider": "hubspot",
        "access_token": "tok", "metadata": {},
    }]

    def fake_fetch(request):
        if request["path"] == "/crm/v3/objects/tasks/search":
            return {"results": []}
        return {"results": [{"id": "d1", "properties": {"dealstage": "appointmentscheduled"}}]}

    today_api.set_today_fetch(fake_fetch)
    try:
        body = _client(store).get("/api/v1/today").json()
    finally:
        today_api.set_today_fetch(None)
        feature_flags_mod.clear_cache()
    assert [item["deal_id"] for item in body["sections"]["deals"]] == ["d1"]
    assert store.tables["deal_handoffs"][0]["status"] == "active"
