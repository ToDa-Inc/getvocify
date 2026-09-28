"""T3 D7 CRM adapter: CrmOwnerWriter against real HubSpot/Pipedrive request shapes
(httpx.MockTransport, same style as meetings/test_crm_writer.py)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-handoffs-32c")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-handoffs-32c")

import json

import httpx

from app.services.handoffs_crm import CrmOwnerWriter, owner_writer_from_connection


def _hubspot_transport(patches: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/crm/v3/owners":
            return httpx.Response(
                200,
                json={"results": [{"id": "111", "email": "ae@vocify.test"}]},
            )
        if request.method == "PATCH" and "/crm/v3/objects/deals/" in request.url.path:
            patches.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "deal-1"})
        if request.method == "PATCH" and "/crm/v3/objects/contacts/" in request.url.path:
            patches.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "contact-1"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_hubspot_writer_finds_the_owner_and_patches_the_deal():
    patches: list = []
    writer = CrmOwnerWriter(provider="hubspot", access_token="pat-test", api_domain=None, transport=_hubspot_transport(patches))
    owner_id = writer.find_owner_id("ae@vocify.test")
    assert owner_id == "111"
    assert writer.set_owner(object_type="deal", object_id="deal-1", owner_id=owner_id) is True
    assert patches == [{"properties": {"hubspot_owner_id": "111"}}]


def test_hubspot_writer_patches_the_contact_without_a_deal():
    patches: list = []
    writer = CrmOwnerWriter(provider="hubspot", access_token="pat-test", api_domain=None, transport=_hubspot_transport(patches))
    assert writer.set_owner(object_type="contact", object_id="contact-1", owner_id="111") is True
    assert patches == [{"properties": {"hubspot_owner_id": "111"}}]


def test_hubspot_writer_owner_not_found():
    writer = CrmOwnerWriter(provider="hubspot", access_token="pat-test", api_domain=None, transport=_hubspot_transport([]))
    assert writer.find_owner_id("nope@vocify.test") is None


def _pipedrive_transport(patches: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"data": [{"id": 222, "email": "ae@vocify.test"}]})
        if request.method == "PATCH" and "/api/v2/deals/" in request.url.path:
            patches.append(json.loads(request.content))
            return httpx.Response(200, json={"data": {"id": 1}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_pipedrive_writer_finds_the_owner_and_patches_the_deal():
    patches: list = []
    writer = CrmOwnerWriter(
        provider="pipedrive", access_token="tok", api_domain="https://acme.pipedrive.com",
        transport=_pipedrive_transport(patches),
    )
    owner_id = writer.find_owner_id("ae@vocify.test")
    assert owner_id == "222"
    assert writer.set_owner(object_type="deal", object_id="1", owner_id=owner_id) is True
    assert patches == [{"owner_id": 222}]


def test_writer_set_owner_returns_false_on_http_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    writer = CrmOwnerWriter(provider="hubspot", access_token="pat", api_domain=None, transport=httpx.MockTransport(handler))
    assert writer.set_owner(object_type="deal", object_id="d1", owner_id="1") is False


def test_owner_writer_from_connection_builds_a_working_writer():
    writer = owner_writer_from_connection({"provider": "hubspot", "access_token": "pat"})
    assert isinstance(writer, CrmOwnerWriter)
