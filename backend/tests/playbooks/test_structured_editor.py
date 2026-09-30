"""The playbook editor saves real steps and objection answers (Lista 3 review fix): a
pasted text used to become one step holding the whole document, so scoring, missed
steps, objection answers and the checklist could never work from the UI."""

import os

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
from app.services.playbooks.structured import (
    PlaybookDraftError,
    editor_view,
    normalize_objections,
    normalize_steps,
    slug,
)


# --- normalization ---


def test_steps_get_stable_ids_from_their_labels_and_keep_given_ids():
    steps = normalize_steps([
        {"label": "Apertura", "criterion": "Se presenta y pide permiso", "step_id": "opening"},
        {"label": "Descubrir el dolor", "criterion": "  Pregunta   por el problema "},
        {"label": "Descubrir el dolor", "criterion": "otra vez"},
    ])
    assert [s["step_id"] for s in steps] == ["opening", "descubrir_el_dolor", "descubrir_el_dolor_2"]
    assert steps[1]["criterion"] == "Pregunta por el problema"


def test_a_step_without_criterion_uses_its_label():
    assert normalize_steps([{"label": "Agendar reunión"}])[0]["criterion"] == "Agendar reunión"


@pytest.mark.parametrize("steps,code", [
    ([], "no_steps"),
    ([{"label": "  "}], "empty_label"),
    ([{"label": "x" * 81}], "label_too_long"),
    ([{"label": "a", "criterion": "x" * 401}], "criterion_too_long"),
    ([{"label": "a", "step_id": "Bad Id"}], "bad_step_id"),
    ([{"label": "a", "step_id": "x"}, {"label": "b", "step_id": "x"}], "duplicate_step_id"),
    ([{"label": f"s{i}"} for i in range(16)], "too_many_steps"),
])
def test_invalid_steps_are_rejected_with_a_code(steps, code):
    with pytest.raises(PlaybookDraftError) as excinfo:
        normalize_steps(steps)
    assert excinfo.value.code == code


def test_objections_only_accept_the_categories_c04_extracts():
    entries = normalize_objections([
        {"category": "price", "guidance": "Compara con el coste de un comercial"},
        {"category": "timing", "guidance": "   "},  # not written yet: dropped, not an error
    ])
    assert entries == [{
        "entry_id": "objection:price", "category": "price",
        "guidance": "Compara con el coste de un comercial", "source_ref": "editor",
    }]
    with pytest.raises(PlaybookDraftError) as excinfo:
        normalize_objections([{"category": "budget", "guidance": "x"}])
    assert excinfo.value.code == "bad_category"
    with pytest.raises(PlaybookDraftError) as excinfo:
        normalize_objections([{"category": "price", "guidance": "a"}, {"category": "price", "guidance": "b"}])
    assert excinfo.value.code == "duplicate_category"


def test_slug_is_ascii():
    assert slug("Cualificación: ¿quién decide?") == "cualificacion_quien_decide"


def test_editor_view_hides_the_legacy_whole_document_entry():
    view = editor_view({
        "steps": [{"step_id": "imported", "label": "Todo", "criterion": "texto largo"}],
        "entries": [{"category": "process", "guidance": "texto largo"}, {"category": "price", "guidance": "ROI"}],
    })
    assert view["steps"] == [{"step_id": "imported", "label": "Todo", "criterion": "texto largo"}]
    assert view["objections"] == [{"category": "price", "guidance": "ROI"}]


# --- HTTP ---


class _NoFlags:
    """get_supabase stand-in: every flag lookup finds no company override."""

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

    def make(role="owner", sales_role=None):
        app = FastAPI()
        app.include_router(playbooks_router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id="u", role=role, status="active", sales_role=sales_role,
        )
        app.dependency_overrides[get_supabase] = lambda: _NoFlags()
        return TestClient(app)

    yield make
    set_playbook_repository(None)
    feature_flags.clear_cache()


DRAFT = {
    "steps": [
        {"label": "Apertura", "criterion": "Se presenta y pide 2 minutos", "step_id": "opening"},
        {"label": "Descubrir el dolor", "criterion": "Pregunta cómo gestionan hoy los leads"},
    ],
    "objections": [{"category": "price", "guidance": "Compara con el coste de un comercial"}],
}


def test_owner_saves_a_structured_draft_and_reads_it_back(client_for):
    client = client_for()
    saved = client.put("/api/v1/playbooks/discovery/draft", json=DRAFT)
    assert saved.status_code == 200
    body = client.get("/api/v1/playbooks/discovery/editor").json()
    assert body["source"] == "draft"
    assert [s["step_id"] for s in body["steps"]] == ["opening", "descubrir_el_dolor"]
    assert body["objections"] == [{"category": "price", "guidance": "Compara con el coste de un comercial"}]
    assert "price" in body["categories"]


def test_publishing_the_draft_makes_it_the_live_version(client_for):
    client = client_for()
    client.put("/api/v1/playbooks/discovery/draft", json=DRAFT)
    assert client.post("/api/v1/playbooks/discovery/publish").status_code == 200
    body = client.get("/api/v1/playbooks/discovery/editor").json()
    assert body["source"] == "published"
    assert len(body["steps"]) == 2


def test_a_rep_reads_only_the_live_version_and_cannot_save(client_for):
    client_for().put("/api/v1/playbooks/discovery/draft", json=DRAFT)
    rep = client_for(role="member")
    assert rep.get("/api/v1/playbooks/discovery/editor").json()["source"] == "empty"
    assert rep.put("/api/v1/playbooks/discovery/draft", json=DRAFT).status_code == 403


def test_an_invalid_draft_is_422_with_a_code(client_for):
    response = client_for().put("/api/v1/playbooks/discovery/draft", json={"steps": [], "objections": []})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_steps"
