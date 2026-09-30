"""Playbooks v2 section 16: pause, resume and delete (soft, undoable) a call type, through the API.

The API runs on InMemoryPlaybookRepository here; the storage semantics (what pausing and deleting do to the rows, the
interaction types, drafts and versions) are the repository contract, tests/playbooks/test_repository_contract.py, which
runs against this fake and against real PostgreSQL. What applies to a call while a playbook is paused or deleted is
tests/playbooks/test_live.py.
"""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbook_rules import router as rules_router
from app.api.playbooks import router as playbooks_router
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository

CO = "co-1"


class _NoFlags:
    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": []})()


class Env:
    def __init__(self):
        self.store = InMemoryPlaybookRepository()
        set_playbook_repository(self.store)

    def client(self, role="owner", sales_role=None, company=CO):
        app = FastAPI()
        app.include_router(rules_router)  # the real order: /company, /catalog... before /{key}
        app.include_router(playbooks_router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id=company, user_id="u-1", role=role, status="active", sales_role=sales_role,
        )
        app.dependency_overrides[get_supabase] = lambda: _NoFlags()
        return TestClient(app)


@pytest.fixture
def env():
    feature_flags.clear_cache()
    yield Env()
    set_playbook_repository(None)
    feature_flags.clear_cache()


API = "/api/v1/playbooks"


