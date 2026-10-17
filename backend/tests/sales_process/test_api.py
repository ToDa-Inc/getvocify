"""The company's own sales process (/api/v1/sales-process): a list of types it names, orders and describes."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.sales_process import router
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository
from app.services.sales_process.store import InMemorySalesProcessStore, SqlSalesProcessStore, set_sales_process_store
from tests.reporting.fake_db import FakeDB

BASE = "/api/v1/sales-process"
STEP = {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta."}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "SALES_PROCESS_ENABLED", True)
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()
    set_playbook_repository(None)
    set_sales_process_store(None)


def make_client(*, role="owner", db=None, store="memory"):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co-1", user_id="u-1", role=role, status="active", sales_role=None)
    database = db if db is not None else FakeDB()
    app.dependency_overrides[get_supabase] = lambda: database
    repo = InMemoryPlaybookRepository()
    set_playbook_repository(repo)
    set_sales_process_store(InMemorySalesProcessStore() if store == "memory" else None)
    client = TestClient(app)
    client.repo = repo
    client.store = InMemorySalesProcessStore() if store != "memory" else None
    return client


def put(client, *types):
    return client.put(BASE, json={"types": list(types)})


def t(label, stage="first_contact", **extra):
    return {"label": label, **({"stage": stage}), **extra}


def test_only_an_owner_or_admin_may_and_only_with_the_flag(monkeypatch):
    assert make_client(role="member").get(BASE).status_code == 403
    monkeypatch.setattr(settings, "SALES_PROCESS_ENABLED", False)
    feature_flags.clear_cache()
    assert make_client().get(BASE).status_code == 404


def test_before_the_tables_exist_it_says_so_calmly():
    class Missing(FakeDB):
        def table(self, name):
            raise RuntimeError(f"Could not find the table 'public.{name}' in the schema cache")

    client = make_client(db=Missing(), store="sql")
    response = client.get(BASE)
    assert response.status_code == 503 and response.json()["detail"] == {"code": "not_activated"}


def test_a_company_that_never_defined_a_process_sees_the_types_it_already_has():
    client = make_client()
    client.repo.save_draft("co-1", "discovery", [STEP], [])
    client.repo.save_draft("co-1", "closing", [STEP], [])
    body = client.get(BASE).json()["types"]
    assert [x["key"] for x in body] == ["discovery", "closing"]
    assert [x["stage"] for x in body] == ["first_contact", "deal"]
    assert body[0]["label"] == "Llamada en frío" and body[0]["step_count"] == 1


def test_defining_the_process_creates_the_types_in_order_with_what_each_is_for():
    client = make_client()
    done = put(client, t("Llamada en frío", recognize="Primer contacto en frío."), t("Discovery"), t("Demo", "deal"))
    assert done.status_code == 200
    types = done.json()["types"]
    assert [x["label"] for x in types] == ["Llamada en frío", "Discovery", "Demo"]
    assert [x["stage"] for x in types] == ["first_contact", "first_contact", "deal"]
    assert types[0]["recognize"] == "Primer contacto en frío."
    assert client.get(BASE).json()["types"] == types
    kept = client.repo.list_types("co-1")
    assert all(kept[x["key"]]["label"] == x["label"] for x in types)


def test_a_name_that_is_a_catalog_key_does_not_become_that_catalog_type():
    client = make_client()
    [only] = put(client, t("Discovery")).json()["types"]
    assert only["key"] not in ("discovery", "ae_discovery") and only["label"] == "Discovery"


def test_renaming_and_reordering_keeps_the_keys_and_what_was_built():
    client = make_client()
    first = put(client, t("Llamada en frío"), t("Demo", "deal")).json()["types"]
    cold, demo = first[0]["key"], first[1]["key"]
    client.repo.save_draft("co-1", cold, [STEP], [])
    again = put(client, {"key": demo, "label": "Demo y propuesta", "stage": "deal"}, {"key": cold, "label": "Prospección", "stage": "first_contact"}).json()["types"]
    assert [x["key"] for x in again] == [demo, cold] and [x["label"] for x in again] == ["Demo y propuesta", "Prospección"]
    assert again[1]["step_count"] == 1


def test_removing_a_type_archives_it_and_takes_it_out_of_every_members_list():
    client = make_client()
    types = put(client, t("Llamada en frío"), t("Demo", "deal")).json()["types"]
    cold, demo = types[0]["key"], types[1]["key"]
    from app.services.sales_process.store import get_sales_process_store

    store = get_sales_process_store(None)
    store.set_member_types("co-1", [cold, demo], user_id="u2")
    store.set_member_types("co-1", [demo], user_id="u3")
    after = put(client, {"key": cold, "label": "Llamada en frío", "stage": "first_contact"}).json()["types"]
    assert [x["key"] for x in after] == [cold]
    assert demo not in client.repo.list_types("co-1")  # archived: it no longer lists
    assert store.get_member_types("co-1", user_id="u2") == [cold] and store.get_member_types("co-1", user_id="u3") is None


def test_a_process_needs_names_that_are_there_and_different():
    client = make_client()
    assert put(client).status_code == 422
    assert put(client, t("  ")).status_code == 422
    assert put(client, t("Demo"), t("demo")).json()["detail"] == {"code": "duplicate_name"}
    assert put(client, {"label": "Demo", "stage": "other"}).status_code == 422
    assert put(client, *[t(f"Tipo {i}") for i in range(21)]).status_code == 422
