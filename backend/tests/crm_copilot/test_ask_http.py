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
    ask_api._OPERATIONS.clear()
    ask_api.set_ask_store(None)
    ask_api.set_ask_transcriber(None)
    ask_api.set_ask_reader(None)
    ask_api.set_ask_loop(None)


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
                    "replayed": False,
                }
                return self.saved
            return {**self.saved, "replayed": True}

        def persist_turn(self, **kwargs):
            del kwargs

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


def test_confirming_another_contact_writes_nothing_and_a_repeat_does_not_apply_twice():
    from app.api.ask import remember_operation

    remember_operation(
        "user-a",
        "conv-1",
        {
            "operation_id": "op-1",
            "revision": 3,
            "contact_id": "contact-a",
            "applied": False,
            "status": "proposed",
        },
    )
    client = _client("user-a")
    wrong = client.post(
        "/api/v1/ask/conversations/conv-1/operations/op-1/confirm",
        json={"revision": 3, "contact_id": "contact-b"},
    )
    assert wrong.status_code == 409
    assert ask_api._OPERATIONS[("user-a", "conv-1", "op-1")]["applied"] is False
    first = client.post(
        "/api/v1/ask/conversations/conv-1/operations/op-1/confirm",
        json={"revision": 3, "contact_id": "contact-a"},
    )
    second = client.post(
        "/api/v1/ask/conversations/conv-1/operations/op-1/confirm",
        json={"revision": 3, "contact_id": "contact-a"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "succeeded"
    assert first.json()["applied"] is True
    assert second.json()["replayed"] is True
    assert second.json()["operation_id"] == "op-1"
    stranger = _client("user-b")
    assert stranger.post(
        "/api/v1/ask/conversations/conv-1/operations/op-1/confirm",
        json={"revision": 3, "contact_id": "contact-a"},
    ).status_code == 404


def test_a_forbidden_read_is_not_the_same_as_no_results():
    def forbidden(_text: str) -> dict:
        return {"items": [], "coverage": "forbidden", "reason": "email_scope_missing"}

    def empty(_text: str) -> dict:
        return {"items": [], "coverage": "complete"}

    ask_api.set_ask_reader(forbidden)
    try:
        client = _client("user-a")
        denied = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-forbid", "text": "¿Qué correos hay?"},
        )
        assert denied.status_code == 200
        assert denied.json()["coverage"] == "forbidden"
        assert denied.json()["item_count"] == 0
        fetched = client.get(
            f"/api/v1/ask/conversations/conv-1/turns/{denied.json()['turn_id']}"
        )
        assert fetched.json()["coverage"] == "forbidden"
    finally:
        ask_api.set_ask_reader(None)

    ask_api.set_ask_reader(empty)
    try:
        client = _client("user-a")
        none = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-empty", "text": "¿Qué correos hay?"},
        )
        assert none.status_code == 200
        assert none.json()["coverage"] == "complete"
        assert none.json()["item_count"] == 0
        assert none.json()["turn_id"] != denied.json()["turn_id"]
    finally:
        ask_api.set_ask_reader(None)


def test_voice_transcription_returns_text_and_creates_no_memo():
    import base64

    seen = {}

    async def transcribe(raw: bytes, **kwargs):
        seen["source"] = kwargs.get("source")
        seen["size"] = len(raw)
        return "¿Qué quedó pendiente con Marina?"

    ask_api.set_ask_transcriber(transcribe)
    try:
        client = _client("user-a")
        response = client.post(
            "/api/v1/ask/transcribe",
            json={"audio_base64": base64.b64encode(b"audio-bytes").decode("ascii")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "¿Qué quedó pendiente con Marina?"
        assert body["memo_id"] is None
        assert seen["source"] == "ask_voice"
        assert seen["size"] == len(b"audio-bytes")
        silent = client.post(
            "/api/v1/ask/transcribe",
            json={"audio_base64": base64.b64encode(b"quiet").decode("ascii")},
        )
    finally:
        ask_api.set_ask_transcriber(None)

    async def blank(raw: bytes, **kwargs):
        del raw, kwargs
        return "   "

    ask_api.set_ask_transcriber(blank)
    try:
        client = _client("user-a")
        silent = client.post(
            "/api/v1/ask/transcribe",
            json={"audio_base64": base64.b64encode(b"quiet").decode("ascii")},
        )
        assert silent.status_code == 200
        assert silent.json()["text"] == ""
        assert silent.json()["memo_id"] is None
    finally:
        ask_api.set_ask_transcriber(None)


def test_the_web_turn_runs_the_loop_once_and_keeps_an_empty_read():
    calls = []

    async def loop(text: str) -> dict:
        calls.append(text)
        return {"text": "Marina queda el jueves.", "envelope": {"items": [], "coverage": "complete"}}

    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        first = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-loop", "text": "¿Qué sigue?"},
        )
        second = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-loop", "text": "otra"},
        )
        assert first.status_code == 200
        assert first.json()["text"] == "Marina queda el jueves."
        assert first.json()["coverage"] == "complete"
        assert first.json()["item_count"] == 0
        assert second.json()["text"] == "Marina queda el jueves."
        assert second.json()["turn_id"] == first.json()["turn_id"]
        assert calls == ["¿Qué sigue?"]
    finally:
        ask_api.set_ask_loop(None)


