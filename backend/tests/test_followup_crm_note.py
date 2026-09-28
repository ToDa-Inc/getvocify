"""D9: log the Vocify-sent follow-up in the CRM, reusing the HubSpot/Pipedrive note helpers."""

import asyncio
import json
import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

import httpx
import respx

from app.services.followup_crm_note import log_followup_note

HUBSPOT_CONNECTION = {"id": "conn-1", "company_id": "co-1", "provider": "hubspot", "status": "connected", "access_token": "tok-hs"}
PIPEDRIVE_CONNECTION = {
    "id": "conn-2", "company_id": "co-1", "provider": "pipedrive", "status": "connected", "access_token": "tok-pd",
    "metadata": {"api_domain": "https://acme.pipedrive.com"},
}


class Query:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        matched = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]
        return SimpleNamespace(data=matched)


class FakeSupabase:
    def __init__(self, connections):
        self.connections = connections

    def table(self, name):
        assert name == "crm_connections", name
        return Query(self.connections)


def memo(**overrides):
    return {"id": "m1", "company_id": "co-1", "hubspot_deal_id": "42", "hubspot_contact_id": "7", **overrides}


def test_no_crm_connection_is_skipped_not_failed():
    result = asyncio.run(log_followup_note(FakeSupabase([]), memo(), "Cuerpo"))
    assert result == {"status": "skipped", "reason": "no_crm"}


def test_no_deal_or_contact_is_skipped():
    m = memo(hubspot_deal_id=None, hubspot_contact_id=None)
    result = asyncio.run(log_followup_note(FakeSupabase([HUBSPOT_CONNECTION]), m, "Cuerpo"))
    assert result == {"status": "skipped", "reason": "no_target"}


def test_no_company_id_is_skipped():
    result = asyncio.run(log_followup_note(FakeSupabase([HUBSPOT_CONNECTION]), {"id": "m1"}, "Cuerpo"))
    assert result == {"status": "skipped", "reason": "no_company"}


@respx.mock
def test_hubspot_note_is_created_with_deal_and_contact_associations():
    route = respx.post("https://api.hubapi.com/crm/v3/objects/notes").mock(
        return_value=httpx.Response(201, json={"id": "note-1"})
    )
    result = asyncio.run(log_followup_note(FakeSupabase([HUBSPOT_CONNECTION]), memo(), "Hola, te confirmo el jueves."))
    assert result == {"status": "done", "provider": "hubspot", "note_id": "note-1"}
    sent = json.loads(route.calls.last.request.content)
    assert sent["properties"]["hs_note_body"].endswith("Hola, te confirmo el jueves.")
    targets = {a["to"]["id"] for a in sent["associations"]}
    assert targets == {"42", "7"}


@respx.mock
def test_a_hubspot_error_is_reported_failed_not_raised():
    respx.post("https://api.hubapi.com/crm/v3/objects/notes").mock(return_value=httpx.Response(500, json={}))
    result = asyncio.run(log_followup_note(FakeSupabase([HUBSPOT_CONNECTION]), memo(), "Cuerpo"))
    assert result == {"status": "failed", "provider": "hubspot", "reason": "error"}


@respx.mock
def test_pipedrive_note_is_created_on_deal_and_person():
    route = respx.post("https://acme.pipedrive.com/api/v1/notes").mock(
        return_value=httpx.Response(201, json={"data": {"id": 55}})
    )
    result = asyncio.run(log_followup_note(FakeSupabase([PIPEDRIVE_CONNECTION]), memo(), "Cuerpo del seguimiento"))
    assert result == {"status": "done", "provider": "pipedrive", "note_id": "55"}
    sent = json.loads(route.calls.last.request.content)
    assert (sent["deal_id"], sent["person_id"]) == (42, 7)
    assert "Cuerpo del seguimiento" in sent["content"]


@respx.mock
def test_pipedrive_note_content_is_html_escaped():
    route = respx.post("https://acme.pipedrive.com/api/v1/notes").mock(
        return_value=httpx.Response(201, json={"data": {"id": 56}})
    )
    body = 'Precio < 100€ & "condiciones especiales" <script>alert(1)</script>'
    asyncio.run(log_followup_note(FakeSupabase([PIPEDRIVE_CONNECTION]), memo(), body))
    sent = json.loads(route.calls.last.request.content)
    assert "<script>" not in sent["content"]
    assert "&lt;script&gt;" in sent["content"]
    assert "&amp;" in sent["content"]
    assert "&quot;condiciones especiales&quot;" in sent["content"]


def test_an_unsupported_provider_is_skipped():
    connection = {**HUBSPOT_CONNECTION, "provider": "salesforce"}
    result = asyncio.run(log_followup_note(FakeSupabase([connection]), memo(), "Cuerpo"))
    assert result == {"status": "skipped", "reason": "unsupported_provider"}