def put(client, key="discovery", label="Apertura", **extra):
    body = {"steps": [{"label": label, "criterion": f"Hace {label} y el prospecto responde."}], "objections": [], **extra}
    response = client.put(f"{API}/{key}/draft", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def publish(client, key="discovery"):
    response = client.post(f"{API}/{key}/publish")
    assert response.status_code == 200, response.text
    return response.json()


def listing(client):
    response = client.get(API)
    assert response.status_code == 200
    return response.json()


def editor(client, key="discovery"):
    return client.get(f"{API}/{key}/editor").json()


def live(client, key="discovery", label="Apertura", **extra):
    put(client, key, label, **extra)
    publish(client, key)


CRITERIA = [{"label": "Presupuesto", "why": "Sin presupuesto no hay compra."}]


# --- pause and resume ------------------------------------------------------------------------


def test_pause_then_resume_round_trip(env):
    client = env.client()
    live(client, qualification=CRITERIA)
    assert listing(client)["motions"]["discovery"] == "published"

    paused = client.post(f"{API}/discovery/pause")
    assert paused.status_code == 200
    body = paused.json()
    assert body["motions"]["discovery"] == "paused"
    assert set(body) >= {"motions", "details"}
    assert body["details"]["discovery"]["paused"] is True
    # The content stays: the counts come from the paused version.
    assert body["details"]["discovery"]["step_count"] == 1 and body["details"]["discovery"]["criteria_count"] == 1
    assert body["details"]["discovery"]["has_draft"] is False
    assert body == listing(client)  # the same shape and content as GET /playbooks

    shown = editor(client)
    assert shown["source"] == "published" and shown["paused"] is True and shown["has_live"] is True
    assert shown["steps"][0]["label"] == "Apertura" and shown["qualification"][0]["label"] == "Presupuesto"

    resumed = client.post(f"{API}/discovery/resume")
    assert resumed.status_code == 200
    assert resumed.json()["motions"]["discovery"] == "published"
    assert resumed.json()["details"]["discovery"]["paused"] is False
    back = editor(client)
    assert back["paused"] is False and back["source"] == "published" and back["steps"][0]["label"] == "Apertura"
    assert back["version_id"] == shown["version_id"]  # the very version that was paused


def test_the_editor_says_paused_false_when_it_is_not(env):
    client = env.client()
    assert editor(client)["paused"] is False  # empty
    put(client)
    assert editor(client)["paused"] is False  # draft
    publish(client)
    assert editor(client)["paused"] is False  # published


def test_pausing_something_that_is_not_published_is_409_not_published(env):
    client = env.client()
    client.post(f"{API}/types", json={"type_key": "renewal", "name": "Renovación"})
    put(client, "discovery")  # a draft, nothing live
    for key in ("renewal", "discovery", "ghost"):
        response = client.post(f"{API}/{key}/pause")
        assert response.status_code == 409 and response.json()["detail"] == {"code": "not_published"}
    live(client, "closing")
    assert client.post(f"{API}/closing/pause").status_code == 200
    again = client.post(f"{API}/closing/pause")
    assert again.status_code == 409 and again.json()["detail"] == {"code": "not_published"}


def test_resuming_something_that_is_not_paused_is_409_not_paused(env):
    client = env.client()
    live(client, "closing")
    put(client, "discovery")
    for key in ("closing", "discovery", "ghost"):
        response = client.post(f"{API}/{key}/resume")
        assert response.status_code == 409 and response.json()["detail"] == {"code": "not_paused"}


def test_a_paused_playbook_with_a_newer_draft_is_still_paused_and_publishing_it_lifts_the_pause(env):
    client = env.client()
    live(client, label="Apertura")
    client.post(f"{API}/discovery/pause")
    saved = put(client, label="Apertura nueva")
    assert saved["paused"] is True and saved["source"] == "draft" and saved["has_live"] is True
    body = listing(client)
    assert body["motions"]["discovery"] == "paused"  # a pending draft does not un-pause it
    assert body["details"]["discovery"]["paused"] is True and body["details"]["discovery"]["has_draft"] is True
    # A rep only ever sees the paused version, and no draft.
    rep = env.client(role="member")
    seen = editor(rep)
    assert seen["source"] == "published" and seen["steps"][0]["label"] == "Apertura" and seen["paused"] is True
    assert listing(rep)["details"]["discovery"]["has_draft"] is False
    # Discarding the draft returns to the paused version.
    put(client, label="Otra")
    discarded = client.delete(f"{API}/discovery/draft").json()
    assert discarded["source"] == "published" and discarded["paused"] is True and discarded["steps"][0]["label"] == "Apertura"
    put(client, label="Apertura nueva")

    published = publish(client)
    assert published["motions"]["discovery"] == "published"
    after = listing(client)
    assert after["details"]["discovery"]["paused"] is False and after["details"]["discovery"]["has_draft"] is False
    now = editor(client)
    assert now["paused"] is False and now["source"] == "published" and now["steps"][0]["label"] == "Apertura nueva"
    assert client.post(f"{API}/discovery/resume").status_code == 409  # nothing paused any more


def test_publishing_a_paused_playbook_that_has_no_draft_is_409(env):
    client = env.client()
    live(client)
    client.post(f"{API}/discovery/pause")
    assert client.post(f"{API}/discovery/publish").status_code == 409
    assert listing(client)["motions"]["discovery"] == "paused"


def test_pause_and_resume_touch_one_type_only(env):
    client = env.client()
    live(client, "discovery")
    live(client, "closing", label="Cierre")
    client.post(f"{API}/discovery/pause")
    motions = listing(client)["motions"]
    assert motions["discovery"] == "paused" and motions["closing"] == "published"
    client.post(f"{API}/discovery/resume")
    assert listing(client)["motions"] == {"discovery": "published", "closing": "published"}


def test_pause_is_per_company(env):
    client = env.client()
    live(client)
    other = env.client(company="co-2")
    assert other.post(f"{API}/discovery/pause").status_code == 409
    assert listing(client)["motions"]["discovery"] == "published"
    assert listing(other)["motions"] == {}


# --- delete (archive) and restore ------------------------------------------------------------


def test_delete_removes_the_type_from_the_list_and_the_editor(env):
    client = env.client()
    live(client, qualification=CRITERIA)
    put(client, label="Cambio a medias")  # a pending draft over the live version
    response = client.delete(f"{API}/discovery")
    assert response.status_code == 200
    body = response.json()
    assert "discovery" not in body["motions"] and "discovery" not in body["details"]
    assert body == listing(client)
    gone = editor(client)
    assert gone["source"] == "empty" and gone["steps"] == [] and gone["paused"] is False and gone["has_live"] is False
    assert client.post(f"{API}/discovery/publish").status_code == 409
    assert client.post(f"{API}/discovery/pause").status_code == 409
    assert client.post(f"{API}/discovery/resume").status_code == 409


def test_deleting_twice_or_a_type_the_company_does_not_have_is_404(env):
    client = env.client()
    assert client.delete(f"{API}/ghost").status_code == 404
    live(client)
    assert client.delete(f"{API}/discovery").status_code == 200
    assert client.delete(f"{API}/discovery").status_code == 404
    other = env.client(company="co-2")
    live(other)
    assert client.delete(f"{API}/discovery").status_code == 404  # co-2's type is not ours


def test_an_empty_type_of_the_company_deletes_and_restores(env):
    client = env.client()
    client.post(f"{API}/types", json={"type_key": "sdr", "name": "SDR"})
    assert listing(client)["motions"] == {"sdr": "missing"}
    body = client.delete(f"{API}/sdr").json()
    assert body["motions"] == {} and body["details"] == {}
    assert client.post(f"{API}/sdr/restore").json()["motions"] == {"sdr": "missing"}


def test_restore_puts_a_published_playbook_back_as_published(env):
    client = env.client()
    live(client, qualification=CRITERIA)
    before = editor(client)
    client.delete(f"{API}/discovery")
    restored = client.post(f"{API}/discovery/restore")
    assert restored.status_code == 200
    body = restored.json()
    assert body["motions"]["discovery"] == "published" and body["details"]["discovery"]["paused"] is False
    assert body == listing(client)
    after = editor(client)
    assert after["source"] == "published" and after["paused"] is False and after["has_live"] is True
    assert after["version_id"] == before["version_id"] and after["steps"] == before["steps"]
    assert after["qualification"] == before["qualification"]


def test_restore_of_a_paused_playbook_stays_paused(env):
    client = env.client()
    live(client)
    client.post(f"{API}/discovery/pause")
    assert client.delete(f"{API}/discovery").status_code == 200
    restored = client.post(f"{API}/discovery/restore").json()
    assert restored["motions"]["discovery"] == "paused" and restored["details"]["discovery"]["paused"] is True
    assert editor(client)["paused"] is True
    assert client.post(f"{API}/discovery/resume").json()["motions"]["discovery"] == "published"


def test_restore_of_a_draft_only_type_is_empty_because_the_draft_went_with_the_delete(env):
    client = env.client()
    put(client)
    assert listing(client)["motions"]["discovery"] == "draft"
    client.delete(f"{API}/discovery")
    restored = client.post(f"{API}/discovery/restore").json()
    assert restored["motions"]["discovery"] == "missing"
    assert editor(client)["source"] == "empty"


def test_restore_of_a_published_type_with_a_draft_comes_back_without_the_draft(env):
    client = env.client()
    live(client, label="Vigente")
    put(client, label="Cambio a medias")
    client.delete(f"{API}/discovery")
    client.post(f"{API}/discovery/restore")
    shown = editor(client)
    assert shown["source"] == "published" and shown["steps"][0]["label"] == "Vigente"
    assert listing(client)["details"]["discovery"]["has_draft"] is False


def test_restore_when_it_is_not_deleted_is_409_not_archived(env):
    client = env.client()
    live(client)
    for key in ("discovery", "ghost"):
        response = client.post(f"{API}/{key}/restore")
        assert response.status_code == 409 and response.json()["detail"] == {"code": "not_archived"}


def test_a_restored_type_can_be_deleted_again(env):
    client = env.client()
    live(client)
    for _ in range(2):
        assert client.delete(f"{API}/discovery").status_code == 200
        assert client.post(f"{API}/discovery/restore").json()["motions"]["discovery"] == "published"


# --- writing to a deleted type brings it back empty ------------------------------------------


def test_a_new_draft_on_a_deleted_type_un_archives_it_without_the_old_content(env):
    client = env.client()
    live(client, label="Viejo", qualification=CRITERIA)
    client.delete(f"{API}/discovery")
    saved = put(client, label="Nuevo")  # no qualification sent: nothing to inherit
    assert saved["source"] == "draft" and saved["paused"] is False and saved["has_live"] is False
    assert [s["label"] for s in saved["steps"]] == ["Nuevo"] and saved["qualification"] == []
    body = listing(client)
    assert body["motions"]["discovery"] == "draft"
    assert body["details"]["discovery"]["paused"] is False and body["details"]["discovery"]["step_count"] == 1
    assert client.post(f"{API}/discovery/restore").status_code == 409  # it is not deleted any more
    published = publish(client)
    assert published["motions"]["discovery"] == "published"
    final = editor(client)
    assert [s["label"] for s in final["steps"]] == ["Nuevo"] and final["qualification"] == [] and final["paused"] is False


def test_creating_a_deleted_type_again_brings_it_back_empty(env):
    client = env.client()
    live(client, label="Viejo")
    client.delete(f"{API}/discovery")
    created = client.post(f"{API}/types", json={"type_key": "discovery", "name": "Llamada en frío"})
    assert created.status_code == 200 and created.json()["motions"]["discovery"] == "missing"
    assert editor(client)["source"] == "empty" and editor(client)["paused"] is False
    assert client.post(f"{API}/discovery/restore").status_code == 409


def test_the_legacy_import_path_un_archives_too(env):
    client = env.client()
    live(client, label="Viejo")
    client.delete(f"{API}/discovery")
    response = client.post(
        f"{API}/imports",
        json={"import_id": "imp-1", "kind": "text", "payload": "Confirmar el problema", "sales_motion_key": "discovery"},
    )
    assert response.status_code == 200
    assert listing(client)["motions"]["discovery"] == "draft"
    assert editor(client)["has_live"] is False and editor(client)["paused"] is False  # nothing of the old one


# --- who can do it ---------------------------------------------------------------------------


def test_a_member_cannot_pause_resume_delete_or_restore(env):
    owner = env.client()
    live(owner)
    rep = env.client(role="member")
    for method, path in (
        ("post", "discovery/pause"), ("post", "discovery/resume"), ("delete", "discovery"), ("post", "discovery/restore"),
        ("post", "ghost/pause"), ("delete", "ghost"),  # 403 before it looks at the type
    ):
        assert getattr(rep, method)(f"{API}/{path}").status_code == 403, path
    assert listing(owner)["motions"]["discovery"] == "published"
    admin = env.client(role="admin")
    assert admin.post(f"{API}/discovery/pause").status_code == 200
    assert admin.post(f"{API}/discovery/resume").status_code == 200
    assert admin.delete(f"{API}/discovery").status_code == 200


def test_a_rep_sees_a_paused_playbook_in_the_list_but_not_a_deleted_one(env):
    owner = env.client()
    live(owner, "discovery")
    live(owner, "closing", label="Cierre")
    owner.post(f"{API}/discovery/pause")
    owner.delete(f"{API}/closing")
    body = listing(env.client(role="member"))
    assert body["motions"] == {"discovery": "paused"}


# --- routes ----------------------------------------------------------------------------------


def test_the_new_routes_do_not_clash_with_the_fixed_ones(env, monkeypatch):
    client = env.client()
    live(client)
    put(client, label="Cambio")
    assert client.get(f"{API}/company").status_code == 200
    assert client.get(f"{API}/catalog").status_code == 200
    assert client.get(f"{API}/qualification-templates").status_code == 200
    assert client.get(f"{API}/deal-stages").status_code == 200
    # DELETE /{key}/draft is still "Descartar cambios", not a delete of the type.
    discarded = client.delete(f"{API}/discovery/draft")
    assert discarded.status_code == 200 and discarded.json()["source"] == "published"
    assert listing(client)["motions"]["discovery"] == "published"
    # ... and DELETE /{key} is the delete.
    assert client.delete(f"{API}/discovery").status_code == 200
    # A fixed path is never a type: DELETE /company is not a delete of anything, knowledge is intact.
    assert client.delete(f"{API}/company").status_code == 404
    assert client.get(f"{API}/company").status_code == 200
    assert client.post(f"{API}/types", json={"type_key": "renewal", "name": "R"}).status_code == 200
    assert client.post(f"{API}/imports", json={"import_id": "i", "kind": "text", "payload": "x"}).status_code == 200


def test_the_real_router_serves_the_lifecycle_routes_and_keeps_the_fixed_paths():
    from app.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    paths = app.openapi()["paths"]
    for method, path in (
        ("post", "/api/v1/playbooks/{sales_motion_key}/pause"),
        ("post", "/api/v1/playbooks/{sales_motion_key}/resume"),
        ("post", "/api/v1/playbooks/{sales_motion_key}/restore"),
        ("delete", "/api/v1/playbooks/{sales_motion_key}"),
        ("delete", "/api/v1/playbooks/{sales_motion_key}/draft"),
        ("get", "/api/v1/playbooks/company"),
        ("get", "/api/v1/playbooks/catalog"),
        ("get", "/api/v1/playbooks/qualification-templates"),
        ("get", "/api/v1/playbooks/deal-stages"),
    ):
        assert method in paths.get(path, {}), (method, path)
    # Behaviour, through the real router: a fixed path is never read as a type.
    set_playbook_repository(InMemoryPlaybookRepository())
    try:
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id=CO, user_id="u-1", role="owner", status="active", sales_role=None,
        )
        app.dependency_overrides[get_supabase] = lambda: _NoFlags()
        client = TestClient(app)
        assert client.get(f"{API}/catalog").json()["types"][0]["key"] == "discovery"
        assert client.get(f"{API}/company").status_code == 200
        assert client.delete(f"{API}/ghost").status_code == 404
        assert client.post(f"{API}/ghost/pause").status_code == 409
    finally:
        set_playbook_repository(None)


# --- the memo's "evaluated as" options ----------------------------------------------------------


def test_the_memo_playbook_options_only_offer_active_types(env):
    from app.api.playbook_rules import _published_options

    client = env.client()
    live(client, "discovery")
    live(client, "closing", label="Cierre")
    membership = Membership(id="m", company_id=CO, user_id="u-1", role="owner", status="active")
    assert [o["key"] for o in _published_options(membership)] == ["discovery", "closing"]
    client.post(f"{API}/closing/pause")
    client.delete(f"{API}/discovery")
    assert _published_options(membership) == []
