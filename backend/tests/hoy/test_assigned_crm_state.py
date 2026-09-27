"""F16: assigned contacts carry crm_state from lead status or latest deal."""

from __future__ import annotations

import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-assigned-crm-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-assigned-crm-32")

import httpx
from httpx import MockTransport, Request, Response

from app.services.hoy.assigned import collect_assigned, connection_assigned_fetch
from app.services.hoy.crm_state import QueueStates

OBSERVED = "2026-09-22T10:00:00Z"
BOOKED = QueueStates(source="deal_stage", booked=("appointmentscheduled",), ended=("closedlost",))
LEAD = QueueStates(source="lead_status", booked=("CONNECTED",), ended=())


def test_hubspot_lead_mode_sets_crm_state_from_hs_lead_status():
    def handler(request: Request) -> Response:
        if request.url.path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        body = json.loads(request.content)
        assert "hs_lead_status" in body["properties"]
        return Response(200, json={"results": [
            {"id": "42", "properties": {
                "hubspot_owner_id": "101",
                "hs_lead_status": "CONNECTED",
                "firstname": "Marta",
            }},
        ]})

    fetch = connection_assigned_fetch(
        {"provider": "hubspot", "access_token": "tok"},
        client=httpx.Client(transport=MockTransport(handler)),
    )
    page = collect_assigned(
        "hubspot", fetch, connection_id="crm-A", observed_at=OBSERVED,
        member_emails={"ana@vocify.test"}, queue_states=LEAD,
    )
    assert page["items"][0]["crm_state"] == "CONNECTED"


def test_hubspot_deal_mode_picks_latest_associated_deal():
    def handler(request: Request) -> Response:
        path = request.url.path
        if path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        if path == "/crm/v3/objects/contacts/search":
            return Response(200, json={"results": [
                {"id": "42", "properties": {"hubspot_owner_id": "101", "firstname": "Marta"}},
            ]})
        if path == "/crm/v3/objects/deals/search":
            return Response(200, json={"results": [
                {"id": "d1", "properties": {
                    "dealstage": "qualifiedtobuy",
                    "hs_lastmodifieddate": "2026-09-20T10:00:00Z",
                    "hubspot_owner_id": "101",
                }},
                {"id": "d2", "properties": {
                    "dealstage": "appointmentscheduled",
                    "hs_lastmodifieddate": "2026-09-21T10:00:00Z",
                    "hubspot_owner_id": "101",
                }},
            ]})
        if path == "/crm/v4/associations/deals/contacts/batch/read":
            return Response(200, json={"results": [
                {"from": {"id": "d1"}, "to": [{"toObjectId": "42"}]},
                {"from": {"id": "d2"}, "to": [{"toObjectId": "42"}]},
            ]})
        return Response(404, json={})

    fetch = connection_assigned_fetch(
        {"provider": "hubspot", "access_token": "tok"},
        client=httpx.Client(transport=MockTransport(handler)),
    )
    page = collect_assigned(
        "hubspot", fetch, connection_id="crm-A", observed_at=OBSERVED,
        member_emails={"ana@vocify.test"}, queue_states=BOOKED,
    )
    assert page["items"][0]["crm_state"] == "appointmentscheduled"


def test_deal_state_read_failure_omits_crm_state_and_is_partial():
    def handler(request: Request) -> Response:
        path = request.url.path
        if path == "/crm/v3/owners":
            return Response(200, json={"results": [{"id": "101", "email": "ana@vocify.test"}]})
        if path == "/crm/v3/objects/contacts/search":
            return Response(200, json={"results": [
                {"id": "42", "properties": {"hubspot_owner_id": "101"}},
            ]})
        if path == "/crm/v3/objects/deals/search":
            return Response(403, json={"message": "denied"})
        return Response(404, json={})

    fetch = connection_assigned_fetch(
        {"provider": "hubspot", "access_token": "tok"},
        client=httpx.Client(transport=MockTransport(handler)),
    )
    page = collect_assigned(
        "hubspot", fetch, connection_id="crm-A", observed_at=OBSERVED,
        member_emails={"ana@vocify.test"}, queue_states=BOOKED,
    )
    assert "crm_state" not in page["items"][0]
    assert page["coverage"] == "partial"


def test_pipedrive_won_deal_sets_status_won():
    def handler(request: Request) -> Response:
        path = request.url.path
        if path == "/api/v1/users":
            return Response(200, json={"data": [{"id": 9, "email": "ana@vocify.test"}]})
        if path == "/api/v2/persons":
            return Response(200, json={"data": [
                {"id": 7, "name": "Marta", "owner_id": 9, "done_activities_count": 1},
            ]})
        if path == "/api/v2/deals":
            return Response(200, json={"data": [
                {"id": 88, "person_id": 7, "stage_id": 3, "status": "won", "update_time": "2026-09-21T10:00:00Z"},
            ]})
        return Response(404, json={})

    fetch = connection_assigned_fetch(
        {
            "provider": "pipedrive",
            "access_token": "tok",
            "metadata": {"api_domain": "https://acme.pipedrive.com"},
        },
        client=httpx.Client(transport=MockTransport(handler)),
    )
    page = collect_assigned(
        "pipedrive", fetch, connection_id="crm-B", observed_at=OBSERVED,
        member_emails={"ana@vocify.test"}, queue_states=BOOKED,
    )
    assert page["items"][0]["crm_state"] == "status:won"
