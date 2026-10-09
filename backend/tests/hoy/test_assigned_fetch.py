"""Assigned contacts: connection token drives HubSpot/Pipedrive HTTP."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-assigned")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-assigned")

import httpx
from httpx import MockTransport, Request, Response

from app.services.hoy.assigned import collect_assigned, connection_assigned_fetch


def test_hubspot_search_uses_bearer_and_403_yields_forbidden_with_no_items():
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: Request) -> Response:
        seen.append((request.method, str(request.url), request.headers.get("Authorization")))
        return Response(403, json={"message": "denied"})

    client = httpx.Client(transport=MockTransport(handler))
    fetch = connection_assigned_fetch(
        {"provider": "hubspot", "access_token": "pat-test"},
        client=client,
    )
    result = collect_assigned(
        "hubspot",
        fetch,
        connection_id="crm-A",
        observed_at="2026-09-22T09:00:00Z",
        member_emails={"ana@vocify.test"},
    )
    assert result["coverage"] == "forbidden"
    assert result["items"] == []
    assert seen == [
        (
            "GET",
            "https://api.hubapi.com/crm/v3/owners?limit=100",
            "Bearer pat-test",
        ),
    ]


def test_missing_token_does_not_call_the_network():
    def handler(_request: Request) -> Response:
        raise AssertionError("network must not run without token")

    client = httpx.Client(transport=MockTransport(handler))
    fetch = connection_assigned_fetch({"provider": "hubspot", "access_token": ""}, client=client)
    payload = fetch({"method": "POST", "path": "/crm/v3/objects/contacts/search", "json": {}})
    assert payload == {"error_kind": "unavailable"}


def test_default_client_closed_after_one_request():
    close_calls = 0
    transport = MockTransport(lambda _request: Response(200, json={"results": []}))
    real_client = httpx.Client

    def tracking_client(*args, **kwargs):
        nonlocal close_calls
        kwargs.setdefault("transport", transport)
        c = real_client(*args, **kwargs)
        original_close = c.close

        def close() -> None:
            nonlocal close_calls
            close_calls += 1
            original_close()

        c.close = close  # type: ignore[method-assign]
        return c

    fetch = connection_assigned_fetch({"provider": "hubspot", "access_token": "pat-test"})
    with patch("app.services.hoy.assigned.httpx.Client", tracking_client):
        payload = fetch({"method": "POST", "path": "/crm/v3/objects/contacts/search", "json": {}})
    assert payload == {"results": []}
    assert close_calls == 1
