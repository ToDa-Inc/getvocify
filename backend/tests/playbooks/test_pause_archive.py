"""Playbooks v2 section 16: pause, resume and delete (soft, undoable) a call type.

Every API test runs against the memory store and against SupabasePlaybookStore over an in-memory
PostgREST stand-in (FakeDb, plus the interaction_types table and migration 069's SQL functions), so
both agree. Pausing nulls the active version, so the readers of "the active playbook" (pinning,
routing, copilot grounding, briefs, insights) are tested against it too.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbook_rules import router as rules_router
from app.api.playbooks import router as playbooks_router
from app.api.playbooks import set_playbook_store
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.store import MemoryPlaybookStore, SupabasePlaybookStore
from app.services.playbooks.versions import LifecycleError, accept_publish
from tests.playbooks.test_draft_autosave import FakeDb, _Query, _Result

CO = "co-1"
ROOT = Path(__file__).resolve().parents[2]


# --- a PostgREST stand-in that also speaks migration 069 ---------------------------------------


class _Neq(_Query):
    def neq(self, col, value):
        self.filters.append(lambda row: row.get(col) != value)
        return self


class _Rpc:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return _Result(self.fn())


class LifeDb(FakeDb):
    """FakeDb with interaction_types and the 069 versions of list_playbook_motions,
    publish_playbook_motion and add_interaction_type."""

    def __init__(self):
        super().__init__()
        for name in ("interaction_types", "company_feature_flags", "memos", "crm_connections"):
            self.tables[name] = []

    def table(self, name):
        return _Neq(self, name)

    def rpc(self, name, params):
        if name == "list_playbook_motions":
            return _Rpc(lambda: self._list(params["p_company"]))
        if name == "add_interaction_type":
            return _Rpc(lambda: self._add_type(params["p_company"], params["p_key"], params.get("p_name")))
        if name == "publish_playbook_motion":
            inner = super().rpc(name, params)

            def publish():
                outcome = inner.execute().data
                if str(outcome).startswith("published"):
                    for pb in self.tables["playbooks"]:
                        if pb["company_id"] == params["p_company"] and pb["sales_motion_key"] == params["p_motion"]:
                            pb.update(paused_version_id=None, archived_at=None, archived_state=None)
                return outcome

            return _Rpc(publish)
        return super().rpc(name, params)

    def _list(self, company):
        rows, seen = [], set()
        for pb in self.tables["playbooks"]:
            if pb["company_id"] != company:
                continue
            seen.add(pb["sales_motion_key"])
            if pb.get("archived_at"):
                continue
            has_draft = any(v["playbook_id"] == pb["id"] and v["status"] == "draft" for v in self.tables["playbook_versions"])
            if pb.get("active_version_id"):
                status = "published"
            elif pb.get("paused_version_id"):
                status = "paused"
            else:
                status = "draft" if has_draft else "missing"
            rows.append({"sales_motion_key": pb["sales_motion_key"], "motion_status": status})
        for t in self.tables["interaction_types"]:
            if t["company_id"] == company and t.get("active", True) and t["type_key"] not in seen:
                rows.append({"sales_motion_key": t["type_key"], "motion_status": "missing"})
        return rows

    def _add_type(self, company, key, name):
        key = key.strip()
        if not key:
            return "empty"
        row = next((t for t in self.tables["interaction_types"] if t["company_id"] == company and t["type_key"] == key), None)
        if row is None:
            self.tables["interaction_types"].append({"company_id": company, "type_key": key, "name": name or key, "active": True})
        else:
            row["active"] = True
        for pb in self.tables["playbooks"]:
            if pb["company_id"] == company and pb["sales_motion_key"] == key and pb.get("archived_at"):
                pb.update(archived_at=None, paused_version_id=None, archived_state=None)
        return key


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
    def __init__(self, kind):
        self.kind = kind
        self.db = LifeDb() if kind == "supabase" else None
        self.store = SupabasePlaybookStore(self.db) if self.db else MemoryPlaybookStore({}, {}, {}, {}, {}, {})
        set_playbook_store(self.store)

    def client(self, role="owner", sales_role=None, company=CO):
        app = FastAPI()
        app.include_router(rules_router)  # the real order: /company, /catalog... before /{key}
        app.include_router(playbooks_router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id=company, user_id="u-1", role=role, status="active", sales_role=sales_role,
        )
        app.dependency_overrides[get_supabase] = lambda: _NoFlags()
        return TestClient(app)


@pytest.fixture(params=["memory", "supabase"])
def env(request):
    feature_flags.clear_cache()
    yield Env(request.param)
    set_playbook_store(None)
    feature_flags.clear_cache()


@pytest.fixture
def pg():
    feature_flags.clear_cache()
    yield Env("supabase")
    set_playbook_store(None)
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


def test_accept_publish_lets_a_paused_type_through_to_the_store():
    assert accept_publish({"a": "paused"}, "a", "owner") == {"a": "published"}
    with pytest.raises(Exception):
        accept_publish({"a": "missing"}, "a", "owner")


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


def test_delete_drops_the_pending_drafts_but_keeps_the_published_version_on_supabase(pg):
    db = pg.db
    client = pg.client()
    live(client, qualification=CRITERIA)
    put(client, label="Cambio a medias")
    playbook = db.tables["playbooks"][0]
    live_id = playbook["active_version_id"]
    drafts = [v for v in db.tables["playbook_versions"] if v["status"] == "draft"]
    assert len(drafts) == 1 and any(r["id"] == f"editor:{drafts[0]['id']}" for r in db.tables["playbook_imports"])
    source = pg.store.save_source(CO, "discovery", "text", "guion", "Pasos del guion")

    assert client.delete(f"{API}/discovery").status_code == 200
    assert [v for v in db.tables["playbook_versions"] if v["status"] == "draft"] == []
    assert not any(r["id"].startswith("editor:") and r["id"] != f"editor:{live_id}" for r in db.tables["playbook_imports"])
    assert any(r["id"] == source["id"] for r in db.tables["playbook_imports"])  # source documents stay
    assert [v["id"] for v in db.tables["playbook_versions"]] == [live_id]  # the published version is kept
    row = db.tables["playbooks"][0]
    assert row["active_version_id"] is None and row["paused_version_id"] == live_id
    assert row["archived_state"] == "published" and row["archived_at"]


def test_delete_deactivates_the_interaction_type_and_restore_reactivates_it(pg):
    db = pg.db
    client = pg.client()
    client.post(f"{API}/types", json={"type_key": "discovery", "name": "Llamada en frío"})
    live(client)
    types = lambda: [t["active"] for t in db.tables["interaction_types"] if t["type_key"] == "discovery"]  # noqa: E731
    assert types() == [True]
    client.delete(f"{API}/discovery")
    assert types() == [False]
    assert "discovery" not in listing(client)["motions"]
    restored = client.post(f"{API}/discovery/restore")
    assert restored.status_code == 200 and restored.json()["motions"]["discovery"] == "published"
    assert types() == [True]


def test_a_legacy_type_that_only_exists_in_interaction_types_deletes_and_restores(pg):
    db = pg.db
    client = pg.client()
    db.tables["interaction_types"].append({"company_id": CO, "type_key": "sales", "name": "Sales", "active": True})
    assert listing(client)["motions"] == {"sales": "missing"}
    assert client.delete(f"{API}/sales").status_code == 200
    assert listing(client)["motions"] == {}
    assert db.tables["interaction_types"][0]["active"] is False
    assert db.tables["playbooks"] == []  # no playbook row was made for it
    assert client.delete(f"{API}/sales").status_code == 404
    restored = client.post(f"{API}/sales/restore")
    assert restored.status_code == 200 and restored.json()["motions"] == {"sales": "missing"}
    assert db.tables["interaction_types"][0]["active"] is True
    assert client.post(f"{API}/sales/restore").status_code == 409  # not deleted any more


def test_an_empty_type_of_the_company_deletes_on_both_stores(env):
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


def test_the_columns_are_clean_after_a_draft_un_archives_a_type(pg):
    client = pg.client()
    live(client)
    client.delete(f"{API}/discovery")
    put(client, label="Nuevo")
    row = pg.db.tables["playbooks"][0]
    assert row["archived_at"] is None and row["archived_state"] is None and row["paused_version_id"] is None
    assert row["active_version_id"] is None


def test_creating_a_deleted_type_again_brings_it_back_empty(env):
    client = env.client()
    live(client, label="Viejo")
    client.delete(f"{API}/discovery")
    created = client.post(f"{API}/types", json={"type_key": "discovery", "name": "Llamada en frío"})
    assert created.status_code == 200 and created.json()["motions"]["discovery"] == "missing"
    assert editor(client)["source"] == "empty" and editor(client)["paused"] is False
    assert client.post(f"{API}/discovery/restore").status_code == 409


def test_creating_a_deleted_legacy_type_again_reactivates_it(pg):
    db = pg.db
    client = pg.client()
    db.tables["interaction_types"].append({"company_id": CO, "type_key": "sales", "name": "Sales", "active": True})
    client.delete(f"{API}/sales")
    created = client.post(f"{API}/types", json={"type_key": "sales", "name": "Sales"})
    assert created.json()["motions"] == {"sales": "missing"}
    assert db.tables["interaction_types"][0]["active"] is True


def test_the_legacy_import_path_un_archives_too_on_the_memory_store():
    env = Env("memory")
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
    set_playbook_store(None)


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
    set_playbook_store(MemoryPlaybookStore({}, {}, {}, {}, {}, {}))
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
        set_playbook_store(None)


def test_the_store_raises_lifecycle_errors_with_the_codes_the_api_uses():
    store = MemoryPlaybookStore({}, {}, {}, {}, {}, {})
    for action, code in (("pause", "not_published"), ("resume", "not_paused"), ("archive", "not_found"), ("restore", "not_archived")):
        with pytest.raises(LifecycleError) as raised:
            getattr(store, action)(CO, "ghost")
        assert raised.value.code == code


# --- readers of "the active playbook" --------------------------------------------------------


@pytest.fixture
def roles_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", False)
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _pin(db, **kwargs):
    from app.services.captures import playbook_fields_for_capture

    kwargs.setdefault("interaction_kind", "call")
    kwargs.setdefault("sales_role", "sdr")
    return playbook_fields_for_capture(db, CO, **kwargs)


def test_routing_never_routes_to_a_paused_type_and_falls_back_to_the_role_default(pg, monkeypatch):
    from app.services.playbooks import routing
    from app.services.playbooks.motion import route

    client = pg.client()
    for key in ("closing", "ae_discovery"):
        live(client, key, label=key)
    rules = lambda: routing.rules_from(pg.store.motions(CO), pg.store.details(CO))  # noqa: E731
    assert route("ae", "meeting", {"contact": "new"}, rules()) == ("ae_discovery", "rule")

    client.post(f"{API}/ae_discovery/pause")
    assert {r["key"]: r["published"] for r in rules()}["ae_discovery"] is False
    assert route("ae", "meeting", {"contact": "new"}, rules()) == ("closing", "rule")
    client.post(f"{API}/closing/pause")
    assert route("ae", "meeting", {"contact": "new"}, rules()) == ("closing", "role_default")

    client.post(f"{API}/ae_discovery/resume")
    client.delete(f"{API}/ae_discovery")
    assert {r["key"]: r["published"] for r in rules()}["ae_discovery"] is False
    assert route("ae", "meeting", {"contact": "new"}, rules())[1] == "role_default"


def test_the_memo_playbook_options_only_offer_active_types(pg):
    from app.api.playbook_rules import _published_options

    client = pg.client()
    live(client, "discovery")
    live(client, "closing", label="Cierre")
    membership = Membership(id="m", company_id=CO, user_id="u-1", role="owner", status="active")
    assert [o["key"] for o in _published_options(membership)] == ["discovery", "closing"]
    client.post(f"{API}/closing/pause")
    client.delete(f"{API}/discovery")
    assert _published_options(membership) == []


# --- the SQL ---------------------------------------------------------------------------------

