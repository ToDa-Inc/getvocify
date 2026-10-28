"""«Cómo trabajamos» of a call type (/api/v1/playbooks/{key}/conduct, migration 087)."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbooks import router
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.copilot import live_context
from app.services.playbooks import conduct
from app.services.playbooks.conduct import InMemoryConductStore, SqlConductStore, set_conduct_store
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository

URL = "/api/v1/playbooks/discovery/conduct"
WRITTEN = {
    "goal": "Una demo con alguien que tenga una necesidad real",
    "also_good": "Encontrar a quien decide; descalificar si no hay encaje",
    "stop_when": "No hay necesidad tras explorarla o un no claro",
    "criteria": ["No asumir dolor.", "  ", "Saber terminar   sin forzar."],
}


@pytest.fixture(autouse=True)
def _clean():
    yield
    set_conduct_store(None)
    set_playbook_repository(None)
    live_context.clear()


def make_client(role="owner", store=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co-1", user_id="u-1", role=role, status="active", sales_role=None)
    app.dependency_overrides[get_supabase] = lambda: object()
    set_playbook_repository(InMemoryPlaybookRepository())
    memory = store or InMemoryConductStore()
    set_conduct_store(memory)
    client = TestClient(app)
    client.store = memory
    return client


def test_written_once_it_is_read_back_trimmed_and_an_empty_one_clears_it():
    client = make_client()
    assert client.get(URL).json() == {"conduct": conduct.empty()}
    saved = client.put(URL, json=WRITTEN).json()["conduct"]
    assert saved["criteria"] == ["No asumir dolor.", "Saber terminar sin forzar."]
    assert client.get(URL).json()["conduct"] == saved
    assert client.put(URL, json=conduct.empty()).json() == {"conduct": conduct.empty()}
    assert client.store.get("co-1", "discovery") is None


def test_saving_it_reaches_the_next_card_at_once():
    client = make_client()
    async def stale():
        await live_context.cached(("conduct", "co-1", "discovery"), lambda: None)
    import asyncio

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(live_context, "ttl_s", lambda: 60.0)
        asyncio.run(stale())
        client.put(URL, json=WRITTEN)
        assert asyncio.run(live_context.cached(("conduct", "co-1", "discovery"), lambda: "read again")).value == "read again"


def test_only_a_manager_writes_it_and_too_many_criteria_are_refused():
    assert make_client(role="member").put(URL, json=WRITTEN).status_code == 403
    assert make_client(role="member").get(URL).status_code == 403
    assert make_client().put(URL, json={**WRITTEN, "criteria": ["x"] * 9}).status_code == 422


def test_before_the_migration_it_says_not_activated_and_the_brain_reads_none():
    class Missing:
        def table(self, name):
            return self

        def select(self, *a):
            return self

        def eq(self, *a):
            return self

        def limit(self, *a):
            return self

        def execute(self):
            raise Exception("{'code': '42703', 'message': 'column playbooks.conduct does not exist'}")

    set_playbook_repository(InMemoryPlaybookRepository())
    client = make_client(store=SqlConductStore(Missing()))
    assert client.get(URL).status_code == 409 and client.get(URL).json()["detail"] == {"code": "not_activated"}
    assert client.put(URL, json=WRITTEN).status_code == 409
    assert conduct.read_for_brain(Missing(), "co-1", "discovery") is None


def test_the_brain_text_uses_the_usual_goal_when_none_is_written_and_nothing_when_empty():
    text = conduct.brain_text({**WRITTEN, "goal": ""}, "a meeting booked")
    assert text.startswith("COMPANY GOAL FOR THIS TYPE OF CALL")
    assert "- Main goal: a meeting booked" in text and "1. No asumir dolor." in text and "2. Saber terminar sin forzar." in text
    assert conduct.brain_text(conduct.empty(), "a meeting booked") == ""
    assert "HOW THIS COMPANY" not in conduct.brain_text({"goal": "Demo"}, None)
