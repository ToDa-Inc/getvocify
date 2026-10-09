"""Playbooks v2, T2: the draft autosaves in place (one row however many saves), a stale editor is
told (409), "Descartar cambios" deletes only the pending draft, and the editor answer says whether
there is a live version and where the playbook came from."""

import copy
import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbooks import router as playbooks_router
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository
from app.services.playbooks.versions import StaleDraftError, is_newer, parse_ts, same_instant

BASE = "/api/v1/playbooks/discovery"


def draft(label="Apertura", criterion="Se presenta y pide un minuto", objection=None):
    body = {"steps": [{"label": label, "criterion": criterion}], "objections": []}
    if objection:
        body["objections"] = [{"category": "price", "guidance": objection}]
    return body


class _NoFlags:
    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": []})()


@pytest.fixture
def client_for():
    store = InMemoryPlaybookRepository()
    set_playbook_repository(store)
    feature_flags.clear_cache()

    def make(role="owner", company="co-1"):
        app = FastAPI()
        app.include_router(playbooks_router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id=company, user_id="u", role=role, status="active", sales_role=None,
        )
        app.dependency_overrides[get_supabase] = lambda: _NoFlags()
        return TestClient(app)

    make.store = store
    yield make
    set_playbook_repository(None)
    feature_flags.clear_cache()


def js_iso(value: str) -> str:
    """What a browser's Date.toISOString() makes of a server timestamp: milliseconds and a Z."""
    parsed = parse_ts(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"


# --- timestamps ---


def test_timestamps_compare_as_instants_not_strings():
    assert same_instant("2026-09-29T10:00:00.123456+00:00", "2026-09-29T10:00:00.123Z")
    assert same_instant("2026-09-29T12:00:00+02:00", "2026-09-29T10:00:00Z")
    assert same_instant("2026-09-29 10:00:00.5+00:00", "2026-09-29T10:00:00.500Z")
    assert not same_instant("2026-09-29T10:00:00.123Z", "2026-09-29T10:00:00.124Z")
    assert is_newer("2026-09-29T10:00:01+00:00", "2026-09-29T10:00:00.999999Z")
    assert not is_newer("2026-09-29T10:00:00Z", "2026-09-29T10:00:00+00:00")
    assert is_newer("2026-09-29T10:00:00Z", None) and not is_newer(None, "2026-09-29T10:00:00Z")
    assert parse_ts("nonsense") is None
    assert same_instant("nonsense", "nonsense") and not same_instant("nonsense", "other")
    assert parse_ts("2026-09-29T10:00:00.12345+00:00").microsecond == 123450


# --- API on the memory store ---


def test_ten_saves_are_one_draft(client_for):
    client = client_for()
    seen = []
    for i in range(10):
        response = client.put(f"{BASE}/draft", json=draft(criterion=f"Se presenta {i}"))
        assert response.status_code == 200
        seen.append(response.json())
    assert len({body["version_id"] for body in seen}) == 1
    stamps = [body["updated_at"] for body in seen]
    assert all(is_newer(b, a) for a, b in zip(stamps, stamps[1:]))
    got = client.get(f"{BASE}/editor").json()
    assert got["steps"][0]["criterion"] == "Se presenta 9"
    assert got["version_id"] == seen[0]["version_id"]
    assert got["updated_at"] == stamps[-1]
    assert got["source"] == "draft" and got["has_live"] is False and got["source_doc"] is None


def test_the_editor_answer_has_the_contract_fields(client_for):
    client = client_for()
    empty = client.get(f"{BASE}/editor").json()
    assert empty["source"] == "empty" and empty["updated_at"] is None and empty["has_live"] is False
    assert empty["version_id"] is None and empty["steps"] == []
    saved = client.put(f"{BASE}/draft", json=draft()).json()
    assert set(saved) >= {"sales_motion_key", "source", "source_doc", "version_id", "updated_at", "has_live", "steps", "objections", "categories"}


def test_publishing_then_editing_creates_a_new_draft_and_leaves_the_live_version(client_for):
    client = client_for()
    first = client.put(f"{BASE}/draft", json=draft("Apertura")).json()
    assert client.post(f"{BASE}/publish").status_code == 200
    live = client.get(f"{BASE}/editor").json()
    assert live["source"] == "published" and live["has_live"] is True
    assert live["version_id"] == first["version_id"]

    edited = client.put(f"{BASE}/draft", json={**draft("Apertura nueva"), "base_updated_at": live["updated_at"]})
    assert edited.status_code == 200
    body = edited.json()
    assert body["version_id"] != live["version_id"]
    assert body["source"] == "draft" and body["has_live"] is True
    # A rep still reads the live version; the manager reads the draft.
    rep = client_for(role="member").get(f"{BASE}/editor").json()
    assert rep["source"] == "published" and rep["steps"][0]["label"] == "Apertura"
    assert client.get(f"{BASE}/editor").json()["steps"][0]["label"] == "Apertura nueva"
    # More edits keep updating that new draft in place.
    again = client.put(f"{BASE}/draft", json=draft("Apertura nueva 2")).json()
    assert again["version_id"] == body["version_id"]


def test_a_stale_base_is_409_and_changes_nothing(client_for):
    client = client_for()
    one = client.put(f"{BASE}/draft", json=draft("Uno")).json()
    two = client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": one["updated_at"]})
    assert two.status_code == 200
    stale = client.put(f"{BASE}/draft", json={**draft("Tres"), "base_updated_at": one["updated_at"]})
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"code": "stale_draft"}
    assert client.get(f"{BASE}/editor").json()["steps"][0]["label"] == "Dos"
    ok = client.put(f"{BASE}/draft", json={**draft("Cuatro"), "base_updated_at": two.json()["updated_at"]})
    assert ok.status_code == 200


