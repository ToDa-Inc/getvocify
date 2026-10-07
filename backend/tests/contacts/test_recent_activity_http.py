"""GET /contacts/{contact_id}/recent-activity: the contact's latest interactions, read from HubSpot and Vocify,
and a short summary that may only say what those interactions say."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import contact_activity as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership

MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")
CONTACT = "901"
DAY = 24 * 3600 * 1000
NOW_MS = 1_791_000_000_000  # 2026-10-03T04:00:00Z


class HubSpotError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HubSpot {status}")
        self.status_code = status


class FakeHubSpot:
    """HubSpot as the endpoint reads it: v4 associations from the contact, then a batch read per object type."""

    def __init__(self, objects: dict[str, list[dict]], *, forbidden: set[str] = frozenset(), company=None):
        self.objects = objects
        self.forbidden = forbidden
        self.company = company

    async def get(self, endpoint, params=None):
        prefix = f"/crm/v4/objects/contacts/{CONTACT}/associations/"
        if endpoint.startswith(prefix):
            kind = endpoint[len(prefix):]
            if kind in self.forbidden:
                raise HubSpotError(403)
            if kind == "companies":
                return {"results": [{"toObjectId": self.company["id"]}]} if self.company else {"results": []}
            return {"results": [{"toObjectId": o["id"]} for o in self.objects.get(kind, [])]}
        if self.company and endpoint == f"/crm/v3/objects/companies/{self.company['id']}":
            return {"id": self.company["id"], "properties": self.company["properties"]}
        raise AssertionError(f"unexpected GET {endpoint}")

    async def post(self, endpoint, data=None):
        kind = endpoint.split("/")[4]
        wanted = {i["id"] for i in data["inputs"]}
        return {"results": [{"id": o["id"], "properties": o["properties"]} for o in self.objects.get(kind, []) if o["id"] in wanted]}


NOTE = {"id": "n1", "properties": {"hs_timestamp": str(NOW_MS - 2 * DAY), "hs_note_body": "<p>Wants pricing for <b>12 seats</b>.</p>"}}
CALL = {"id": "c1", "properties": {"hs_timestamp": str(NOW_MS - 5 * DAY), "hs_call_title": "Discovery", "hs_call_body": "Talked about the pilot.", "hs_call_disposition": "f240bbac-87c9-4f6e-bf70-924b57d47db7", "hs_call_direction": "OUTBOUND"}}
MEETING = {"id": "m1", "properties": {"hs_timestamp": str(NOW_MS - 1 * DAY), "hs_meeting_title": "Demo", "hs_meeting_body": "Demo with the ops team."}}
TASK = {"id": "t1", "properties": {"hs_timestamp": str(NOW_MS + 2 * DAY), "hs_task_subject": "Send proposal", "hs_task_status": "NOT_STARTED"}}
EMAIL = {"id": "e1", "properties": {"hs_timestamp": str(NOW_MS - 3 * DAY), "hs_email_subject": "Proposal", "hs_email_text": "Here it is.", "hs_email_direction": "EMAIL"}}
COMPANY = {"id": "co77", "properties": {"name": "Acme SL", "domain": "acme.es", "industry": "Logistics", "numberofemployees": "120"}}
MEMO = {
    "id": "memo-1",
    "created_at": "2026-09-30T10:00:00+00:00",
    "capture_started_at": None,
    "user_id": "rep-1",
    "extraction": {"summary": "Ana confirmed the budget for Q4. Next: send the proposal."},
}


@pytest.fixture
def world(monkeypatch):
    state = {"hubspot": FakeHubSpot({"notes": [NOTE], "calls": [CALL], "meetings": [MEETING], "tasks": [TASK]}, forbidden={"emails"}, company=COMPANY), "memos": [MEMO], "llm": None, "llm_calls": 0}

    monkeypatch.setattr(api, "hubspot_client_for", lambda _supabase, _user_id: state["hubspot"])
    monkeypatch.setattr(api, "read_contact_memos", lambda _supabase, _membership, _contact_id: state["memos"])

    async def summarize(messages):
        state["llm_calls"] += 1
        state["last_prompt"] = messages
        if isinstance(state["llm"], Exception):
            raise state["llm"]
        return state["llm"]

    monkeypatch.setattr(api, "summarize_json", summarize)
    api.clear_cache()
    return state


@pytest.fixture
def client(world):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: MEMBERSHIP
    app.dependency_overrides[get_supabase] = lambda: object()
    return TestClient(app)


def get(client, **params):
    response = client.get(f"/api/v1/contacts/{CONTACT}/recent-activity", params={"connection_id": "hubspot", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_returns_the_interactions_it_read_newest_first_with_their_ids(client):
    body = get(client, summary="false")
    ids = [i["id"] for i in body["interactions"]]
    # task due 5 Oct, meeting 2 Oct, note 1 Oct, Vocify conversation 30 Sep, call 28 Sep
    assert ids == ["hubspot:task:t1", "hubspot:meeting:m1", "hubspot:note:n1", "vocify:memo:memo-1", "hubspot:call:c1"]
    note = next(i for i in body["interactions"] if i["id"] == "hubspot:note:n1")
    assert note["type"] == "note"
    assert note["text"] == "Wants pricing for 12 seats."
    assert note["occurred_at"] == "2026-10-01T04:00:00Z"
    memo = next(i for i in body["interactions"] if i["id"] == "vocify:memo:memo-1")
    assert (memo["type"], memo["text"]) == ("vocify_conversation", "Ana confirmed the budget for Q4.")


def test_company_context_comes_from_hubspot(client):
    body = get(client, summary="false")
    assert body["company"] == {"id": "hubspot:company:co77", "name": "Acme SL", "domain": "acme.es", "industry": "Logistics", "employees": "120"}


def test_says_which_sources_could_not_be_read_instead_of_hiding_them(client):
    body = get(client, summary="false")
    assert body["sources"]["hubspot"]["emails"] == "not_allowed"
    assert body["sources"]["hubspot"]["notes"] == "read"
    assert body["sources"]["vocify"] == "read"


def test_emails_are_included_when_the_connection_may_read_them(client, world):
    world["hubspot"] = FakeHubSpot({"emails": [EMAIL]}, company=None)
    body = get(client, summary="false")
    email = next(i for i in body["interactions"] if i["id"] == "hubspot:email:e1")
    assert (email["type"], email["text"]) == ("email", "Proposal — Here it is.")
    assert body["sources"]["hubspot"]["emails"] == "read"
    assert body["company"] is None


def test_the_summary_keeps_only_lines_grounded_in_what_was_read(client, world):
    world["llm"] = {
        "lines": [
            {"text": "Demo with the ops team yesterday; proposal still to send.", "sources": ["hubspot:meeting:m1", "hubspot:task:t1"]},
            {"text": "Their CFO approved the budget.", "sources": ["hubspot:email:e999"]},
            {"text": "Wants pricing for 12 seats.", "sources": []},
        ]
    }
    body = get(client)
    assert body["summary"]["lines"] == [
        {"text": "Demo with the ops team yesterday; proposal still to send.", "sources": ["hubspot:meeting:m1", "hubspot:task:t1"]},
    ]
    # The model saw only what was read, with the ids it must cite.
    prompt = str(world["last_prompt"])
    assert "hubspot:note:n1" in prompt and "Wants pricing for 12 seats." in prompt


def test_a_model_failure_still_returns_the_interactions(client, world):
    world["llm"] = RuntimeError("Together AI down")
    body = get(client)
    assert body["summary"] is None
    assert len(body["interactions"]) == 5


def test_nothing_to_summarize_asks_no_model(client, world):
    world["hubspot"] = FakeHubSpot({}, company=None)
    world["memos"] = []
    body = get(client)
    assert body["interactions"] == []
    assert body["summary"] is None
    assert world["llm_calls"] == 0


def test_the_same_interactions_are_summarized_once(client, world):
    world["llm"] = {"lines": [{"text": "Demo yesterday.", "sources": ["hubspot:meeting:m1"]}]}
    get(client)
    get(client)
    assert world["llm_calls"] == 1


def test_hubspot_unreachable_still_answers_with_vocify(client, world):
    class Down:
        async def get(self, *_a, **_k):
            raise HubSpotError(500)

        async def post(self, *_a, **_k):
            raise HubSpotError(500)

    world["hubspot"] = Down()
    body = get(client, summary="false")
    assert [i["id"] for i in body["interactions"]] == ["vocify:memo:memo-1"]
    assert body["sources"]["hubspot"]["notes"] == "failed"


def test_ids_cited_the_way_the_prompt_shows_them_still_count(client, world):
    # The prompt lists items as "[hubspot:meeting:m1] ..."; a model citing them with the brackets is citing them.
    world["llm"] = {"lines": [{"text": "Demo yesterday.", "sources": ["[hubspot:meeting:m1]", " hubspot:task:t1 "]}]}
    body = get(client)
    assert body["summary"]["lines"] == [{"text": "Demo yesterday.", "sources": ["hubspot:meeting:m1", "hubspot:task:t1"]}]


def test_a_summary_left_with_no_lines_is_asked_again_next_time(client, world):
    world["llm"] = {"lines": [{"text": "Their CFO approved it.", "sources": ["hubspot:email:e999"]}]}
    assert get(client)["summary"] == {"lines": [], "model": body_model()}
    world["llm"] = {"lines": [{"text": "Demo yesterday.", "sources": ["hubspot:meeting:m1"]}]}
    assert get(client)["summary"]["lines"] == [{"text": "Demo yesterday.", "sources": ["hubspot:meeting:m1"]}]
    assert world["llm_calls"] == 2


def body_model():
    from app.config import settings

    return settings.EXTRACTION_MODEL
