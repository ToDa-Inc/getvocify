"""F07.05: a Pipedrive company can use Ask reads. What Pipedrive cannot read says so."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.crm_copilot.loop import run_copilot_turn
from app.services.crm_copilot.pipedrive_reads import PipedriveReader
from app.services.crm_copilot.tools import OPENAI_TOOLS, CopilotContext, execute_tool, write_blocked

CONNECTION = {
    "id": "pd-1",
    "provider": "pipedrive",
    "metadata": {"api_domain": "https://acme.pipedrive.com", "company_domain": "acme"},
}


class Denied(Exception):
    status_code = 403


class FakeSearch:
    def __init__(self, *, deny=False):
        self.deny = deny

    async def search_persons(self, term, *, fields="name,email,phone", limit=10):
        if self.deny:
            raise Denied("forbidden")
        return [
            {"id": 11, "name": "Marina Ruiz", "emails": ["marina@acme.es"], "phones": ["+34600000000"], "organization": {"id": 5, "name": "Acme"}},
            {"id": 12, "name": "Marina Gil", "emails": [], "phones": []},
        ][:limit]

    async def get_person(self, person_id):
        return {
            "id": int(person_id),
            "name": "Marina Ruiz",
            "first_name": "Marina",
            "last_name": "Ruiz",
            "emails": [{"value": "marina@acme.es", "primary": True}],
            "phones": [{"value": "+34600000000", "primary": True}],
            "org_id": 5,
            "job_title": "CEO",
        }

    async def deals_for_person(self, person_id, *, limit=5):
        return [{"id": 70, "title": "Acme anual", "value": 1200, "currency": "EUR", "stage_id": 3, "status": "open"}]

    async def get_organization(self, org_id):
        return {"id": int(org_id), "name": "Acme", "address": "Madrid"}

    async def search_organizations(self, term, *, limit=10):
        return [{"id": 5, "name": "Acme"}]

    async def search_deals(self, term, *, limit=10):
        return [{"id": 70, "title": "Acme anual", "value": 1200, "currency": "EUR", "stage_id": 3}]

    async def get_deal(self, deal_id):
        return {"id": int(deal_id), "title": "Acme anual", "value": 1200, "currency": "EUR", "stage_id": 3, "person_id": 11}


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(settings, "ASK_VOCIFY_DATA_TOOLS_ENABLED", True)


def _ctx(search=None):
    ctx = CopilotContext(supabase=None, user_id="rep-a", artifacts={})
    ctx.crm = PipedriveReader(search or FakeSearch(), CONNECTION)
    return ctx


async def test_search_contacts_returns_pipedrive_people_with_their_url():
    result = await execute_tool("search_contacts", {"query": "Marina"}, _ctx())
    names = [row["name"] for row in result["contacts"]]
    assert names == ["Marina Ruiz", "Marina Gil"]
    first = result["contacts"][0]
    assert first["contact_id"] == "11"
    assert first["email"] == "marina@acme.es"
    assert first["url"] == "https://acme.pipedrive.com/person/11"
    assert result["provider"] == "pipedrive"


async def test_get_contact_reads_fields_company_and_deals_and_marks_the_rest_unavailable():
    ctx = _ctx()
    result = await execute_tool("get_contact", {"contact_id": "11"}, ctx)
    assert result["name"] == "Marina Ruiz"
    assert result["jobtitle"] == "CEO"
    assert result["company"]["name"] == "Acme"
    assert result["deals"][0]["deal_id"] == "70"
    assert result["deals"][0]["url"] == "https://acme.pipedrive.com/deal/70"
    assert result["coverage"] == "partial"
    assert result["reason"] == "not_available_for_pipedrive"
    assert set(result["unavailable"]) == {"notes", "tasks", "calls", "emails"}
    assert "notes" not in result
    assert ctx.artifacts["crm_coverage"] == "partial"


async def test_inspect_record_uses_the_contact_in_focus():
    ctx = _ctx()
    ctx.artifacts["copilot"] = {"last_contact_id": "11"}
    result = await execute_tool("inspect_record", {}, ctx)
    assert result["contact_id"] == "11"


@pytest.mark.parametrize("name", ["list_notes", "list_tasks"])
async def test_notes_and_tasks_are_not_available_for_pipedrive_not_empty(name):
    result = await execute_tool(name, {"contact_id": "11"}, _ctx())
    assert result["ok"] is False
    assert result["coverage"] == "unavailable"
    assert result["reason"] == "not_available_for_pipedrive"
    assert result["items"] == []
    assert "notes" not in result and "tasks" not in result


async def test_deals_companies_and_associations_read_from_pipedrive():
    ctx = _ctx()
    deals = await execute_tool("search_deals", {"query": "Acme"}, ctx)
    assert deals["deals"][0]["name"] == "Acme anual"
    assert deals["deals"][0]["amount"] == 1200
    deal = await execute_tool("get_deal", {"deal_id": "70"}, ctx)
    assert deal["deal_url"] == "https://acme.pipedrive.com/deal/70"
    companies = await execute_tool("search_companies", {"query": "Acme"}, ctx)
    assert companies["companies"][0]["url"] == "https://acme.pipedrive.com/organization/5"
    company = await execute_tool("get_company", {"company_id": "5"}, ctx)
    assert company["name"] == "Acme"
    associated = await execute_tool("list_associated_deals", {"contact_id": "11"}, ctx)
    assert associated["deals"][0]["deal_id"] == "70"


async def test_a_pipedrive_403_is_forbidden_not_nothing_found():
    result = await execute_tool("search_contacts", {"query": "Marina"}, _ctx(FakeSearch(deny=True)))
    assert result["ok"] is False
    assert result["coverage"] == "forbidden"
    assert "contacts" not in result


async def test_a_pipedrive_write_is_refused_before_asking_to_confirm():
    ctx = _ctx()
    blocked = await write_blocked("create_note", ctx)
    assert blocked["coverage"] == "unavailable"
    assert blocked["reason"] == "not_available_for_pipedrive"
    assert await write_blocked("search_contacts", ctx) is None

    class FakeLLM:
        def __init__(self):
            self.rounds = 0

        async def chat_tools(self, messages, **_kwargs):
            self.rounds += 1
            if self.rounds == 1:
                return SimpleNamespace(
                    content=None,
                    tool_calls=[{"id": "tc-1", "name": "create_note", "arguments": {"body": "hola", "contact_id": "11"}}],
                    raw_message=None,
                )
            assert "not_available_for_pipedrive" in messages[-1]["content"]
            return SimpleNamespace(content="En Pipedrive aún no puedo crear notas.", tool_calls=[], raw_message=None)

    result = await run_copilot_turn("anota hola", artifacts=ctx.artifacts, llm=FakeLLM(), tools=OPENAI_TOOLS, system="s", ctx=ctx)
    assert result.kind == "text"
    assert "pending_tool" not in ctx.artifacts["copilot"]


async def test_a_hubspot_write_still_pauses_for_confirmation():
    ctx = CopilotContext(supabase=None, user_id="rep-a", artifacts={}, hs=object())
    assert await write_blocked("create_note", ctx) is None
