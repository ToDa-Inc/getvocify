"""HUBSPOT_READ_ONLY: a backend that reads a real portal but never writes to it."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-read-only-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-read-only-32")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.handoffs_crm import CrmOwnerWriter  # noqa: E402
from app.services.hubspot import read_only  # noqa: E402
from app.services.hubspot.client import HubSpotClient  # noqa: E402

BASE = "https://api.hubapi.com"


@pytest.mark.parametrize("method,path", [
    ("GET", "/crm/v3/objects/contacts/1"),
    ("POST", "/crm/v3/objects/contacts/search"),
    ("POST", "/crm/v3/objects/tasks/search"),
    ("POST", "/crm/v3/objects/deals/batch/read"),
    ("POST", "/crm/v4/associations/tasks/contacts/batch/read"),
    ("POST", "/oauth/v1/token"),
])
def test_reads_pass(method, path):
    assert read_only.is_write(method, BASE + path) is False


@pytest.mark.parametrize("method,path", [
    ("POST", "/crm/v3/objects/notes"),
    ("POST", "/crm/v3/objects/tasks"),
    ("POST", "/crm/v3/objects/deals/batch/create"),
    ("PATCH", "/crm/v3/objects/deals/7"),
    ("PUT", "/crm/v4/objects/deals/7/associations/default/contacts/1"),
    ("DELETE", "/crm/v3/objects/contacts/1"),
    ("POST", "/crm/extensions/calling/2026-03/settings"),
])
def test_writes_are_writes(method, path):
    assert read_only.is_write(method, BASE + path) is True


def test_other_hosts_are_never_touched():
    assert read_only.is_write("PATCH", "https://api.pipedrive.com/api/v2/deals/1") is False


def _recording():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={"id": "1", "results": []})

    return seen, handler


def test_off_by_default_changes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "HUBSPOT_READ_ONLY", False)
    inner = httpx.MockTransport(lambda r: httpx.Response(200))
    assert read_only.sync_transport(inner) is inner
    assert read_only.sync_transport(None) is None
    assert read_only.async_transport(None) is None


def test_on_a_write_never_leaves_and_a_read_goes_through(monkeypatch):
    monkeypatch.setattr(settings, "HUBSPOT_READ_ONLY", True)
    seen, handler = _recording()
    client = httpx.Client(transport=read_only.sync_transport(httpx.MockTransport(handler)))
    blocked = client.patch(f"{BASE}/crm/v3/objects/deals/7", json={"properties": {"dealstage": "x"}})
    read = client.post(f"{BASE}/crm/v3/objects/contacts/search", json={})
    assert blocked.status_code == read_only.BLOCKED_STATUS
    assert "read-only" in blocked.json()["message"]
    assert read.status_code == 200
    assert seen == ["POST /crm/v3/objects/contacts/search"]


def test_the_handoff_owner_writer_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "HUBSPOT_READ_ONLY", True)
    seen, handler = _recording()
    writer = CrmOwnerWriter(provider="hubspot", access_token="t", transport=httpx.MockTransport(handler))
    assert writer.set_owner(object_type="deal", object_id="7", owner_id="77") is False
    assert seen == []


def test_the_shared_client_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "HUBSPOT_READ_ONLY", True)
    sent: list[str] = []
    real = httpx.AsyncHTTPTransport.handle_async_request

    async def fake(self, request):  # the network, if anything got that far
        sent.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake)
    client = HubSpotClient("token")
    with pytest.raises(Exception) as caught:
        asyncio.run(client.post("/crm/v3/objects/notes", {"properties": {}}))
    assert "read-only" in str(caught.value)
    asyncio.run(client.get("/crm/v3/objects/contacts/1"))
    assert sent == ["GET /crm/v3/objects/contacts/1"]
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", real)
