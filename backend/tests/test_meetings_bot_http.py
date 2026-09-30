"""T14: POST /api/v1/meetings/bot. Flag off -> 404. No RECALL_API_KEY -> 503. A Recall
API error is a 502, not a 500. A successful create reserves the capture (D1: capture_id
is the reserved memo id, C01) with source_type=recall_bot."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

from unittest.mock import patch

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import meetings as api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership

COMPANY = "co-recall-bot"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store, self._table = store, table
        self._filters = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        self._mode, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            row = {"id": f"row-{len(rows) + 1}", **self._payload}
            rows.append(row)
            return _Result([row])
        if self._mode == "update":
            updated = []
            for row in rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
                    updated.append(dict(row))
            return _Result(updated)
        filtered = list(rows)
        for c, v in self._filters:
            filtered = [row for row in filtered if row.get(c) == v]
        return _Result(filtered)


class _Supabase:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return _Query(self.tables, name)


STORE = _Supabase()
MEMBERSHIP = Membership(
    id="member-1", company_id=COMPANY, user_id="rep-1", role="member", status="active", sales_role="general"
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_supabase] = lambda: STORE
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    return TestClient(app)


def setup_function():
    STORE.tables = {}
    feature_flags.clear_cache()
    settings.RECALL_BOT_ENABLED = True
    settings.RECALL_API_KEY = "key-1"


def teardown_function():
    settings.RECALL_BOT_ENABLED = False
    settings.RECALL_API_KEY = None


def test_flag_off_is_404():
    settings.RECALL_BOT_ENABLED = False
    client = _client()
    response = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://zoom.us/j/1"})
    assert response.status_code == 404


def test_no_api_key_is_503():
    settings.RECALL_API_KEY = None
    client = _client()
    response = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://zoom.us/j/1"})
    assert response.status_code == 503


@respx.mock
def test_recall_error_is_502_not_500():
    respx.post("https://eu-central-1.recall.ai/api/v1/bot/").mock(return_value=httpx.Response(422, text="bad url"))
    client = _client()
    response = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://zoom.us/j/1"})
    assert response.status_code == 502


def test_a_non_allowed_meeting_url_is_422():
    client = _client()
    response = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://evil.example/j/1"})
    assert response.status_code == 422


def test_a_non_https_meeting_url_is_422():
    client = _client()
    response = client.post("/api/v1/meetings/bot", json={"meeting_url": "http://zoom.us/j/1"})
    assert response.status_code == 422


@respx.mock
def test_successful_create_reserves_the_capture():
    respx.post("https://eu-central-1.recall.ai/api/v1/bot/").mock(
        return_value=httpx.Response(201, json={"id": "bot-77", "status": "joining_call"})
    )
    client = _client()
    response = client.post(
        "/api/v1/meetings/bot",
        json={"meeting_url": "https://zoom.us/j/123", "contact_id": "contact-9"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bot_id"] == "bot-77"
    assert body["memo_id"] == body["capture_id"]

    memo = STORE.tables["memos"][0]
    assert memo["client_capture_id"] == "recall:bot-77"
    assert memo["source_type"] == "recall_bot"
    assert memo["interaction_kind"] == "meeting"
    assert memo["hubspot_contact_id"] == "contact-9"


@respx.mock
def test_a_reserve_failure_deletes_the_orphan_bot_and_returns_502():
    respx.post("https://eu-central-1.recall.ai/api/v1/bot/").mock(
        return_value=httpx.Response(201, json={"id": "bot-orphan"})
    )
    delete_route = respx.delete("https://eu-central-1.recall.ai/api/v1/bot/bot-orphan/").mock(
        return_value=httpx.Response(204)
    )
    # An empty client_capture_id makes reserve_recall_capture's underlying
    # reserve_capture raise (400), simulating any reservation failure.
    with patch("app.services.meetings.recall_bot.client_capture_id_for_bot", return_value=""):
        client = _client()
        response = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://zoom.us/j/1"})
    assert response.status_code == 502
    assert delete_route.called
    assert STORE.tables.get("memos", []) == []


@respx.mock
def test_a_retry_with_the_same_meeting_reuses_the_same_bot_capture_when_ids_match():
    """Recall issues a fresh bot_id per create_bot call, so this is really about the
    reservation itself being keyed by bot_id (idempotent per bot, T3-style)."""
    respx.post("https://eu-central-1.recall.ai/api/v1/bot/").mock(
        return_value=httpx.Response(201, json={"id": "bot-1"})
    )
    client = _client()
    first = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://zoom.us/j/1"}).json()
    second = client.post("/api/v1/meetings/bot", json={"meeting_url": "https://zoom.us/j/1"}).json()
    assert first["memo_id"] == second["memo_id"]
    assert len(STORE.tables["memos"]) == 1
