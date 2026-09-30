"""F08: one active playbook version, and a meeting keeps the version it started with."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest

from app.services.playbooks.versions import (
    can_publish,
    get_published_playbook,
    snapshot_for_capture,
    validate_entries,
)

PLAYBOOK = {"id": "pb-1", "company_id": "co-1", "sales_motion_key": "discovery", "active_version_id": "pv-2"}
V1 = {"id": "pv-1", "status": "published", "steps": [{"step_id": "pain", "label": "Confirmar problema", "criterion": "El prospecto confirma un problema concreto"}], "entries": []}
V2 = {"id": "pv-2", "status": "published", "steps": [{"step_id": "next", "label": "Siguiente paso", "criterion": "Hay un siguiente paso concreto"}], "entries": []}


def test_capture_keeps_the_version_fixed_at_the_start():
    assert snapshot_for_capture("pv-1", "pv-2") == "pv-1"
    assert get_published_playbook(PLAYBOOK, [V1, V2], version_id="pv-1")["version_id"] == "pv-1"
    assert get_published_playbook(PLAYBOOK, [V1, V2])["version_id"] == "pv-2"


def test_member_cannot_publish_and_an_entry_needs_a_source():
    assert can_publish("member") is False
    assert can_publish("owner") is True
    with pytest.raises(ValueError):
        validate_entries([{"entry_id": "e1", "source_ref": "  "}])


def test_unpublished_playbook_is_explicitly_absent():
    draft = {**PLAYBOOK, "active_version_id": None}
    assert get_published_playbook(draft, [{**V1, "status": "draft"}]) is None


def test_publishing_discovery_does_not_activate_another_motion_and_a_member_cannot():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import playbooks as playbooks_api
    from app.api.playbooks import router as playbooks_router
    from app.deps import get_membership
    from app.services.company import Membership

    playbooks_api._MOTIONS.clear()
    playbooks_api._LATEST.clear()
    playbooks_api._ACTIVATED.clear()
    role = {"value": "owner"}
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role=role["value"], status="active",
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/playbooks/imports",
        json={
            "import_id": "imp-discovery",
            "kind": "text",
            "payload": "Confirmar el problema antes del precio.",
            "sales_motion_key": "discovery",
        },
    )
    assert created.status_code == 200
    assert created.json()["published"] is False
    missing = client.post("/api/v1/playbooks/qualification/publish")
    assert missing.status_code == 409
    published = client.post("/api/v1/playbooks/discovery/publish")
    assert published.status_code == 200
    motions = published.json()["motions"]
    assert motions["discovery"] == "published"
    assert published.json()["activated"]["discovery"]
    assert "qualification" not in published.json()["activated"]
    assert motions.get("qualification") != "published"
    listed = client.get("/api/v1/playbooks")
    assert listed.status_code == 200
    assert listed.json()["motions"]["discovery"] == "published"
    role["value"] = "member"
    denied = client.post("/api/v1/playbooks/discovery/publish")
    assert denied.status_code == 403
    assert playbooks_api._MOTIONS["co"]["discovery"] == "published"


def test_the_publish_route_asks_postgres_for_one_motion_only():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.playbooks import router as playbooks_router
    from app.api.playbooks import set_playbook_store
    from app.deps import get_membership
    from app.services.company import Membership
    from app.services.playbooks.store import SupabasePlaybookStore

    class Result:
        def __init__(self, data):
            self.data = data

        def execute(self):
            return self

    class Client:
        def __init__(self):
            self.calls = []
            self.motions = {}

        def table(self, _name):
            class Chain:
                def select(self, *_args, **_kwargs):
                    return self

                def eq(self, *_args, **_kwargs):
                    return self

                def limit(self, *_args, **_kwargs):
                    return self

                def execute(self):
                    return Result([])

            return Chain()

        def rpc(self, name, params):
            self.calls.append((name, params))
            if name == "save_playbook_draft":
                self.motions[params["p_motion"]] = "draft"
                return Result("ready")
            if name == "list_playbook_motions":
                return Result([
                    {"sales_motion_key": key, "motion_status": status}
                    for key, status in self.motions.items()
                ])
            if name == "publish_playbook_motion":
                if self.motions.get(params["p_motion"]) != "draft":
                    return Result("not_a_draft")
                self.motions[params["p_motion"]] = "published"
                return Result("published")
            raise AssertionError(name)

    database = Client()
    set_playbook_store(SupabasePlaybookStore(database))
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role="owner", status="active",
    )
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/playbooks/imports",
            json={
                "import_id": "imp-discovery",
                "kind": "text",
                "payload": "Confirmar el problema antes del precio.",
                "sales_motion_key": "discovery",
            },
        )
        assert created.status_code == 200
        assert client.post("/api/v1/playbooks/qualification/publish").status_code == 409
        published = client.post("/api/v1/playbooks/discovery/publish")
        assert published.status_code == 200
        assert published.json()["motions"]["discovery"] == "published"
        assert "qualification" not in published.json()["motions"]
        assert [
            params["p_motion"]
            for name, params in database.calls
            if name == "publish_playbook_motion"
        ] == ["discovery"]
    finally:
        set_playbook_store(None)


def test_adding_a_typology_does_not_publish_it_and_a_member_cannot():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import playbooks as playbooks_api
    from app.api.playbooks import router as playbooks_router
    from app.deps import get_membership
    from app.services.company import Membership

    playbooks_api._MOTIONS.clear()
    playbooks_api._LATEST.clear()
    playbooks_api._ACTIVATED.clear()
    role = {"value": "member"}
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role=role["value"], status="active",
    )
    client = TestClient(app)
    denied = client.post("/api/v1/playbooks/types", json={"type_key": "renewal", "name": "Renovación"})
    assert denied.status_code == 403
    role["value"] = "owner"
    empty = client.post("/api/v1/playbooks/types", json={"type_key": "  ", "name": "Vacía"})
    assert empty.status_code == 409
    created = client.post("/api/v1/playbooks/types", json={"type_key": "renewal", "name": "Renovación"})
    assert created.status_code == 200
    assert created.json()["motions"]["renewal"] == "missing"
    assert created.json()["motions"].get("discovery") != "published"
    again = client.post("/api/v1/playbooks/types", json={"type_key": "renewal", "name": "Renovación"})
    assert again.json()["motions"]["renewal"] == "missing"

