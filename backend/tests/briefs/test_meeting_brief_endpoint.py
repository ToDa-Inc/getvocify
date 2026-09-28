"""GET /briefs/meeting (T6): the AE's pre-meeting brief end to end."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meeting-brief")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meeting-brief")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import briefs as briefs_api
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.eqs, self.ins = [], []
        self.n = None

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

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        rows = [row for row in self.db.tables.get(self.name, []) if all(row.get(c) == v for c, v in self.eqs)]
        rows = [row for row in rows if all(row.get(c) in v for c, v in self.ins)]
        return SimpleNamespace(data=rows[: self.n] if self.n else rows)


class _Db:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self, name)


def _get(db, membership=None, **params):
    app = FastAPI()
    app.include_router(briefs_api.router)
    app.dependency_overrides[get_membership] = lambda: membership or Membership(
        id="m", company_id="co-1", user_id="ae-1", role="member", status="active", sales_role="ae",
    )
    app.dependency_overrides[get_supabase] = lambda: db
    query = {"connection_id": "crm-A", "contact_id": "42", **params}
    return TestClient(app).get("/api/v1/briefs/meeting", params=query)


def _isolate():
    feature_flags.clear_cache()
    briefs_api.set_brief_tasks(None)


def test_flag_off_is_not_found():
    _isolate()
    db = _Db({"company_feature_flags": []})
    response = _get(db)
    assert response.status_code == 404
    feature_flags.clear_cache()


def test_flag_on_returns_the_brief_with_the_handoff_sdr_included_and_named():
    _isolate()
    db = _Db({
        "company_feature_flags": [
            {"company_id": "co-1", "flag": "HOY_AE_DEALS_ENABLED", "enabled": True},
            {"company_id": "co-1", "flag": "HANDOFF_ENABLED", "enabled": True},
        ],
        "deal_handoffs": [{
            "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42",
            "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
        }],
        "memos": [{
            "id": "m1", "company_id": "co-1", "user_id": "sdr-1", "hubspot_contact_id": "42",
            "hubspot_deal_id": None, "matched_deal_id": None,
            "created_at": "2026-09-20T10:00:00Z", "capture_started_at": "2026-09-20T10:00:00Z",
            "playbook_version_id": None, "sales_motion_key": "discovery",
            "extraction": {"summary": "Primera llamada, buen fit"},
        }],
        "user_profiles": [{"id": "sdr-1", "full_name": "Marina (SDR)"}],
        "company_members": [
            {"user_id": "ae-1", "company_id": "co-1", "role": "member", "visibility": "own", "status": "active"},
            {"user_id": "sdr-1", "company_id": "co-1", "role": "member", "visibility": "own", "status": "active"},
        ],
        "playbooks": [],
    })
    try:
        response = _get(db)
        assert response.status_code == 200, response.text
        body = response.json()
    finally:
        feature_flags.clear_cache()
    assert body["interactions"][0]["author"] == "Marina (SDR)"
    assert body["interactions"][0]["text"] == "Primera llamada, buen fit"
    assert body["open_items"] == {"objections": [], "commitments": [], "missing_playbook_steps": []}


def test_a_sdr_who_never_handed_this_contact_off_is_excluded():
    _isolate()
    db = _Db({
        "company_feature_flags": [
            {"company_id": "co-1", "flag": "HOY_AE_DEALS_ENABLED", "enabled": True},
            {"company_id": "co-1", "flag": "HANDOFF_ENABLED", "enabled": True},
        ],
        "deal_handoffs": [],
        "memos": [{
            "id": "m1", "company_id": "co-1", "user_id": "other-sdr", "hubspot_contact_id": "42",
            "hubspot_deal_id": None, "matched_deal_id": None,
            "created_at": "2026-09-20T10:00:00Z", "capture_started_at": "2026-09-20T10:00:00Z",
            "playbook_version_id": None, "sales_motion_key": "discovery",
            "extraction": {"summary": "No debería verse"},
        }],
        "user_profiles": [],
        "company_members": [],
        "playbooks": [],
    })
    try:
        response = _get(db)
        assert response.status_code == 200, response.text
        body = response.json()
    finally:
        feature_flags.clear_cache()
    assert body["interactions"] == []
