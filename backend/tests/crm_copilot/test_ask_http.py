"""Ask HTTP: 202 while pending, and a repeated client turn is the same turn."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ask as ask_api
from app.deps import get_membership
from app.services.company import Membership


def _client(user_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(ask_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id=user_id, role="member", status="active",
    )
    return TestClient(app)


def setup_function():
    ask_api._TURNS.clear()
    ask_api.set_ask_store(None)


def test_a_stored_turn_replays_the_same_id_for_the_callers_company():
    class Store:
        def __init__(self):
            self.companies = []
            self.saved = None

        def save_turn(self, *, user_id, company_id, conversation_id, client_turn_id, text):
            self.companies.append(company_id)
            if self.saved is None:
                self.saved = {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "turn_id": "turn-db",
                    "status": "pending",
                    "client_turn_id": client_turn_id,
                    "text": text,
                }
            return self.saved

        def get_turn(self, *, user_id, conversation_id, turn_id):
            if (
                not self.saved
                or self.saved["user_id"] != user_id
                or self.saved["turn_id"] != turn_id
                or self.saved["conversation_id"] != conversation_id
            ):
                return None
            return self.saved

    store = Store()
    ask_api.set_ask_store(store)
    try:
        client = _client("user-a")
        first = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-2", "text": "¿Qué sigue?"},
        )
        second = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-2", "text": "otra"},
        )
        assert first.status_code == 202
        assert first.json()["turn_id"] == second.json()["turn_id"] == "turn-db"
        assert second.json()["text"] == "¿Qué sigue?"
        assert store.companies == ["co-1", "co-1"]
        fetched = client.get("/api/v1/ask/conversations/conv-1/turns/turn-db")
        assert fetched.status_code == 200
        stranger = _client("user-b")
        assert stranger.get("/api/v1/ask/conversations/conv-1/turns/turn-db").status_code == 404
    finally:
        ask_api.set_ask_store(None)


def test_pending_turn_is_accepted_and_replay_keeps_the_same_id():
    client = _client("user-a")
    body = {"client_turn_id": "web-2", "text": "¿Qué sigue con Marina?"}
    first = client.post("/api/v1/ask/conversations/conv-1/turns", json=body)
    second = client.post("/api/v1/ask/conversations/conv-1/turns", json={**body, "text": "otra"})
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["turn_id"] == second.json()["turn_id"]
    assert second.json()["text"] == "¿Qué sigue con Marina?"
    assert "delta" not in first.json()
    fetched = client.get(f"/api/v1/ask/conversations/conv-1/turns/{first.json()['turn_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["client_turn_id"] == "web-2"


def test_another_user_cannot_read_the_turn():
    owner = _client("user-a")
    created = owner.post(
        "/api/v1/ask/conversations/conv-1/turns",
        json={"client_turn_id": "web-2", "text": "privado"},
    )
    stranger = _client("user-b")
    hidden = stranger.get(f"/api/v1/ask/conversations/conv-1/turns/{created.json()['turn_id']}")
    assert hidden.status_code == 404
