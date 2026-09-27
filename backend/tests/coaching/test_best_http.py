"""T11: GET /coaching/best, gated by PLAYBOOK_TAB_ENABLED, open to any active member."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-coaching-best-http-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-coaching-best-http-32")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import coaching as coaching_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from tests.reporting.fake_db import FakeDB

COMPANY = "77777777-7777-7777-7777-777777777777"
REP = "88888888-8888-8888-8888-888888888888"
OTHER_REP = "66666666-6666-6666-6666-666666666666"


@pytest.fixture(autouse=True)
def fresh_flags():
    from app.services import feature_flags

    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _memo(memo_id: str, *, user_id: str = REP, motion: str = "discovery", at: str = "2026-09-22T10:00:00+00:00") -> dict:
    return {
        "id": memo_id,
        "user_id": user_id,
        "company_id": COMPANY,
        "sales_motion_key": motion,
        "capture_started_at": at,
        "created_at": at,
        "extraction": {"intelligence": {"evidence": [{"start_ms": 2000, "label": "Cita destacada"}]}},
    }


def _score(memo_id: str, value: float) -> dict:
    return {"memo_id": memo_id, "score": {"value": value}, "revision_seq": 1}


def _client(*, memos, scores, flags=None) -> TestClient:
    app = FastAPI()
    app.include_router(coaching_api.router)
    store = FakeDB({
        "company_feature_flags": flags or [],
        "memos": memos,
        "memo_scores": scores,
        "company_members": [
            {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
            {"company_id": COMPANY, "user_id": OTHER_REP, "role": "member", "status": "active"},
        ],
    })
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=REP, role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def test_flag_off_is_not_found():
    client = _client(memos=[_memo("m1")], scores=[_score("m1", 8)])
    response = client.get("/api/v1/coaching/best")
    assert response.status_code == 404


def test_flag_on_returns_top_three_per_flow_for_any_member():
    memos = [_memo("m1", motion="discovery"), _memo("m2", user_id=OTHER_REP, motion="closing")]
    scores = [_score("m1", 8), _score("m2", 9)]
    flags = [{"company_id": COMPANY, "flag": "PLAYBOOK_TAB_ENABLED", "enabled": True}]
    client = _client(memos=memos, scores=scores, flags=flags)
    body = client.get("/api/v1/coaching/best?week=2026-09-22T10:00:00Z").json()
    assert [item["memo_id"] for item in body["sdr"]] == ["m1"]
    assert [item["memo_id"] for item in body["ae"]] == ["m2"]
    assert body["sdr"][0]["value"] == 8
    assert body["sdr"][0]["highlights"] == ["min 00:02 · Cita destacada"]


def test_unscored_memo_does_not_appear():
    flags = [{"company_id": COMPANY, "flag": "PLAYBOOK_TAB_ENABLED", "enabled": True}]
    client = _client(memos=[_memo("m1")], scores=[], flags=flags)
    body = client.get("/api/v1/coaching/best?week=2026-09-22T10:00:00Z").json()
    assert body["sdr"] == []


def test_week_param_selects_a_different_madrid_week():
    memos = [_memo("m-this-week", at="2026-09-22T10:00:00+00:00")]
    scores = [_score("m-this-week", 8)]
    flags = [{"company_id": COMPANY, "flag": "PLAYBOOK_TAB_ENABLED", "enabled": True}]
    client = _client(memos=memos, scores=scores, flags=flags)
    other_week = client.get("/api/v1/coaching/best?week=2026-09-15T10:00:00Z").json()
    this_week = client.get("/api/v1/coaching/best?week=2026-09-22T10:00:00Z").json()
    assert other_week["sdr"] == []
    assert [item["memo_id"] for item in this_week["sdr"]] == ["m-this-week"]
