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


MAPPING = {"pipeline_id": "default", "stage_id": "meeting"}
HS_STAGES = {
    "id": "default",
    "stages": [
        {"id": "new", "displayOrder": 0, "metadata": {"isClosed": "false"}},
        {"id": "meeting", "displayOrder": 1, "metadata": {"isClosed": "false"}},
        {"id": "proposal", "displayOrder": 2, "metadata": {"isClosed": "false"}},
        {"id": "won", "displayOrder": 3, "metadata": {"isClosed": "true"}},
    ],
}


def _hubspot_deal_transport(deal: dict, patches: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/tasks"):
            return httpx.Response(201, json={"id": "hs-task-99"})
        if request.method == "GET" and path == "/crm/v3/objects/deals/77":
            return httpx.Response(200, json={"id": "77", "properties": deal})
        if request.method == "GET" and path == "/crm/v3/pipelines/deals/default":
            return httpx.Response(200, json=HS_STAGES)
        if request.method == "PATCH" and path == "/crm/v3/objects/deals/77":
            patches.append(request)
            return httpx.Response(200, json={"id": "77"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _hs_writer(deal: dict, patches: list) -> CrmMeetingActivityWriter:
    return CrmMeetingActivityWriter(
        provider="hubspot",
        access_token="pat-test",
        transport=_hubspot_deal_transport(deal, patches),
        deal_id="77",
    )


def test_an_accepted_meeting_moves_an_earlier_hubspot_deal_to_the_mapped_stage():
    patches: list = []
    result = register_meeting(
        proposal=PROPOSAL,
        decision="accept",
        operation_key="op-stage",
        writer=_hs_writer({"pipeline": "default", "dealstage": "new"}, patches),
        stage_mapping=MAPPING,
        existing=None,
    )
    assert result["stage_changed"] is True
    assert result["closes_deal"] is False
    assert len(patches) == 1
    assert b'"dealstage":"meeting"' in patches[0].content.replace(b" ", b"")


def test_a_hubspot_deal_never_moves_back_out_of_closed_or_across_pipelines():
    for deal in (
        {"pipeline": "default", "dealstage": "proposal"},
        {"pipeline": "default", "dealstage": "meeting"},
        {"pipeline": "default", "dealstage": "won"},
        {"pipeline": "other", "dealstage": "new"},
    ):
        patches: list = []
        result = register_meeting(
            proposal=PROPOSAL,
            decision="accept",
            operation_key="op-stage",
            writer=_hs_writer(deal, patches),
            stage_mapping=MAPPING,
            existing=None,
        )
        assert result["crm_status"] == "succeeded"
        assert result["stage_changed"] is False, deal
        assert patches == []


def test_a_booked_meeting_never_closes_a_hubspot_deal():
    patches: list = []
    writer = _hs_writer({"pipeline": "default", "dealstage": "new"}, patches)
    assert writer.change_stage({"pipeline_id": "default", "stage_id": "won"}) is False
    assert patches == []


def test_without_a_deal_or_mapping_nothing_moves():
    patches: list = []
    writer = CrmMeetingActivityWriter(
        provider="hubspot",
        access_token="pat-test",
        transport=_hubspot_deal_transport({"pipeline": "default", "dealstage": "new"}, patches),
    )
    assert writer.change_stage(MAPPING) is False
    assert _hs_writer({"pipeline": "default", "dealstage": "new"}, patches).change_stage(None) is False
    assert patches == []


def _pipedrive_transport(deal: dict, patches: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/api/v1/activityTypes":
            return httpx.Response(200, json={"data": [{"key_string": "meeting", "icon_key": "meeting"}]})
        if request.method == "POST" and path == "/api/v1/activities":
            return httpx.Response(201, json={"data": {"id": 501}})
        if request.method == "GET" and path == "/api/v2/deals/88":
            return httpx.Response(200, json={"data": deal})
        if request.method == "GET" and path == "/api/v2/stages":
            assert request.url.params.get("pipeline_id") == "3"
            return httpx.Response(200, json={"data": [
                {"id": 10, "order_nr": 1},
                {"id": 11, "order_nr": 2},
                {"id": 12, "order_nr": 3},
            ]})
        if request.method == "PATCH" and path == "/api/v2/deals/88":
            patches.append(request)
            return httpx.Response(200, json={"data": {"id": 88}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _pd_writer(deal: dict, patches: list) -> CrmMeetingActivityWriter:
    return CrmMeetingActivityWriter(
        provider="pipedrive",
        access_token="tok",
        api_domain="https://acme.pipedrive.com",
        transport=_pipedrive_transport(deal, patches),
        deal_id="88",
    )


def test_an_accepted_meeting_moves_an_open_earlier_pipedrive_deal():
    patches: list = []
    result = register_meeting(
        proposal=PROPOSAL,
        decision="accept",
        operation_key="op-pd",
        writer=_pd_writer({"id": 88, "pipeline_id": 3, "stage_id": 10, "status": "open"}, patches),
        stage_mapping={"pipeline_id": "3", "stage_id": "11"},
        existing=None,
    )
    assert result["remote_id"] == "501"
    assert result["stage_changed"] is True
    assert b'"stage_id":11' in patches[0].content.replace(b" ", b"")


def test_a_won_or_later_pipedrive_deal_keeps_its_stage():
    for deal in (
        {"id": 88, "pipeline_id": 3, "stage_id": 10, "status": "won"},
        {"id": 88, "pipeline_id": 3, "stage_id": 12, "status": "open"},
        {"id": 88, "pipeline_id": 4, "stage_id": 10, "status": "open"},
    ):
        patches: list = []
        moved = _pd_writer(deal, patches).change_stage({"pipeline_id": "3", "stage_id": "11"})
        assert moved is False, deal
        assert patches == []


def test_a_stage_error_keeps_the_activity_as_saved():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"id": "hs-task-99"})
        return httpx.Response(500)

    writer = CrmMeetingActivityWriter(
        provider="hubspot", access_token="pat", transport=httpx.MockTransport(handler), deal_id="77",
    )
    result = register_meeting(
        proposal=PROPOSAL, decision="accept", operation_key="op-err", writer=writer,
        stage_mapping=MAPPING, existing=None,
    )
    assert result["crm_status"] == "succeeded"
    assert result["stage_changed"] is False


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
