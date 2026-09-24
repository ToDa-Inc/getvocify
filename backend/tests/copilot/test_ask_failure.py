"""Ask HTTP: a loop that returns nothing ends the turn as failed."""

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
    ask_api._OPERATIONS.clear()
    ask_api.set_ask_store(None)
    ask_api.set_ask_transcriber(None)
    ask_api.set_ask_reader(None)
    ask_api.set_ask_loop(None)


def test_a_failed_ask_loop_ends_the_turn():
    from app.services.crm_copilot.web_sessions import SupabaseAskStore

    class _Result:
        def __init__(self, data):
            self.data = data

    class _FakeTable:
        def __init__(self, db):
            self.db = db
            self._filters = []
            self._payload = None

        def select(self, _cols):
            return self

        def update(self, payload):
            self._payload = payload
            return self

        def eq(self, col, val):
            self._filters.append((col, val))
            return self

        def limit(self, _n):
            return self

        def execute(self):
            if self._payload is not None:
                turn_id = next(v for c, v in self._filters if c == "id")
                row = self.db.rows[turn_id]
                row.update(self._payload)
                return _Result([dict(row)])
            turn_id = next(v for c, v in self._filters if c == "id")
            user_id = next(v for c, v in self._filters if c == "user_id")
            conversation_id = next(v for c, v in self._filters if c == "conversation_id")
            row = self.db.rows.get(turn_id)
            if not row or row["user_id"] != user_id or row["conversation_id"] != conversation_id:
                return _Result([])
            return _Result([dict(row)])

    class _FakeRPC:
        def __init__(self, db, params):
            self.db = db
            self.params = params

        def execute(self):
            key = (
                self.params["p_user"],
                self.params["p_conversation"],
                self.params["p_client_turn"],
            )
            existing = self.db.by_client.get(key)
            if existing:
                row = self.db.rows[existing]
                return _Result([{"turn_id": existing, "body": row["body"], "replayed": True}])
            turn_id = "turn-fail"
            self.db.rows[turn_id] = {
                "id": turn_id,
                "user_id": self.params["p_user"],
                "conversation_id": self.params["p_conversation"],
                "client_turn_id": self.params["p_client_turn"],
                "status": "pending",
                "body": self.params["p_text"],
            }
            self.db.by_client[key] = turn_id
            return _Result(
                [{"turn_id": turn_id, "body": self.params["p_text"], "replayed": False}]
            )

    class FakeSupabase:
        def __init__(self):
            self.rows = {}
            self.by_client = {}

        def rpc(self, _name, params):
            return _FakeRPC(self, params)

        def table(self, _name):
            return _FakeTable(self)

    async def loop(_text: str):
        return None

    ask_api.set_ask_store(SupabaseAskStore(FakeSupabase()))
    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        response = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-fail", "text": "¿Qué sigue?"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        fetched = client.get("/api/v1/ask/conversations/conv-1/turns/turn-fail")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "failed"
    finally:
        ask_api.set_ask_store(None)
        ask_api.set_ask_loop(None)


def test_a_successful_ask_loop_still_completes():
    async def loop(_text: str):
        return {"text": "Marina queda el jueves."}

    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        response = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-ok", "text": "¿Qué sigue?"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
    finally:
        ask_api.set_ask_loop(None)
