"""GET memo brief: preference shapes highlight without mutating the stored brief."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-brief-http-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-brief-http-32b")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import coaching as coaching_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.coaching import brief_preferences as store

MEMO_ID = "88888888-8888-8888-8888-888888888888"
COMPANY_ID = "co-1"
USER_ID = "99999999-9999-9999-9999-999999999999"
READY_AT = "2026-09-22T16:00:00Z"
SECTIONS = [{"kind": "objections", "evidence_refs": ["ev-1"]}]


class BriefStore:
    def __init__(self, *, briefs: list[dict] | None = None):
        self.briefs = briefs or []

    def table(self, name: str):
        query = MagicMock()
        if name == "memos":
            query.execute.return_value = SimpleNamespace(
                data=[{"id": MEMO_ID, "company_id": COMPANY_ID}],
            )
        elif name == "post_interaction_briefs":
            query.execute.return_value = SimpleNamespace(data=list(self.briefs))
        query.eq.return_value = query
        query.select.return_value = query
        return query


def _client(store: BriefStore) -> TestClient:
    app = FastAPI()
    app.include_router(coaching_api.router)
    app.dependency_overrides[get_supabase] = lambda: store
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m",
        company_id=COMPANY_ID,
        user_id=USER_ID,
        role="member",
        status="active",
    )
    return TestClient(app)


def setup_function():
    store._STORE.clear()


def test_changing_preference_updates_highlight_time_on_read():
    row = {
        "revision_seq": 4,
        "status": "ready",
        "input_revision": "rev-4",
        "created_at": READY_AT,
        "body": {
            "input_revision": "rev-4",
            "sections": SECTIONS,
            "audio_available": False,
            "strength": "Nombró el precio",
            "improvement": None,
            "waiting": False,
            "reason": None,
        },
    }
    store.write_preference(USER_ID, {"highlight_mode": "deferred", "timezone": "Europe/Madrid"})
    deferred = _client(BriefStore(briefs=[row])).get(f"/api/v1/memos/{MEMO_ID}/brief").json()
    store.write_preference(USER_ID, {"highlight_mode": "end_of_day", "timezone": "Europe/Madrid"})
    end_of_day = _client(BriefStore(briefs=[row])).get(f"/api/v1/memos/{MEMO_ID}/brief").json()
    assert deferred["highlight"]["highlight_mode"] == "deferred"
    assert end_of_day["highlight"]["highlight_mode"] == "end_of_day"
    assert deferred["highlight"]["highlight_at"] != end_of_day["highlight"]["highlight_at"]


def test_deferred_preference_adds_highlight_without_changing_the_brief():
    store.write_preference(USER_ID, {"highlight_mode": "deferred", "timezone": "Europe/Madrid"})
    row = {
        "revision_seq": 4,
        "status": "ready",
        "input_revision": "rev-4",
        "created_at": READY_AT,
        "body": {
            "input_revision": "rev-4",
            "sections": SECTIONS,
            "audio_available": False,
            "strength": "Nombró el precio",
            "improvement": None,
            "waiting": False,
            "reason": None,
        },
    }
    got = _client(BriefStore(briefs=[row])).get(f"/api/v1/memos/{MEMO_ID}/brief")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "ready"
    assert body["sections"] == SECTIONS
    assert body["highlight"]["highlight_mode"] == "deferred"
    assert body["highlight"]["highlight_at"] == "2026-09-22T16:30:00Z"
    assert body["highlight"]["timezone"] == "Europe/Madrid"


def test_get_brief_uses_the_highest_revision_row():
    older = {
        "revision_seq": 3,
        "status": "ready",
        "input_revision": "rev-3",
        "created_at": READY_AT,
        "body": {
            "input_revision": "rev-3",
            "sections": [],
            "audio_available": False,
            "strength": "Conclusión antigua",
            "improvement": "Mejora antigua",
            "waiting": False,
            "reason": None,
        },
    }
    current = {
        "revision_seq": 4,
        "status": "partial",
        "input_revision": "rev-4",
        "created_at": READY_AT,
        "body": {
            "input_revision": "rev-4",
            "sections": SECTIONS,
            "audio_available": False,
            "strength": None,
            "improvement": None,
            "waiting": False,
            "reason": "score_pending",
        },
    }
    got = _client(BriefStore(briefs=[older, current])).get(f"/api/v1/memos/{MEMO_ID}/brief")
    assert got.status_code == 200
    body = got.json()
    assert body["input_revision"] == "rev-4"
    assert body["status"] == "partial"
    assert body.get("strength") is None
    assert body.get("improvement") is None


def test_not_started_has_no_highlight_at():
    got = _client(BriefStore()).get(f"/api/v1/memos/{MEMO_ID}/brief")
    assert got.status_code == 200
    body = got.json()
    assert body["reason"] == "not_started"
    assert "highlight" not in body
