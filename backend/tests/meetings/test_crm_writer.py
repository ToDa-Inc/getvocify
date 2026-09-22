"""F14 CRM adapter: one accept posts once; timeout is uncertain; reconcile may be empty."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meetings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meetings-32")

import httpx
from app.services.meetings.crm_writer import CrmMeetingActivityWriter, writer_from_connection
from app.services.meetings.writes import register_meeting

PROPOSAL = {
    "proposal_id": "meet-1",
    "agreement": "agreed",
    "starts_at": "2026-09-29T15:00:00+00:00",
    "timezone": "Europe/Madrid",
    "precision": "exact",
    "needs_review": False,
}


def _hubspot_transport(posts: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/tasks"):
            posts.append(request)
            return httpx.Response(201, json={"id": "hs-task-99"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_one_accept_creates_one_hubspot_activity_and_repeat_does_not_post():
    posts: list = []
    writer = CrmMeetingActivityWriter(
        provider="hubspot",
        access_token="pat-test",
        transport=_hubspot_transport(posts),
        timeout=5.0,
    )
    first = register_meeting(
        proposal=PROPOSAL,
        decision="accept",
        operation_key="op-hs-1",
        writer=writer,
        stage_mapping=None,
        existing=None,
    )
    second = register_meeting(
        proposal=PROPOSAL,
        decision="accept",
        operation_key="op-hs-1",
        writer=writer,
        stage_mapping=None,
        existing=first,
    )
    assert len(posts) == 1
    assert first["remote_id"] == "hs-task-99"
    assert second["replayed"] is True
    assert second["remote_id"] == "hs-task-99"


def test_timeout_is_uncertain_and_reconcile_may_be_none():
    posts: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(request)
            raise httpx.ReadTimeout("slow crm")
        return httpx.Response(404)

    writer = CrmMeetingActivityWriter(
        provider="hubspot",
        access_token="pat-test",
        transport=httpx.MockTransport(handler),
        timeout=0.01,
    )
    uncertain = register_meeting(
        proposal=PROPOSAL,
        decision="accept",
        operation_key="op-timeout",
        writer=writer,
        stage_mapping=None,
        existing=None,
    )
    assert uncertain["crm_status"] == "uncertain"
    assert uncertain["remote_id"] is None
    assert writer.reconcile("op-timeout") is None
    assert len(posts) == 1


def test_writer_from_connection_requires_token():
    assert writer_from_connection({"provider": "hubspot"}) is None
    built = writer_from_connection(
        {"provider": "hubspot", "access_token": "tok"},
        transport=_hubspot_transport([]),
    )
    assert built is not None
    assert built.create("op-2", PROPOSAL) == "hs-task-99"


def test_forbidden_does_not_create_second_activity():
    posts: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(403, json={"message": "missing scope"})

    writer = CrmMeetingActivityWriter(
        provider="hubspot",
        access_token="pat-test",
        transport=httpx.MockTransport(handler),
    )
    result = register_meeting(
        proposal=PROPOSAL,
        decision="accept",
        operation_key="op-forbidden",
        writer=writer,
        stage_mapping=None,
        existing=None,
    )
    assert result["crm_status"] == "failed"
    assert len(posts) == 1
