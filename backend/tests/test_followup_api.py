"""GET/POST follow-up: a manager may read, only the author may hand off."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import followup as followup_api
from app.config import settings
from app.deps import get_supabase, get_user_id
from app.services import feature_flags
from app.services import followup as followup_service

AUTHOR = "11111111-1111-1111-1111-111111111111"
MANAGER = "22222222-2222-2222-2222-222222222222"
MEMO_ID = "33333333-3333-3333-3333-333333333333"
EXTRACTION = {
    "summary": "Resumen",
    "contactName": "Marina",
    "contactEmail": "marina@tenes.io",
    "contactPhone": "+34 600 111 222",
}
SAMPLE_A = "Hola Marina, te paso el resumen de lo que vimos esta mañana."
SAMPLE_B = "Buenas, Jorge. Como quedamos, te cuento los tres puntos que me pediste."


def pasted(text):
    return {"text": text, "source": "pasted"}


class Store:
    def __init__(self, flags=()):
        self.followup = None
        self.samples = ["hola"]
        self.flags = list(flags)

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
        if name == "company_feature_flags":
            query.execute.return_value = SimpleNamespace(data=list(self.flags))
        query.eq.return_value = query
        query.limit.return_value = query
        query.select.return_value = query
        return query


@pytest.fixture(autouse=True)
def fresh_flags(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    yield
    feature_flags.clear_cache()


def client_for(user_id: str, memo: dict, store: Store) -> TestClient:
    app = FastAPI()
    app.include_router(followup_api.router)
    app.include_router(followup_api.listing)
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


def pending_memo(company_id: str) -> dict:
    return {**ready_memo(), "company_id": company_id, "followup": None}


def test_followup_off_for_the_company_the_get_does_not_schedule(monkeypatch):
    started = []

    async def fake_ensure(_supabase, memo_id, **_kwargs):
        started.append(memo_id)

    monkeypatch.setattr(followup_service, "ensure_followup", fake_ensure)
    off = Store(flags=[{"company_id": "co-off", "flag": "FOLLOWUP_ENABLED", "enabled": False}])
    got = client_for(AUTHOR, pending_memo("co-off"), off).get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert got.json()["status"] == "unavailable"
    assert started == []

    on = client_for(AUTHOR, pending_memo("co-on"), Store()).get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert on.json()["status"] == "generating", "no company row: the safety net works as today"


def test_rep_saves_up_to_three_trimmed_samples_and_reads_them_back():
    store = Store()
    store.samples = ["aprendido"]
    rep = client_for(AUTHOR, ready_memo(), store)
    saved = rep.put("/api/v1/writing-samples", json={"samples": [f"  {SAMPLE_A}  ", "", SAMPLE_B]})
    assert saved.status_code == 200
    assert saved.json() == {"samples": [SAMPLE_A, SAMPLE_B]}
    assert store.samples == ["aprendido", pasted(SAMPLE_A), pasted(SAMPLE_B)]
    assert rep.get("/api/v1/writing-samples").json() == {"samples": [SAMPLE_A, SAMPLE_B]}


@pytest.mark.parametrize("samples", [[SAMPLE_A] * 4, ["Muy corto"], ["x" * 1501]])
def test_a_fourth_or_badly_sized_sample_is_rejected_and_nothing_changes(samples):
    store = Store()
    store.samples = ["aprendido", pasted(SAMPLE_A)]
    before = list(store.samples)
    rejected = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": samples})
    assert rejected.status_code == 422
    assert store.samples == before


def test_an_oversized_sample_is_rejected_by_the_model_before_anything_is_read():
    store = Store()
    store.samples = ["aprendido"]
    rejected = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": ["x" * 5001]})
    assert rejected.status_code == 422
    assert isinstance(rejected.json()["detail"], list), "pydantic rejected it, not clean_pasted"
    assert store.samples == ["aprendido"]


def test_a_full_sample_with_surrounding_spaces_still_fits():
    store = Store()
    full = "x" * 1500
    saved = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": [f"   {full}\n\n"]})
    assert saved.json() == {"samples": [full]}


def test_emptying_removes_pasted_and_keeps_learned():
    store = Store()
    store.samples = ["aprendido", pasted(SAMPLE_A)]
    cleared = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": []})
    assert cleared.json() == {"samples": []}
    assert store.samples == ["aprendido"]


def test_an_edit_after_pasting_keeps_the_pasted_samples():
    store = Store()
    store.samples = [pasted(SAMPLE_A)]
    edited = "Marina, adjunto la propuesta que te comenté. Nos vemos el jueves. Un abrazo."
    client_for(AUTHOR, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "subject": "Caso", "body": edited},
    )
    assert store.samples == [pasted(SAMPLE_A), edited]
