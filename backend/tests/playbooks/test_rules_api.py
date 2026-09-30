"""T7 endpoints: GET /playbooks details, /catalog, POST /types with a rule, PUT /{key}/rule, /deal-stages."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import playbook_rules
from app.api.playbook_rules import router as rules_router
from app.api.playbooks import router as playbooks_router, set_playbook_store
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.catalog import default_applies_to
from app.services.playbooks.store import MemoryPlaybookStore


@pytest.fixture(autouse=True)
def _clean():
    feature_flags.clear_cache()
    playbook_rules.clear_deal_stages_cache()
    yield
    feature_flags.clear_cache()
    playbook_rules.clear_deal_stages_cache()
    set_playbook_store(None)


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


def _client(store=None, role="owner", sales_role=None):
    # The real router order: rules first, so /catalog and /deal-stages are never a {key}.
    app = FastAPI()
    app.include_router(rules_router)
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="u-1", role=role, status="active", sales_role=sales_role,
    )
    app.dependency_overrides[get_supabase] = lambda: _FlagSupabase()
    set_playbook_store(store or MemoryPlaybookStore({}, {}))
    return TestClient(app)


def _routing(monkeypatch, on=True):
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", on)


# -- GET /playbooks details ------------------------------------------------------------------


def test_list_adds_details_for_every_type(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    store = MemoryPlaybookStore({"co-1": {"discovery": "published", "renewal": "missing", "qualification": "missing"}}, {})
    rule = {"role": "ae", "channels": ["call"], "contact": "contacted", "deal_stages": []}
    store.save_type_meta("co-1", "renewal", label="Renovación", applies_to=rule)
    body = _client(store).get("/api/v1/playbooks").json()
    assert body["details"]["discovery"] == {
        "label": None,
        "role": "sdr",
        "applies_to": default_applies_to("discovery"),
        "goal": "meeting_booked",
        "catalog": True,
        "step_count": 0, "answer_count": 0, "criteria_count": 0, "has_draft": False, "paused": False,
    }
    assert body["details"]["renewal"] == {
        "label": "Renovación", "role": "ae", "applies_to": rule, "goal": None, "catalog": False,
        "step_count": 0, "answer_count": 0, "criteria_count": 0, "has_draft": False, "paused": False,
    }
    assert body["details"]["qualification"] == {
        "label": None, "role": None, "applies_to": None, "goal": None, "catalog": False,
        "step_count": 0, "answer_count": 0, "criteria_count": 0, "has_draft": False, "paused": False,
    }


def test_details_follow_the_role_filter(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    store = MemoryPlaybookStore(
        {"co-1": {"discovery": "published", "inbound": "draft", "closing": "published", "negotiation": "missing", "renewal": "missing"}}, {},
    )
    store.save_type_meta("co-1", "renewal", label="Renovación", applies_to={"role": "any", "channels": [], "contact": "any", "deal_stages": []})
    sdr = _client(store, role="member", sales_role="sdr").get("/api/v1/playbooks").json()
    assert set(sdr["motions"]) == {"discovery", "inbound", "renewal"}
    assert set(sdr["details"]) == set(sdr["motions"])
    ae = _client(store, role="member", sales_role="ae").get("/api/v1/playbooks").json()
    assert set(ae["motions"]) == {"closing", "negotiation", "renewal"}
    manager = _client(store, role="admin", sales_role="sdr").get("/api/v1/playbooks").json()
    assert set(manager["details"]) == {"discovery", "inbound", "closing", "negotiation", "renewal"}


# -- GET /catalog ----------------------------------------------------------------------------


def test_catalog_lists_the_five_types_for_any_member():
    for role in ("member", "owner"):
        body = _client(role=role).get("/api/v1/playbooks/catalog").json()
        assert [entry["key"] for entry in body["types"]] == ["discovery", "inbound", "ae_discovery", "closing", "negotiation"]
        first = body["types"][0]
        assert first["label"] == {"es": "Llamada en frío", "en": "Cold call"}
        assert first["applies_to"]["role"] == "sdr"
        assert len(first["template"]["es"]) == len(first["template"]["en"]) >= 4
        assert set(first["template"]["es"][0]) == {"step_id", "label", "criterion"}


def test_catalog_is_not_read_as_a_playbook_key():
    # /catalog is a single segment, but the rules router goes first regardless.
    response = _client().get("/api/v1/playbooks/catalog")
    assert response.status_code == 200 and "types" in response.json()


# -- POST /types -----------------------------------------------------------------------------


def test_a_custom_type_without_a_rule_is_422_when_routing_is_on(monkeypatch):
    _routing(monkeypatch)
    client = _client()
    response = client.post("/api/v1/playbooks/types", json={"type_key": "renewal", "name": "Renovación"})
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "rule_required"}
    assert "renewal" not in client.get("/api/v1/playbooks").json()["motions"]


def test_a_custom_type_with_a_rule_is_saved_with_its_label(monkeypatch):
    _routing(monkeypatch)
    rule = {"role": "ae", "channels": ["call"], "contact": "contacted", "deal_stages": ["renewal_due"]}
    response = _client().post(
        "/api/v1/playbooks/types", json={"type_key": "renewal", "name": "Renovación", "applies_to": rule},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["motions"]["renewal"] == "missing"
    assert body["details"]["renewal"] == {"label": "Renovación", "role": "ae", "applies_to": rule, "goal": None, "catalog": False, "paused": False}


def test_a_bad_rule_on_a_new_type_is_422_bad_rule(monkeypatch):
    _routing(monkeypatch)
    response = _client().post(
        "/api/v1/playbooks/types", json={"type_key": "renewal", "name": "R", "applies_to": {"role": "boss"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "bad_rule"}


def test_a_catalog_type_gets_its_default_rule_and_a_label(monkeypatch):
    _routing(monkeypatch)
    response = _client().post("/api/v1/playbooks/types", json={"type_key": "ae_discovery", "name": ""})
    assert response.status_code == 200
    detail = response.json()["details"]["ae_discovery"]
    assert detail["applies_to"] == default_applies_to("ae_discovery")
    assert detail["label"] == "Discovery"
    assert detail["catalog"] is True and detail["role"] == "ae" and detail["goal"] == "demo_booked"
    assert response.json()["motions"]["ae_discovery"] == "missing"


def test_a_catalog_type_keeps_the_name_it_was_given(monkeypatch):
    _routing(monkeypatch)
    response = _client().post("/api/v1/playbooks/types", json={"type_key": "inbound", "name": "Formularios web"})
    assert response.json()["details"]["inbound"]["label"] == "Formularios web"


def test_routing_off_keeps_todays_behaviour(monkeypatch):
    _routing(monkeypatch, on=False)
    client = _client()
    created = client.post("/api/v1/playbooks/types", json={"type_key": "renewal", "name": "Renovación"})
    assert created.status_code == 200
    assert created.json()["motions"]["renewal"] == "missing"
    assert created.json()["details"]["renewal"]["applies_to"] is None


def test_a_member_cannot_add_a_type_and_gets_403_before_any_rule_check(monkeypatch):
    _routing(monkeypatch)
    response = _client(role="member").post("/api/v1/playbooks/types", json={"type_key": "renewal", "name": "R"})
    assert response.status_code == 403


# -- PUT /{key}/rule -------------------------------------------------------------------------


def test_put_rule_saves_it_and_details_show_it(monkeypatch):
    store = MemoryPlaybookStore({"co-1": {"closing": "published"}}, {})
    client = _client(store)
    rule = {"role": "ae", "channels": ["meeting"], "contact": "contacted", "deal_stages": ["contract", 7]}
    response = client.put("/api/v1/playbooks/closing/rule", json={"applies_to": rule})
    assert response.status_code == 200
    saved = {"role": "ae", "channels": ["meeting"], "contact": "contacted", "deal_stages": ["contract", "7"]}
    assert response.json() == {"sales_motion_key": "closing", "applies_to": saved}
    assert client.get("/api/v1/playbooks").json()["details"]["closing"]["applies_to"] == saved


def test_put_rule_on_a_catalog_type_that_was_never_created_lists_it():
    client = _client()
    assert client.put(
        "/api/v1/playbooks/negotiation/rule",
        json={"applies_to": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": ["proposal"]}},
    ).status_code == 200
    assert client.get("/api/v1/playbooks").json()["motions"]["negotiation"] == "missing"


@pytest.mark.parametrize(
    "applies_to",
    [{}, {"role": "boss"}, {"role": "ae", "channels": ["sms"]}, {"role": "ae", "contact": "x"}, {"role": "ae", "deal_stages": "won"}],
)
def test_put_rule_validates_the_schema(applies_to):
    store = MemoryPlaybookStore({"co-1": {"closing": "published"}}, {})
    response = _client(store).put("/api/v1/playbooks/closing/rule", json={"applies_to": applies_to})
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "bad_rule"}


def test_put_rule_is_for_owner_and_admin_only():
    store = MemoryPlaybookStore({"co-1": {"closing": "published"}}, {})
    rule = {"applies_to": {"role": "ae"}}
    assert _client(store, role="member").put("/api/v1/playbooks/closing/rule", json=rule).status_code == 403
    assert _client(store, role="admin").put("/api/v1/playbooks/closing/rule", json=rule).status_code == 200
    assert _client(store, role="owner").put("/api/v1/playbooks/closing/rule", json=rule).status_code == 200


def test_put_rule_on_an_unknown_type_is_404():
    assert _client().put("/api/v1/playbooks/ghost/rule", json={"applies_to": {"role": "ae"}}).status_code == 404


# -- GET /deal-stages ------------------------------------------------------------------------


class _Stage:
    def __init__(self, id, label, order=0):
        self.id, self.label, self.displayOrder = id, label, order


class _Pipeline:
    def __init__(self, label, stages):
        self.label, self.stages = label, stages


def _patch_crm(monkeypatch, *, hubspot=None, pipedrive=None):
    from app.api import crm, crm_pipedrive

    async def missing(**_kw):
        raise RuntimeError("no connection")

    async def hub(**_kw):
        return hubspot

    async def pipe(**_kw):
        return pipedrive

    monkeypatch.setattr(crm, "get_hubspot_pipelines", hub if hubspot is not None else missing)
    monkeypatch.setattr(crm_pipedrive, "pipedrive_pipelines", pipe if pipedrive is not None else missing)


def test_deal_stages_are_empty_without_a_crm(monkeypatch):
    _patch_crm(monkeypatch)
    assert _client().get("/api/v1/playbooks/deal-stages").json() == {"stages": []}


def test_deal_stages_of_the_connected_hubspot(monkeypatch):
    _patch_crm(monkeypatch, hubspot=[_Pipeline("Ventas", [_Stage("s2", "Propuesta", 2), _Stage("s1", "Cita", 1)])])
    body = _client().get("/api/v1/playbooks/deal-stages").json()
    assert body == {"stages": [{"id": "s1", "label": "Cita"}, {"id": "s2", "label": "Propuesta"}]}


def test_deal_stages_fall_back_to_pipedrive_and_name_the_pipeline_when_there_are_several(monkeypatch):
    _patch_crm(
        monkeypatch,
        pipedrive=[_Pipeline("A", [_Stage("1", "Lead", 1)]), _Pipeline("B", [_Stage("9", "Lead", 1)])],
    )
    body = _client().get("/api/v1/playbooks/deal-stages").json()
    assert body == {"stages": [{"id": "1", "label": "A · Lead"}, {"id": "9", "label": "B · Lead"}]}


def test_deal_stages_are_cached_per_company_and_errors_are_not(monkeypatch):
    calls = []
    from app.api import crm

    async def hub(**_kw):
        calls.append(1)
        return [_Pipeline("Ventas", [_Stage("s1", "Cita", 1)])]

    _patch_crm(monkeypatch, pipedrive=None)
    monkeypatch.setattr(crm, "get_hubspot_pipelines", hub)
    client = _client()
    assert client.get("/api/v1/playbooks/deal-stages").json()["stages"][0]["id"] == "s1"
    assert client.get("/api/v1/playbooks/deal-stages").json()["stages"][0]["id"] == "s1"
    assert len(calls) == 1


def test_a_failing_crm_is_an_empty_list_not_an_error(monkeypatch):
    from app.api import crm, crm_pipedrive

    async def boom(**_kw):
        raise ConnectionError("hubspot down")

    monkeypatch.setattr(crm, "get_hubspot_pipelines", boom)
    monkeypatch.setattr(crm_pipedrive, "pipedrive_pipelines", boom)
    response = _client().get("/api/v1/playbooks/deal-stages")
    assert response.status_code == 200
    assert response.json() == {"stages": []}
