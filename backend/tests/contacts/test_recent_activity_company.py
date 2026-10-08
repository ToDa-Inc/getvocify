"""GET /contacts/{contact_id}/recent-activity, the company part: what was already said with other people at the
contact's company (HubSpot activity and Vocify conversations), so a rep never pitches from scratch to a company
someone already talked to. Who and when always come from what was read."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import contact_activity as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership

MEMBERSHIP = Membership(id="member-1", company_id="co-1", user_id="rep-1", role="member", status="active")
CONTACT = "901"
TONI = "902"
MARTA = "903"
DAY = 24 * 3600 * 1000
NOW_MS = 1_791_000_000_000  # 2026-10-03T04:00:00Z
PRIMARY = [{"category": "HUBSPOT_DEFINED", "typeId": 1, "label": "Primary"}]
UNLABELED = [{"category": "HUBSPOT_DEFINED", "typeId": 279, "label": None}]


class HubSpotError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HubSpot {status}")
        self.status_code = status


def engagement(kind: str, oid: str, days_ago: float, **props):
    return {"id": oid, "properties": {"hs_timestamp": str(int(NOW_MS - days_ago * DAY)), **props}}


class FakeHubSpot:
    """HubSpot as the endpoint reads it. `activity[(object, id)][kind]` lists the engagements associated with that
    record; `links[(kind, engagement id)]` the contacts an engagement is associated with."""

    def __init__(self, *, companies=None, activity=None, links=None, people=None, company_contacts=None, forbidden=frozenset()):
        self.companies = companies if companies is not None else [{"toObjectId": "co77", "associationTypes": PRIMARY}]
        self.activity = activity or {}
        self.links = links or {}
        self.people = people or {}
        self.company_contacts = company_contacts if company_contacts is not None else [CONTACT, TONI, MARTA]
        self.forbidden = forbidden
        self.calls: list[str] = []

    def _engagements(self, obj, oid, kind):
        return self.activity.get((obj, oid), {}).get(kind, [])

    async def get(self, endpoint, params=None):
        self.calls.append(f"GET {endpoint}")
        parts = endpoint.strip("/").split("/")
        if parts[:3] == ["crm", "v4", "objects"] and parts[5] == "associations":
            obj, oid, kind = parts[3], parts[4], parts[6]
            if kind in self.forbidden:
                raise HubSpotError(403)
            if obj == "contacts" and kind == "companies":
                return {"results": self.companies}
            if obj == "companies" and kind == "contacts":
                return {"results": [{"toObjectId": c, "associationTypes": UNLABELED} for c in self.company_contacts]}
            return {"results": [{"toObjectId": e["id"]} for e in self._engagements(obj, oid, kind)]}
        if parts[:4] == ["crm", "v3", "objects", "companies"]:
            return {"id": parts[4], "properties": {"name": "Acme SL", "domain": "acme.es", "industry": "Logistics"}}
        raise AssertionError(f"unexpected GET {endpoint}")

    async def post(self, endpoint, data=None):
        self.calls.append(f"POST {endpoint}")
        parts = endpoint.strip("/").split("/")
        wanted = [i["id"] for i in data["inputs"]]
        if parts[:3] == ["crm", "v4", "associations"]:
            kind = parts[3]
            return {"results": [{"from": {"id": e}, "to": [{"toObjectId": c} for c in self.links.get((kind, e), [])]} for e in wanted]}
        kind = parts[3]
        if kind == "contacts":
            return {"results": [{"id": c, "properties": self.people[c]} for c in wanted if c in self.people]}
        every = {e["id"]: e for per in self.activity.values() for e in per.get(kind, [])}
        return {"results": [every[e] for e in wanted if e in every]}


PEOPLE = {
    TONI: {"firstname": "Toni", "lastname": "García", "jobtitle": "CFO"},
    MARTA: {"firstname": "Marta", "lastname": "Soler", "jobtitle": ""},
}
TONI_CALL = engagement("calls", "c7", 21, hs_call_title="Pricing", hs_call_body="Asked for a demo for the ops team.")
MARTA_NOTE = engagement("notes", "n8", 40, hs_note_body="Uses an in-house CRM.")
COMPANY_NOTE = engagement("notes", "n9", 60, hs_note_body="Renewal of their current tool is in March.")
OWN_NOTE = engagement("notes", "n1", 2, hs_note_body="Wants pricing for 12 seats.")


def acme(**overrides):
    """Juan (901) works at Acme; Toni and Marta too. HubSpot files activity under the company as well."""
    kwargs = dict(
        activity={
            ("contacts", CONTACT): {"notes": [OWN_NOTE]},
            ("companies", "co77"): {"calls": [TONI_CALL], "notes": [OWN_NOTE, MARTA_NOTE, COMPANY_NOTE]},
        },
        links={("calls", "c7"): [TONI], ("notes", "n8"): [MARTA], ("notes", "n1"): [CONTACT], ("notes", "n9"): []},
        people=PEOPLE,
    )
    kwargs.update(overrides)
    return FakeHubSpot(**kwargs)


TONI_MEMO = {
    "id": "memo-7",
    "created_at": "2026-09-01T10:00:00+00:00",
    "capture_started_at": None,
    "user_id": "rep-2",
    "hubspot_contact_id": TONI,
    "extraction": {"summary": "Toni wants to see the reporting before deciding."},
}


@pytest.fixture
def world(monkeypatch):
    state = {
        "hubspot": acme(),
        "memos": [],
        "colleague_memos": [TONI_MEMO],
        "pushed": set(),
        "llm": {"lines": [], "company_lines": []},
        "colleague_reads": [],
    }
    monkeypatch.setattr(api, "hubspot_client_for", lambda _supabase, _user_id: state["hubspot"])
    monkeypatch.setattr(api, "read_contact_memos", lambda _supabase, _membership, _contact_id: state["memos"])

    def colleague_memos(_supabase, _membership, contact_ids):
        state["colleague_reads"].append(sorted(contact_ids))
        return [m for m in state["colleague_memos"] if m["hubspot_contact_id"] in contact_ids]

    monkeypatch.setattr(api, "read_colleague_memos", colleague_memos)
    monkeypatch.setattr(api, "vocify_pushed_ids", lambda _supabase, _company_id, memo_ids: state["pushed"])

    async def summarize(messages):
        state["last_prompt"] = messages
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


def test_the_company_is_its_name_and_nothing_the_rep_already_sees_in_the_crm(client):
    assert get(client, summary="false")["company"] == {"id": "hubspot:company:co77", "name": "Acme SL"}


def test_what_others_at_the_company_said_comes_with_who_said_it_newest_first(client):
    body = get(client, summary="false")
    others = body["company_interactions"]
    assert [i["id"] for i in others] == ["hubspot:call:c7", "vocify:memo:memo-7", "hubspot:note:n8", "hubspot:note:n9"]
    toni = others[0]
    assert (toni["type"], toni["text"], toni["with"]) == ("call", "Pricing — Asked for a demo for the ops team.", {"name": "Toni García", "title": "CFO"})
    assert others[1]["with"] == {"name": "Toni García", "title": "CFO"}
    assert others[1]["text"] == "Toni wants to see the reporting before deciding."
    assert others[2]["with"] == {"name": "Marta Soler", "title": None}
    # Filed on the company itself, with nobody: shown as the company's, never given a person.
    assert others[3]["with"] is None


def test_what_was_already_with_this_contact_is_not_repeated_as_the_company_s(client):
    body = get(client, summary="false")
    assert [i["id"] for i in body["interactions"]] == ["hubspot:note:n1"]
    assert "hubspot:note:n1" not in [i["id"] for i in body["company_interactions"]]


def test_vocify_conversations_are_read_for_the_other_contacts_only(client, world):
    get(client, summary="false")
    assert world["colleague_reads"] == [sorted([TONI, MARTA])]


def test_a_conversation_vocify_recorded_and_pushed_shows_once_as_the_vocify_conversation(client, world):
    # Vocify recorded Toni's call (memo-7) and logged it in HubSpot as call c7: the same conversation.
    world["pushed"] = {"hubspot:call:c7"}
    others = get(client, summary="false")["company_interactions"]
    assert [i["id"] for i in others] == ["vocify:memo:memo-7", "hubspot:note:n8", "hubspot:note:n9"]


def test_the_same_holds_for_the_contact_s_own_activity(client, world):
    world["memos"] = [{"id": "memo-1", "created_at": "2026-10-01T04:00:00+00:00", "capture_started_at": None, "user_id": "rep-1", "extraction": {"summary": "Wants pricing for 12 seats."}}]
    world["pushed"] = {"hubspot:note:n1"}
    assert [i["id"] for i in get(client, summary="false")["interactions"]] == ["vocify:memo:memo-1"]


def test_no_company_means_no_company_part(client, world):
    world["hubspot"] = acme(companies=[])
    body = get(client, summary="false")
    assert body["company"] is None
    assert body["company_interactions"] == []
    assert world["colleague_reads"] == []


def test_several_companies_and_none_primary_is_not_guessed(client, world):
    world["hubspot"] = acme(companies=[{"toObjectId": "co77", "associationTypes": UNLABELED}, {"toObjectId": "co78", "associationTypes": UNLABELED}])
    body = get(client, summary="false")
    assert body["company"] is None
    assert body["sources"]["hubspot_company"]["company"] == "ambiguous"


def test_the_primary_company_is_the_one_read_when_there_are_several(client, world):
    world["hubspot"] = acme(companies=[{"toObjectId": "co12", "associationTypes": UNLABELED}, {"toObjectId": "co77", "associationTypes": PRIMARY}])
    assert get(client, summary="false")["company"]["id"] == "hubspot:company:co77"


def test_a_company_part_that_cannot_be_read_never_hides_the_contact_s(client, world):
    world["hubspot"] = acme(forbidden={"emails"})
    body = get(client, summary="false")
    assert [i["id"] for i in body["interactions"]] == ["hubspot:note:n1"]
    assert body["sources"]["hubspot_company"]["emails"] == "not_allowed"
    assert body["sources"]["hubspot_company"]["calls"] == "read"


def test_a_big_company_reads_a_bounded_number_of_people(client, world):
    many = [str(5000 + i) for i in range(1200)]
    world["hubspot"] = acme(company_contacts=[CONTACT, *many])
    get(client, summary="false")
    assert len(world["colleague_reads"][0]) <= api.COLLEAGUES_LIMIT


def test_company_lines_cite_only_what_others_said_and_carry_who_and_when(client, world):
    world["llm"] = {
        "lines": [
            {"text": "Pricing for 12 seats", "sources": ["hubspot:note:n1"]},
            {"text": "Toni asked for a demo", "sources": ["hubspot:call:c7"]},  # a company item in the contact's lines
        ],
        "company_lines": [
            {"text": "Asked for a demo; wants reporting first", "sources": ["hubspot:call:c7", "vocify:memo:memo-7"]},
            {"text": "Pricing for 12 seats", "sources": ["hubspot:note:n1"]},  # the contact's own item
            {"text": "Renewal in March", "sources": ["hubspot:note:n9"]},
        ],
    }
    summary = get(client)["summary"]
    assert [line["text"] for line in summary["lines"]] == ["Pricing for 12 seats"]
    assert summary["company_lines"] == [
        {"text": "Asked for a demo; wants reporting first", "sources": ["hubspot:call:c7", "vocify:memo:memo-7"], "type": "call", "occurred_at": "2026-09-12T04:00:00Z", "with": {"name": "Toni García", "title": "CFO"}},
        {"text": "Renewal in March", "sources": ["hubspot:note:n9"], "type": "note", "occurred_at": "2026-08-04T04:00:00Z", "with": None},
    ]
    prompt = str(world["last_prompt"])
    assert "Toni García (CFO)" in prompt and "Acme SL" in prompt
    assert "acme.es" not in prompt and "Logistics" not in prompt


def test_only_the_company_has_history_and_it_is_still_summarized(client, world):
    world["hubspot"] = acme(activity={("companies", "co77"): {"calls": [TONI_CALL]}})
    world["llm"] = {"lines": [], "company_lines": [{"text": "Asked for a demo", "sources": ["hubspot:call:c7"]}]}
    body = get(client)
    assert body["interactions"] == []
    assert [line["text"] for line in body["summary"]["company_lines"]] == ["Asked for a demo"]