def test_a_base_that_went_through_a_js_date_still_matches(client_for):
    client = client_for()
    saved = client.put(f"{BASE}/draft", json=draft("Uno")).json()
    ok = client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": js_iso(saved["updated_at"])})
    assert ok.status_code == 200


def test_a_base_for_a_draft_that_no_longer_exists_is_stale(client_for):
    client = client_for()
    saved = client.put(f"{BASE}/draft", json=draft("Uno")).json()
    assert client.delete(f"{BASE}/draft").status_code == 200
    response = client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": saved["updated_at"]})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "stale_draft"


def test_a_null_base_never_conflicts(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft("Uno"))
    assert client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": None}).status_code == 200


def test_discarding_without_a_live_version_leaves_it_empty(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft())
    assert client.get("/api/v1/playbooks").json()["motions"]["discovery"] == "draft"
    response = client.delete(f"{BASE}/draft")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "empty" and body["steps"] == [] and body["has_live"] is False
    assert body["updated_at"] is None and body["version_id"] is None
    assert client.get("/api/v1/playbooks").json()["motions"]["discovery"] == "missing"
    assert client.post(f"{BASE}/publish").status_code == 409  # nothing left to publish


def test_discarding_over_a_live_version_returns_to_published(client_for):
    client = client_for()
    live = client.put(f"{BASE}/draft", json=draft("Apertura")).json()
    client.post(f"{BASE}/publish")
    client.put(f"{BASE}/draft", json=draft("Cambio a medias"))
    response = client.delete(f"{BASE}/draft")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "published" and body["has_live"] is True
    assert body["version_id"] == live["version_id"]
    assert body["steps"][0]["label"] == "Apertura"
    assert client.get("/api/v1/playbooks").json()["motions"]["discovery"] == "published"


def test_discarding_never_touches_a_published_version_and_is_idempotent(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft("Apertura"))
    client.post(f"{BASE}/publish")
    for _ in range(2):
        body = client.delete(f"{BASE}/draft").json()
        assert body["source"] == "published" and body["steps"][0]["label"] == "Apertura"


def test_editing_a_live_playbook_and_activating_again_publishes_the_edit(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft("Apertura"))
    client.post(f"{BASE}/publish")
    client.put(f"{BASE}/draft", json=draft("Apertura nueva"))
    listed = client.get("/api/v1/playbooks").json()
    assert listed["motions"]["discovery"] == "published" and listed["details"]["discovery"]["has_draft"] is True
    activated = client.post(f"{BASE}/publish")  # "Activar para el equipo" on a page with pending edits
    assert activated.status_code == 200 and activated.json()["motions"]["discovery"] == "published"
    now = client.get(f"{BASE}/editor").json()
    assert now["source"] == "published" and now["steps"][0]["label"] == "Apertura nueva"
    assert activated.json()["activated"]["discovery"] == now["version_id"]
    assert client.get("/api/v1/playbooks").json()["details"]["discovery"]["has_draft"] is False
    assert client.post(f"{BASE}/publish").status_code == 409  # nothing pending any more


def test_a_member_cannot_save_discard_or_reach_a_draft(client_for):
    client_for().put(f"{BASE}/draft", json=draft())
    rep = client_for(role="member")
    assert rep.put(f"{BASE}/draft", json=draft("Otro")).status_code == 403
    assert rep.delete(f"{BASE}/draft").status_code == 403
    assert client_for().get(f"{BASE}/editor").json()["steps"][0]["label"] == "Apertura"
    assert rep.get(f"{BASE}/editor").json()["source"] == "empty"


def test_the_source_travels_with_the_draft_and_survives_publishing(client_for):
    client = client_for()
    source = client_for.store.save_source("co-1", "discovery", "pdf", "guion-sdr.pdf", "Confirmar el problema")
    saved = client.put(f"{BASE}/draft", json={**draft(), "source_id": source["id"]}).json()
    assert saved["source_doc"] == {"id": source["id"], "kind": "pdf", "name": "guion-sdr.pdf"}
    # A later save that does not repeat the id keeps it.
    kept = client.put(f"{BASE}/draft", json=draft("Apertura 2")).json()
    assert kept["source_doc"]["id"] == source["id"]
    client.post(f"{BASE}/publish")
    assert client.get(f"{BASE}/editor").json()["source_doc"]["name"] == "guion-sdr.pdf"
    assert client_for(role="member").get(f"{BASE}/editor").json()["source_doc"]["name"] == "guion-sdr.pdf"
    # The next draft over the live version still points at it.
    over = client.put(f"{BASE}/draft", json=draft("Apertura 3")).json()
    assert over["source_doc"]["id"] == source["id"]


def test_a_source_id_from_another_company_or_made_up_is_ignored(client_for):
    client = client_for()
    other = client_for.store.save_source("co-2", "discovery", "text", "ajeno", "secreto")
    for bad in (other["id"], "source:nope", "editor:abc", "x"):
        saved = client.put(f"{BASE}/draft", json={**draft(), "source_id": bad}).json()
        assert saved["source_doc"] is None


def test_an_editor_save_clears_a_contradictory_import_gate(client_for):
    client = client_for()
    client.post(
        "/api/v1/playbooks/imports",
        json={"import_id": "imp-c", "kind": "text", "payload": "Nunca descuentes. Siempre cierra.", "sales_motion_key": "discovery"},
    )
    assert client.post(f"{BASE}/publish").status_code == 409
    client.put(f"{BASE}/draft", json=draft())
    assert client.post(f"{BASE}/publish").status_code == 200
