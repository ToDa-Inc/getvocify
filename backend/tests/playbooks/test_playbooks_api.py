"""T2: GET /playbooks exposes goal and, per member, only the motions of their flow (D4/D5)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbooks import router as playbooks_router
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository


@pytest.fixture(autouse=True)
def _clear_flag_cache():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


class _FlagSupabase:
    """No company override: is_enabled falls back to the global settings value."""

    def table(self, name):
        assert name == "company_feature_flags"

        class _Q:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def execute(self):
                return type("R", (), {"data": []})()

        return _Q()


def _client(store, role: str, sales_role):
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="u", role=role, status="active", sales_role=sales_role,
    )
    app.dependency_overrides[get_supabase] = lambda: _FlagSupabase()
    set_playbook_repository(store)
    return TestClient(app)


def _store() -> InMemoryPlaybookRepository:
    return InMemoryPlaybookRepository({"co-1": {"discovery": "published", "closing": "published", "qualification": "missing"}})


def test_flag_off_returns_the_old_shape(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    client = _client(_store(), role="member", sales_role="sdr")
    try:
        body = client.get("/api/v1/playbooks").json()
        assert body["motions"] == {"discovery": "published", "closing": "published", "qualification": "missing"}
        assert "goals" not in body
        # v2 contract: `details` is always there, additive.
        assert set(body["details"]) == {"discovery", "closing", "qualification"}
    finally:
        set_playbook_repository(None)


def test_sdr_member_does_not_see_closing(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    client = _client(_store(), role="member", sales_role="sdr")
    try:
        body = client.get("/api/v1/playbooks").json()
        assert "closing" not in body["motions"]
        assert body["motions"]["discovery"] == "published"
        assert body["goals"] == {"discovery": "meeting_booked"}
    finally:
        set_playbook_repository(None)


def test_ae_member_does_not_see_discovery(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    client = _client(_store(), role="member", sales_role="ae")
    try:
        body = client.get("/api/v1/playbooks").json()
        assert "discovery" not in body["motions"]
        assert body["motions"]["closing"] == "published"
    finally:
        set_playbook_repository(None)


def test_general_member_sees_both_flows(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    client = _client(_store(), role="member", sales_role=None)
    try:
        body = client.get("/api/v1/playbooks").json()
        assert body["motions"]["discovery"] == "published"
        assert body["motions"]["closing"] == "published"
    finally:
        set_playbook_repository(None)


def test_owner_sees_every_motion_regardless_of_sales_role(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    client = _client(_store(), role="owner", sales_role="sdr")
    try:
        body = client.get("/api/v1/playbooks").json()
        assert body["motions"]["discovery"] == "published"
        assert body["motions"]["closing"] == "published"
    finally:
        set_playbook_repository(None)


def test_a_rep_opens_exactly_the_types_the_list_gives_them(monkeypatch):
    """Coaching → Playbook opens a listed type: what the list shows the editor must serve."""
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    store = _store()
    store.set_meta("co-1", "closing", applies_to={"role": "any"})  # saved for every role
    client = _client(store, role="member", sales_role="sdr")
    try:
        listed = {k for k, s in client.get("/api/v1/playbooks").json()["motions"].items() if s == "published"}
        assert listed == {"discovery", "closing"}
        for key in listed:
            assert client.get(f"/api/v1/playbooks/{key}/editor").status_code == 200, key
    finally:
        set_playbook_repository(None)


def test_a_rep_cannot_open_the_other_roles_type(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    client = _client(_store(), role="member", sales_role="sdr")
    try:
        assert client.get("/api/v1/playbooks/closing/editor").status_code == 404
        assert client.get("/api/v1/playbooks/discovery/editor").status_code == 200
    finally:
        set_playbook_repository(None)
