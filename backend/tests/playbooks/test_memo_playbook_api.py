"""T10 backend: GET/POST /api/v1/memos/{memo_id}/playbook."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.playbook_rules import memo_router
from app.api.playbooks import set_playbook_store
from app.config import settings
from app.deps import get_membership, get_supabase, get_user_id
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.store import MemoryPlaybookStore
from tests.playbooks.live_double import TablesWithLiveView

MEMO = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", True)
    yield
    feature_flags.clear_cache()
    set_playbook_store(None)


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters: list[tuple[str, object]] = []
        self.patch = None

    def select(self, *_a, **_k):
        return self

    def update(self, patch):
        self.patch = patch
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        rows = self.db.tables.get(self.name, [])
        for column, value in self.filters:
            rows = [r for r in rows if str(r.get(column)) == str(value)]
        if self.patch is not None:
            for row in rows:
                row.update(self.patch)
        return type("R", (), {"data": rows})()


class _Db:
    def __init__(self, memo=None, published=("closing", "discovery")):
        self.tables = TablesWithLiveView({
            "memos": [memo] if memo else [],
            "playbooks": [
                {"company_id": "co-1", "sales_motion_key": key, "active_version_id": f"v-{key}"} for key in published
            ],
            "company_feature_flags": [],
        })

    def table(self, name):
        return _Query(self, name)

    @property
    def memo(self):
        return self.tables["memos"][0]


def _memo(**overrides):
    memo = {
        "id": MEMO,
        "company_id": "co-1",
        "user_id": "author",
        "sales_motion_key": "closing",
        "playbook_version_id": "v-closing-old",
        "pipeline_meta": {"stages": [], "playbook_pin": {"source": "rule"}},
        "extraction": {"summary": "s"},
        "transcript": "You: hola",
    }
    memo.update(overrides)
    return memo


def _client(db, *, user="author", role="member", company="co-1", store=None):
    app = FastAPI()
    app.include_router(memo_router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_user_id] = lambda: user
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=company, user_id=user, role=role, status="active",
    )
    set_playbook_store(store or MemoryPlaybookStore(
        {"co-1": {"discovery": "published", "closing": "published", "inbound": "draft", "negotiation": "missing", "renewal": "published"}},
        {},
    ))
    return TestClient(app)


@pytest.fixture
def requeued(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "app.services.memo_extraction_hooks.run_post_extraction_hooks",
        lambda _s, *, memo_id, extraction, memo=None: seen.append(("hooks", dict(memo))),
    )
    monkeypatch.setattr(
        "app.services.intelligence.worker.record_enqueue",
        lambda _s, memo: seen.append(("enqueue", dict(memo))),
    )
    return seen


# -- POST ------------------------------------------------------------------------------------


def test_the_author_changes_the_playbook_and_c04_and_scoring_run_again(requeued):
    db = _Db(_memo())
    response = _client(db).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"})
    assert response.status_code == 200
    assert response.json() == {"sales_motion_key": "discovery", "playbook_version_id": "v-discovery", "status": "requeued"}
    assert (db.memo["sales_motion_key"], db.memo["playbook_version_id"]) == ("discovery", "v-discovery")
    pin = db.memo["pipeline_meta"]["playbook_pin"]
    assert pin == {"source": "manual", "changed_from": "closing", "changed_by": "author"}
    assert db.memo["pipeline_meta"]["stages"] == []
    # The same path a fresh extraction takes, with the memo as it is now pinned.
    assert [name for name, _ in requeued] == ["hooks", "enqueue"]
    for _, memo in requeued:
        assert memo["sales_motion_key"] == "discovery" and memo["playbook_version_id"] == "v-discovery"


def test_a_manager_of_the_company_can_change_it_too(requeued):
    for role in ("owner", "admin"):
        db = _Db(_memo())
        response = _client(db, user="boss", role=role).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"})
        assert response.status_code == 200
        assert db.memo["sales_motion_key"] == "discovery"
        assert db.memo["pipeline_meta"]["playbook_pin"]["changed_by"] == "boss"


def test_another_member_gets_403_and_nothing_changes(requeued):
    db = _Db(_memo())
    response = _client(db, user="colleague", role="member").post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"})
    assert response.status_code == 403
    assert db.memo["sales_motion_key"] == "closing"
    assert requeued == []


def test_a_manager_of_another_company_gets_403(requeued):
    db = _Db(_memo())
    response = _client(db, user="stranger", role="owner", company="co-2").post(
        f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"},
    )
    assert response.status_code == 403
    assert db.memo["sales_motion_key"] == "closing"


def test_an_unknown_memo_is_404(requeued):
    response = _client(_Db(None)).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"})
    assert response.status_code == 404


@pytest.mark.parametrize("key", ["negotiation", "inbound", "ghost", "  "])
def test_a_type_without_an_active_version_is_409_not_published(requeued, key):
    db = _Db(_memo())
    response = _client(db).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": key})
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "not_published"}
    assert db.memo["sales_motion_key"] == "closing"
    assert requeued == []


def test_a_failed_requeue_still_leaves_the_new_pin_and_answers(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("queue down")

    monkeypatch.setattr("app.services.memo_extraction_hooks.run_post_extraction_hooks", boom)
    monkeypatch.setattr("app.services.intelligence.worker.record_enqueue", boom)
    db = _Db(_memo())
    response = _client(db).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"})
    assert response.status_code == 200
    assert db.memo["sales_motion_key"] == "discovery"


def test_the_real_hooks_republish_coaching_for_the_new_pin_and_never_re_route_it(monkeypatch):
    """No stubs on run_post_extraction_hooks: with C04 off the score is published straight
    away for the memo as pinned now, and the manual pin is not re-routed by the hook."""
    from app.services import memo_extraction_hooks

    published = []
    monkeypatch.setattr(memo_extraction_hooks, "_publish_coaching", lambda _s, memo, _e: published.append(memo["sales_motion_key"]))
    monkeypatch.setattr(memo_extraction_hooks, "_maybe_insert_meeting_proposal", lambda *a, **k: None)
    monkeypatch.setattr(memo_extraction_hooks, "_ensure_screening_outcome", lambda _s, m: m)
    monkeypatch.setattr("app.services.intelligence.extract.schedule_intelligence", lambda *_a, **_k: False)
    monkeypatch.setattr("app.services.intelligence.worker.record_enqueue", lambda *_a, **_k: None)
    db = _Db(_memo())
    response = _client(db).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "discovery"})
    assert response.status_code == 200
    assert published == ["discovery"]
    assert db.memo["sales_motion_key"] == "discovery"


# -- GET -------------------------------------------------------------------------------------


def test_get_lists_the_published_types_and_says_the_author_can_change_it():
    store = MemoryPlaybookStore(
        {"co-1": {"renewal": "published", "closing": "published", "inbound": "draft", "discovery": "published", "negotiation": "missing"}}, {},
    )
    store.save_type_meta("co-1", "renewal", label="Renovación")
    body = _client(_Db(_memo()), store=store).get(f"/api/v1/memos/{MEMO}/playbook").json()
    assert body == {
        "sales_motion_key": "closing",
        "playbook_version_id": "v-closing-old",
        "can_change": True,
        "options": [
            {"key": "discovery", "label": None},
            {"key": "closing", "label": None},
            {"key": "renewal", "label": "Renovación"},
        ],
    }


def test_get_can_change_needs_the_routing_flag(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", False)
    body = _client(_Db(_memo())).get(f"/api/v1/memos/{MEMO}/playbook").json()
    assert body["can_change"] is False
    assert body["sales_motion_key"] == "closing"


def test_get_a_manager_can_change_it():
    body = _client(_Db(_memo()), user="boss", role="admin").get(f"/api/v1/memos/{MEMO}/playbook").json()
    assert body["can_change"] is True


def test_get_a_reader_who_is_not_the_author_sees_it_but_cannot_change_it(monkeypatch):
    seen = []
    monkeypatch.setattr("app.api.memos._require_viewable_memo", lambda _s, memo_id, user_id: seen.append((memo_id, user_id)) or ({}, {}))
    body = _client(_Db(_memo()), user="colleague").get(f"/api/v1/memos/{MEMO}/playbook").json()
    assert body["can_change"] is False
    assert body["sales_motion_key"] == "closing"
    assert seen == [(MEMO, "colleague")]


def test_get_a_member_who_cannot_read_the_memo_gets_404(monkeypatch):
    def not_readable(*_a):
        raise HTTPException(status_code=404, detail="Memo not found")

    monkeypatch.setattr("app.api.memos._require_viewable_memo", not_readable)
    assert _client(_Db(_memo()), user="colleague").get(f"/api/v1/memos/{MEMO}/playbook").status_code == 404


def test_get_an_unknown_memo_is_404():
    assert _client(_Db(None)).get(f"/api/v1/memos/{MEMO}/playbook").status_code == 404


def test_get_a_memo_with_no_pin():
    memo = _memo(sales_motion_key=None, playbook_version_id=None)
    body = _client(_Db(memo)).get(f"/api/v1/memos/{MEMO}/playbook").json()
    assert body["sales_motion_key"] is None and body["playbook_version_id"] is None


def test_the_memo_routes_are_registered_on_the_real_router():
    from app.api import playbook_rules, playbooks
    from app.api.router import api_router

    included = [getattr(route, "original_router", None) for route in api_router.routes]
    assert playbook_rules.router in included and playbook_rules.memo_router in included
    # /catalog and /deal-stages must be matched before any /{sales_motion_key} route.
    assert included.index(playbook_rules.router) < included.index(playbooks.router)

    app = FastAPI()
    app.include_router(api_router)
    schema = app.openapi()["paths"]
    assert {"get", "post"} <= set(schema["/api/v1/memos/{memo_id}/playbook"])
    assert "get" in schema["/api/v1/playbooks/catalog"] and "get" in schema["/api/v1/playbooks/deal-stages"]
    assert "put" in schema["/api/v1/playbooks/{sales_motion_key}/rule"]
