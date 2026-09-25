"""GET/POST follow-up: a manager may read, only the author may hand off."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import followup as followup_api
from app.deps import get_supabase, get_user_id

AUTHOR = "11111111-1111-1111-1111-111111111111"
MANAGER = "22222222-2222-2222-2222-222222222222"
MEMO_ID = "33333333-3333-3333-3333-333333333333"
EXTRACTION = {
    "summary": "Resumen",
    "contactName": "Marina",
    "contactEmail": "marina@tenes.io",
    "contactPhone": "+34 600 111 222",
}


class Store:
    def __init__(self):
        self.followup = None
        self.samples = ["hola"]

    def table(self, name):
        query = MagicMock()
        if name == "memos":
            def update(patch):
                self.followup = patch["followup"]
                query.execute.return_value = SimpleNamespace(data=[patch])
                return query
            query.update.side_effect = update
        if name == "user_profiles":
            query.execute.return_value = SimpleNamespace(data=[{"writing_samples": list(self.samples)}])
            def update(patch):
                self.samples = patch["writing_samples"]
                return query
            query.update.side_effect = update
        query.eq.return_value = query
        query.limit.return_value = query
        query.select.return_value = query
        return query


def client_for(user_id: str, memo: dict, store: Store) -> TestClient:
    app = FastAPI()
    app.include_router(followup_api.router)
    app.dependency_overrides[get_supabase] = lambda: store
    app.dependency_overrides[get_user_id] = lambda: user_id
    followup_api._require_readable_memo = lambda *_a, **_k: memo
    return TestClient(app)


def ready_memo():
    return {
        "id": MEMO_ID,
        "user_id": AUTHOR,
        "transcript": "Marina: hola",
        "extraction": EXTRACTION,
        "screening_outcome": None,
        "followup": {"status": "ready", "subject": "Caso", "body": "Hola Marina, te paso el caso."},
    }


def test_manager_reads_the_draft_and_cannot_hand_it_off():
    memo = ready_memo()
    store = Store()
    reader = client_for(MANAGER, memo, store)
    got = reader.get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert got.status_code == 200
    assert got.json()["status"] == "ready"
    assert got.json()["subject"] == "Caso"
    denied = reader.post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "subject": "Caso", "body": "Hola Marina, te paso el caso."},
    )
    assert denied.status_code == 403
    assert store.followup is None


def test_author_handoff_is_sent_and_an_unready_draft_conflicts():
    memo = ready_memo()
    store = Store()
    author = client_for(AUTHOR, memo, store)
    sent = author.post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "subject": "", "body": "Hola Marina, te paso el caso."},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "sent"
    assert body["channel"] == "email"
    assert "entregado" not in body.get("body", "").lower()
    assert store.followup["status"] == "sent"

    pending = {**memo, "followup": {"status": "generating"}}
    again = client_for(AUTHOR, pending, Store())
    conflict = again.post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "body": "Hola"},
    )
    assert conflict.status_code == 409


def test_missing_draft_without_a_running_generation_is_unavailable():
    memo = {
        "id": MEMO_ID,
        "user_id": AUTHOR,
        "transcript": "   ",
        "extraction": EXTRACTION,
        "followup": None,
    }
    got = client_for(AUTHOR, memo, Store()).get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert got.status_code == 200
    assert got.json()["status"] == "unavailable"
    assert UUID(MEMO_ID)
