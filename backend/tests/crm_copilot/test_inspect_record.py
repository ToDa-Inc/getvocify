import pytest

from app.services.crm_copilot.tools import CopilotContext, HubSpotBundle, confirmation_required, execute_tool


class FakeObj:
    def __init__(self, id, **properties):
        self.id = id
        self.properties = properties


class FakeClient:
    async def get(self, path, params=None):
        if "/notes/" in path:
            return {
                "id": path.rsplit("/", 1)[-1],
                "properties": {"hs_note_body": "<p>Ya hemos integrado Pipedrive</p>", "hs_timestamp": "1710000000000"},
            }
        if "/calls/" in path:
            return {
                "id": path.rsplit("/", 1)[-1],
                "properties": {"hs_call_title": "Demo", "hs_call_body": "Quieren Pipedrive", "hs_timestamp": "1"},
            }
        return {}


class FakeAssoc:
    def __init__(self):
        self.calls = []

    async def get_associations(self, object_type, object_id, to_object_type):
        self.calls.append((object_type, object_id, to_object_type))
        return {
            "notes": ["n1"],
            "deals": ["d1"],
            "companies": ["co1"],
            "calls": ["call1"],
            "emails": [],
            "meetings": [],
        }.get(to_object_type, [])


class FakeContacts:
    async def get(self, contact_id, properties=None):
        del properties
        return FakeObj(
            contact_id,
            firstname="Marc",
            lastname="Boixet",
            email="marc.boixet@mathew.ai",
            jobtitle="Sales Manager",
            phone="+34696832039",
            lifecyclestage="opportunity",
            hs_lead_status="IN_PROGRESS",
            hs_analytics_source="OFFLINE",
        )


class FakeDeals:
    async def get(self, deal_id, properties=None):
        del properties
        return FakeObj(deal_id, dealname="mathew.ai", amount="5000", dealstage="appointmentscheduled")


class FakeCompanies:
    async def get(self, company_id, properties=None):
        del properties
        return FakeObj(company_id, name="mathew.ai", domain="mathew.ai")


class FakeTasks:
    async def list_tasks_for_contact(self, contact_id, properties=None):
        del contact_id, properties
        return [{"id": "t1", "subject": "Follow up Pipedrive", "due_date": None}]

    async def list_tasks_for_deal(self, deal_id, properties=None):
        del deal_id, properties
        return []


class FakeSearch:
    def __init__(self, hits):
        self.hits = hits

    async def search_contacts_by_query(self, query, limit=8):
        del query, limit
        return self.hits

    async def search_deals_by_query(self, query, limit=8):
        del query, limit
        return []


def _hs(search_hits=None, assoc=None):
    return HubSpotBundle(
        client=FakeClient(),
        connection={"metadata": {"portal_id": "123", "region": "na1"}},
        search=FakeSearch(search_hits or [FakeObj("c1", firstname="Marc", lastname="Boixet")]),
        contacts=FakeContacts(),
        companies=FakeCompanies(),
        deals=FakeDeals(),
        associations=assoc or FakeAssoc(),
        tasks=FakeTasks(),
        preview=None,
        provider=None,
    )


def _ctx(hs, copilot=None):
    return CopilotContext(supabase=None, user_id="u1", artifacts={"copilot": copilot or {}}, hs=hs)


@pytest.mark.asyncio
async def test_get_contact_reads_notes_fields_deals_tasks():
    result = await execute_tool("get_contact", {"contact_id": "c1"}, _ctx(_hs()))
    assert result["name"] == "Marc Boixet"
    assert result["fields"]["lifecyclestage"] == "opportunity"
    assert result["fields"]["hs_lead_status"] == "IN_PROGRESS"
    assert "hs_analytics_source" not in result["fields"]
    assert result["notes"][0]["body"] == "Ya hemos integrado Pipedrive"
    assert result["deals"][0]["name"] == "mathew.ai"
    assert result["tasks"][0]["subject"] == "Follow up Pipedrive"
    assert result["company"]["name"] == "mathew.ai"
    assert result["calls"][0]["title"] == "Demo"


@pytest.mark.asyncio
async def test_inspect_record_uses_last_contact():
    assert not confirmation_required("inspect_record")
    result = await execute_tool("inspect_record", {}, _ctx(_hs(), {"last_contact_id": "c1"}))
    assert result["notes"][0]["body"] == "Ya hemos integrado Pipedrive"
    assert "Pipedrive" in result["notes"][0]["body"]


@pytest.mark.asyncio
async def test_single_search_hit_hydrates_record():
    result = await execute_tool("search_contacts", {"query": "Marc"}, _ctx(_hs()))
    assert len(result["contacts"]) == 1
    assert result["contacts"][0]["notes"][0]["body"] == "Ya hemos integrado Pipedrive"


@pytest.mark.asyncio
async def test_multi_search_stays_thin():
    assoc = FakeAssoc()
    hits = [
        FakeObj("c1", firstname="Marc", lastname="Boixet"),
        FakeObj("c2", firstname="Marc", lastname="Other"),
    ]
    result = await execute_tool("search_contacts", {"query": "Marc"}, _ctx(_hs(hits, assoc)))
    assert len(result["contacts"]) == 2
    assert "notes" not in result["contacts"][0]
    assert assoc.calls == []