def test_a_proposed_confirmation_can_be_confirmed_for_that_contact_only():
    calls = []

    async def loop(_text: str, confirm=None):
        calls.append(confirm)
        if confirm:
            return {"text": "Nota creada"}
        return {
            "text": "¿Creo la nota?",
            "confirmation": {
                "operation_id": "op-9",
                "revision": 2,
                "contact_id": "contact-a",
            },
        }

    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        created = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-confirm", "text": "anota esto"},
        )
        assert created.status_code == 200
        assert created.json()["confirmation"]["contact_id"] == "contact-a"
        wrong = client.post(
            "/api/v1/ask/conversations/conv-1/operations/op-9/confirm",
            json={"revision": 2, "contact_id": "contact-b"},
        )
        assert wrong.status_code == 409
        assert calls == [None]
        right = client.post(
            "/api/v1/ask/conversations/conv-1/operations/op-9/confirm",
            json={"revision": 2, "contact_id": "contact-a"},
        )
        assert right.status_code == 200
        assert right.json()["applied"] is True
        assert right.json()["text"] == "Nota creada"
        repeat = client.post(
            "/api/v1/ask/conversations/conv-1/operations/op-9/confirm",
            json={"revision": 2, "contact_id": "contact-a"},
        )
        assert repeat.json()["replayed"] is True
        assert calls == [None, True]
    finally:
        ask_api.set_ask_loop(None)


def test_a_choices_turn_returns_both_labels_in_the_public_payload():
    async def loop(_text: str) -> dict:
        return {
            "text": "¿Cuál Marina?",
            "choices": [
                {"id": "c1", "label": "Marina López"},
                {"id": "c2", "label": "Marina Ruiz"},
            ],
        }

    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        response = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-choices", "text": "busca Marina"},
        )
        assert response.status_code == 200
        body = response.json()
        assert [row["label"] for row in body["choices"]] == ["Marina López", "Marina Ruiz"]
        fetched = client.get(f"/api/v1/ask/conversations/conv-1/turns/{body['turn_id']}")
        assert "choices" in fetched.json()
    finally:
        ask_api.set_ask_loop(None)


def test_supabase_store_persists_a_finished_turn_and_replay_skips_the_loop():
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
            turn_id = f"turn-{len(self.db.rows) + 1}"
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

    calls = []

    async def loop(_text: str) -> dict:
        calls.append(_text)
        return {
            "text": "Marina queda el jueves.",
            "choices": [{"id": "c1", "label": "Marina López"}],
        }

    ask_api.set_ask_store(SupabaseAskStore(FakeSupabase()))
    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        first = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-db", "text": "¿Qué sigue?"},
        )
        second = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-db", "text": "otra"},
        )
        assert first.status_code == 200
        assert first.json()["text"] == "Marina queda el jueves."
        assert first.json()["choices"][0]["label"] == "Marina López"
        assert second.status_code == 200
        assert second.json()["turn_id"] == first.json()["turn_id"]
        assert second.json()["text"] == "Marina queda el jueves."
        assert calls == ["¿Qué sigue?"]
        fetched = client.get(
            f"/api/v1/ask/conversations/conv-1/turns/{first.json()['turn_id']}"
        )
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["status"] == "completed"
        assert body["text"] == "Marina queda el jueves."
        assert body["choices"][0]["id"] == "c1"
    finally:
        ask_api.set_ask_store(None)
        ask_api.set_ask_loop(None)


def test_a_failed_loop_leaves_the_turn_pending():
    async def loop(_text: str):
        return None

    ask_api.set_ask_loop(loop)
    try:
        client = _client("user-a")
        response = client.post(
            "/api/v1/ask/conversations/conv-1/turns",
            json={"client_turn_id": "web-fail", "text": "¿Qué sigue?"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        assert response.json()["text"] == "¿Qué sigue?"
    finally:
        ask_api.set_ask_loop(None)
