"""GET /memos filters by channel (interaction_kind) and type (sales_motion_key); the memo carries its
type; the web voice-memo upload can store a voice note."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-filters-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-filters-32")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import memos as memos_api
from app.api.router import api_router
from app.deps import get_supabase, get_user_id
from tests.postgrest_or import matches

USER = "rep-1"


def _uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _row(n: int, **extra) -> dict:
    return {
        "id": _uuid(n),
        "user_id": USER,
        "audio_url": "",
        "audio_duration": 60,
        "status": "approved",
        "created_at": f"2026-09-2{n}T10:00:00+00:00",
        **extra,
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name):
        self.store, self.name, self.filters = store, name, []
        self.payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: row.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda row: row.get(column) in set(values))
        return self

    def or_(self, expression):
        self.filters.append(lambda row: matches(expression, row))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def offset(self, _n):
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.payload is not None:
            self.store.inserted.append(dict(self.payload))
            return _Result([{**self.payload, "id": _uuid(99)}])
        rows = [r for r in self.store.tables.get(self.name, []) if all(f(r) for f in self.filters)]
        return _Result(rows)


class _Store:
    def __init__(self, *rows):
        self.tables = {"memos": list(rows)}
        self.inserted: list[dict] = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def _viewer(monkeypatch):
    monkeypatch.setattr(memos_api, "load_viewer_scope", lambda _s, _u: (None, [], {}))


def _client(store) -> TestClient:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_user_id] = lambda: USER
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def _ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return sorted(item["id"] for item in response.json())


def _mixed_store() -> _Store:
    return _Store(
        _row(1, interaction_kind="voice_note"),
        _row(2, interaction_kind="visit"),
        _row(3, source="whatsapp"),  # legacy: no stored kind, a visit by origin
        _row(4, source="vocify_call"),  # legacy call
        _row(5, source_type="meeting_transcript"),  # legacy meeting
    )


def test_list_memos_filters_by_channel_including_unstamped_rows():
    client = _client(_mixed_store())
    assert _ids(client.get("/api/v1/memos?interaction_kind=visit")) == [_uuid(2), _uuid(3)]
    assert _ids(client.get("/api/v1/memos?interaction_kind=voice_note")) == [_uuid(1)]
    assert _ids(client.get("/api/v1/memos?interaction_kind=call")) == [_uuid(4)]
    assert _ids(client.get("/api/v1/memos?interaction_kind=meeting")) == [_uuid(5)]


def test_list_memos_without_the_filters_is_unchanged():
    assert len(_ids(_client(_mixed_store()).get("/api/v1/memos"))) == 5


def test_list_memos_rejects_unknown_interaction_kind():
    assert _client(_mixed_store()).get("/api/v1/memos?interaction_kind=fax").status_code == 422


def test_list_memos_filters_by_sales_motion_key():
    store = _Store(
        _row(1, sales_motion_key="discovery"),
        _row(2, sales_motion_key="internal"),
        _row(3),
    )
    assert _ids(_client(store).get("/api/v1/memos?sales_motion_key=internal")) == [_uuid(2)]


def test_list_memos_channel_and_type_compose():
    store = _Store(
        _row(1, interaction_kind="visit", sales_motion_key="discovery"),
        _row(2, interaction_kind="visit", sales_motion_key="internal"),
        _row(3, interaction_kind="call", sales_motion_key="internal"),
    )
    response = _client(store).get("/api/v1/memos?interaction_kind=visit&sales_motion_key=internal")
    assert _ids(response) == [_uuid(2)]


def test_memo_exposes_sales_motion_key():
    body = memos_api._memo_from_row(_row(1, sales_motion_key="discovery")).model_dump(mode="json")
    assert body["salesMotionKey"] == "discovery"
    assert memos_api._memo_from_row(_row(2)).salesMotionKey is None


def _upload(client, **data):
    return client.post(
        "/api/v1/memos/upload",
        files={"audio": ("note.webm", b"x", "audio/webm")},
        data={"transcript": "Hola, hablé con el cliente.", **data},
    )


@pytest.fixture
def _upload_stubs(monkeypatch):
    async def fake_specs(*_a, **_k):
        return []

    async def fake_sanitize(text, *_a, **_k):
        return text

    async def fake_start(*_a, **_k):
        return None

    monkeypatch.setattr(memos_api, "_curated_field_specs_for_primary_crm", fake_specs)
    monkeypatch.setattr("app.services.transcript_sanitize.sanitize_user_transcript", fake_sanitize)
    monkeypatch.setattr(memos_api, "start_extraction_from_transcript", fake_start)


def test_upload_stores_voice_note_kind(_upload_stubs):
    store = _Store()
    response = _upload(_client(store), interaction_kind="voice_note")
    assert response.status_code == 200, response.text
    assert store.inserted[0]["interaction_kind"] == "voice_note"
    assert store.inserted[0]["source_type"] == "voice_memo"


def test_upload_without_a_kind_is_unchanged(_upload_stubs):
    store = _Store()
    assert _upload(_client(store)).status_code == 200
    assert store.inserted[0]["interaction_kind"] == "call"  # derived, as before


def test_upload_rejects_unknown_kind(_upload_stubs):
    store = _Store()
    assert _upload(_client(store), interaction_kind="fax").status_code == 422
    assert store.inserted == []


# The web recorder creates its memo from the live transcript through these two (JSON body).
TRANSCRIPT_PATHS = ("/api/v1/memos/upload-transcript", "/api/v1/memos/upload-and-extract")


@pytest.mark.parametrize("path", TRANSCRIPT_PATHS)
def test_transcript_uploads_store_voice_note_kind(_upload_stubs, path):
    store = _Store()
    response = _client(store).post(path, json={"transcript": "Hola, hablé con el cliente.", "interaction_kind": "voice_note"})
    assert response.status_code == 200, response.text
    assert store.inserted[0]["interaction_kind"] == "voice_note"
    assert store.inserted[0]["source_type"] == "voice_memo"


@pytest.mark.parametrize("path", TRANSCRIPT_PATHS)
def test_transcript_uploads_without_a_kind_are_unchanged(_upload_stubs, path):
    store = _Store()
    assert _client(store).post(path, json={"transcript": "Hola, hablé con el cliente."}).status_code == 200
    assert store.inserted[0]["interaction_kind"] == "call"  # derived, as before


@pytest.mark.parametrize("path", TRANSCRIPT_PATHS)
def test_transcript_uploads_reject_unknown_kind(_upload_stubs, path):
    store = _Store()
    assert _client(store).post(path, json={"transcript": "Hola.", "interaction_kind": "fax"}).status_code == 422
    assert store.inserted == []
