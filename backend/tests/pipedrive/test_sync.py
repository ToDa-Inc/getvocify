from uuid import uuid4

import pytest

from app.models.approval import CallOutcomeAvailability
from app.models.memo import MemoExtraction
from app.services.crm_providers.pipedrive_provider import PipedriveCRMProvider
from app.services.pipedrive.sync import PipedriveSyncService


class _Tracked:
    data: dict = {}
    resource_id = None


class _Updates:
    def __init__(self, previous=()):
        self.previous = list(previous)
        self.tracked = []

    async def create_update(self, **k):
        return "u1"

    async def get_memo_updates(self, memo_id):
        return self.previous

    def track(self, **k):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def tracking():
            tracked = _Tracked()
            yield tracked
            self.tracked.append((k["action_type"], tracked.resource_id))

        return tracking()


class _FakeClient:
    def __init__(self):
        self.posts = []
        self.patches = []
        self.connection_id = "c1"
        self.api_domain = "https://acme.pipedrive.com"

    async def get(self, path, *, version="v2", params=None):
        if path == "/activityTypes":
            return {"data": [{"key_string": "task", "icon_key": "task"}]}
        if path == "/organizations/search":
            return {"data": {"items": []}}
        if path == "/persons/search":
            return {"data": {"items": []}}
        if path.startswith("/deals/"):
            return {"data": {"id": 1, "title": "Acme"}}
        if path.startswith("/persons/"):
            return {"data": {"id": 20, "name": "Ada"}}
        if path.startswith("/organizations/"):
            return {"data": {"id": 10, "name": "Acme"}}
        return {"data": []}

    async def post(self, path, json_body=None, *, version="v2"):
        self.posts.append((path, json_body, version))
        if path == "/organizations":
            return {"data": {"id": 10, "name": json_body["name"]}}
        if path == "/persons":
            return {"data": {"id": 20, "name": json_body["name"]}}
        if path == "/deals":
            return {"data": {"id": 30, "title": json_body.get("title")}}
        if path == "/notes":
            return {"data": {"id": 40}}
        if path == "/activities":
            return {"data": {"id": 50}}
        return {"data": {"id": 99}}

    async def patch(self, path, json_body, *, version="v2"):
        self.patches.append((path, json_body))
        return {"data": {"id": 30}}


def _svc(client=None, previous=()):
    c = client or _FakeClient()
    return PipedriveSyncService(c, None, _Updates(previous)), c


@pytest.mark.asyncio
async def test_skip_deal_writes_person_and_note_not_deal():
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", companyName="Acme", summary="Hi"),
        skip_deal=True,
        auto_create_contacts=True,
        auto_create_companies=True,
        create_note=True,
        transcript="hello",
    )
    assert result.success is True
    assert result.deal_id is None
    assert result.deal_url is None
    assert result.contact_url == "https://acme.pipedrive.com/person/20"
    paths = [p[0] for p in client.posts]
    assert "/deals" not in paths
    assert "/persons" in paths
    assert "/notes" in paths


@pytest.mark.asyncio
async def test_existing_person_and_org_patch_allowlisted_custom_fields():
    person_field = "5f65fa0c38e46e47a59a4721d5b51f21d89fb679"
    org_field = "ad74fad4499ad8e6347dc8cb6b86cd0b6998cab6"
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(
            contactName="Ada",
            companyName="Acme",
            summary="Hi",
            raw_extraction={
                "contact_properties": {person_field: "director"},
                "company_properties": {org_field: "1339"},
            },
        ),
        skip_deal=True,
        contact_id="20",
        company_id="10",
        allowed_contact_fields=["name", "emails", "phones", person_field],
        allowed_company_fields=["name", org_field],
        create_note=False,
    )
    assert result.success is True
    assert "/deals" not in [p[0] for p in client.posts]
    person_patch = next(p for p in client.patches if p[0] == "/persons/20")
    org_patch = next(p for p in client.patches if p[0] == "/organizations/10")
    assert person_patch[1]["custom_fields"][person_field] == "director"
    assert "name" not in person_patch[1]
    assert org_patch[1]["custom_fields"][org_field] == "1339"
    assert "name" not in org_patch[1]


@pytest.mark.asyncio
async def test_new_deal_without_a_stage_is_skipped_not_the_whole_call():
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme"),
        is_new_deal=True,
        auto_create_companies=True,
    )
    assert result.success is True
    assert result.deal_id is None and result.deal_url is None
    assert result.deal_warning
    assert not any(p[0] == "/deals" for p in client.posts)


@pytest.mark.asyncio
async def test_new_deal_creates_with_stage_and_deal_url():
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme", dealAmount=1000, dealCurrency="EUR", summary="Ok"),
        is_new_deal=True,
        default_stage_id="5",
        default_pipeline_id="1",
        auto_create_companies=True,
        create_note=True,
        transcript="t",
    )
    assert result.success is True
    assert result.deal_id == "30"
    assert result.deal_url == "https://acme.pipedrive.com/deal/30"
    deal_post = next(p for p in client.posts if p[0] == "/deals")
    assert deal_post[1]["title"] == "Acme"
    assert deal_post[1]["stage_id"] == 5
    assert deal_post[1]["value"] == 1000


@pytest.mark.asyncio
async def test_call_outcome_unsupported():
    provider = PipedriveCRMProvider(
        None,
        {
            "id": "c1",
            "access_token": "t",
            "metadata": {"api_domain": "https://acme.pipedrive.com"},
        },
    )
    result = await provider.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme"),
        call_outcome="lost",
    )
    assert result.success is False
    assert result.error_code == "CALL_OUTCOME_UNSUPPORTED"
    avail = await provider.get_call_outcome_availability()
    assert avail == CallOutcomeAvailability(converted=False, on_hold=False, lost=False)


@pytest.mark.asyncio
async def test_missing_task_type_warns():
    client = _FakeClient()

    async def no_types(path, *, version="v2", params=None):
        if path == "/activityTypes":
            return {"data": [{"key_string": "call", "icon_key": "call"}]}
        return await _FakeClient.get(client, path, version=version, params=params)

    client.get = no_types
    svc, _ = _svc(client)
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme", nextSteps=["Send proposal"]),
        is_new_deal=True,
        default_stage_id="5",
        auto_create_companies=True,
    )
    assert result.success is True
    assert result.tasks_warning
    assert result.tasks_created_count == 0
    assert not any(p[0] == "/activities" for p in client.posts)


@pytest.mark.asyncio
async def test_create_note_false_skips_note():
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme", summary="Hi"),
        is_new_deal=True,
        default_stage_id="5",
        auto_create_companies=True,
        create_note=False,
        transcript="t",
    )
    assert result.success is True
    assert "/notes" not in [p[0] for p in client.posts]


@pytest.mark.asyncio
async def test_promised_note_missing_fails_sync():
    client = _FakeClient()

    async def no_note(path, json_body=None, *, version="v2"):
        if path == "/notes":
            return {"data": {}}
        return await _FakeClient.post(client, path, json_body=json_body, version=version)

    client.post = no_note
    svc, _ = _svc(client)
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme", summary="Hi"),
        is_new_deal=True,
        default_stage_id="5",
        auto_create_companies=True,
        create_note=True,
        transcript="t",
    )
    assert result.success is False
    assert result.error_code == "PIPEDRIVE_NOTE_FAILED"


@pytest.mark.asyncio
async def test_note_is_tracked_and_not_written_twice_on_a_retry():
    svc, client = _svc()
    kwargs = dict(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="Hi"),
        skip_deal=True,
        contact_id="20",
        transcript="hello",
    )
    assert (await svc.sync_memo(**kwargs)).success is True
    assert [p[0] for p in client.posts].count("/notes") == 1
    assert svc.crm_updates.tracked == [("create_note", "40")]

    retry, retry_client = _svc(previous=[{"action_type": "create_note", "status": "success"}])
    assert (await retry.sync_memo(**kwargs)).success is True
    assert "/notes" not in [p[0] for p in retry_client.posts]


@pytest.mark.asyncio
async def test_a_failed_note_row_does_not_block_the_retry():
    svc, client = _svc(previous=[{"action_type": "create_note", "status": "failed"}])
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="Hi"),
        skip_deal=True,
        contact_id="20",
        transcript="hello",
    )
    assert result.success is True and "/notes" in [p[0] for p in client.posts]


@pytest.mark.asyncio
async def test_new_deal_links_its_person_by_person_id_even_when_person_id_is_not_an_allowed_field():
    # Live v2 API (2026-11-09): POST /deals takes person_id and refuses "participants".
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", companyName="Acme", summary="Hi"),
        is_new_deal=True,
        default_stage_id="5",
        contact_id="20",
        allowed_fields=["title", "value", "stage_id"],
        create_note=False,
    )
    assert result.success is True
    body = next(p[1] for p in client.posts if p[0] == "/deals")
    assert body["person_id"] == 20
    assert "participants" not in body


@pytest.mark.asyncio
async def test_existing_deal_without_a_person_gets_one():
    # Live v2 API (2026-11-09): no /deals/{id}/participants route; PATCH person_id sets it.
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="Hi", dealAmount=10),
        deal_id="1",
        contact_id="20",
        allowed_fields=["title", "value", "person_id"],
        create_note=False,
    )
    assert result.success is True
    assert any(p[0] == "/deals/1" and p[1] == {"person_id": 20} for p in client.patches)
    assert not any(p[0].endswith("/participants") for p in client.posts)


@pytest.mark.asyncio
async def test_existing_deal_that_has_a_person_is_left_alone():
    client = _FakeClient()
    base_get = client.get

    async def get(path, *, version="v2", params=None):
        if path == "/deals/1":
            return {"data": {"id": 1, "title": "Acme", "person_id": 7}}
        return await base_get(path, version=version, params=params)

    client.get = get
    svc, _ = _svc(client)
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="Hi", dealAmount=10),
        deal_id="1",
        contact_id="20",
        allowed_fields=["value", "person_id"],
        create_note=False,
    )
    assert result.success is True
    assert not any(p[0].endswith("/participants") for p in client.posts)
    assert not any(p[1].get("person_id") for p in client.patches)


@pytest.mark.asyncio
async def test_no_default_stage_still_writes_the_note_and_says_no_deal_was_made():
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="Wants a follow-up"),
        is_new_deal=True,
        contact_id="20",
        allowed_fields=["title", "value"],
        create_note=True,
    )
    assert result.success is True
    assert result.deal_id is None
    assert "No deal was created" in (result.deal_warning or "")
    assert not any(p[0] == "/deals" for p in client.posts)
    assert any(p[0] == "/notes" and p[1].get("person_id") == 20 for p in client.posts)


@pytest.mark.asyncio
async def test_a_call_is_also_logged_as_a_done_call_activity_with_the_summary():
    svc, client = _svc()

    async def get(path, *, version="v2", params=None):
        if path == "/activityTypes":
            return {"data": [{"key_string": "call", "icon_key": "call"}, {"key_string": "task", "icon_key": "task"}]}
        return await base_get(path, version=version, params=params)

    base_get = client.get
    client.get = get
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="## Contexto de la llamada\n- Pide un follow-up el lunes."),
        deal_id="1",
        contact_id="20",
        allowed_fields=["value"],
        create_note=True,
        transcript="SPEAKER: S2\nSí, llámame el lunes por la mañana.",
        conversation={"kind": "call", "occurred_at": "2026-11-06T19:12:14+00:00", "duration_seconds": 46, "activity_id": None},
    )
    assert result.success is True
    body = next(p[1] for p in client.posts if p[0] == "/activities" and p[1].get("type") == "call")
    assert body["done"] is True and body["subject"] == "Llamada con Ada"
    assert body["participants"] == [{"person_id": 20, "primary": True}] and body["deal_id"] == 1
    assert body["due_date"] == "2026-11-06" and body["due_time"] == "19:12" and body["duration"] == "00:01"
    assert "Contexto de la llamada" in body["note"]


@pytest.mark.asyncio
async def test_a_call_vocify_dialed_puts_the_summary_on_its_own_call_activity():
    svc, client = _svc()
    await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="- Pide un follow-up."),
        deal_id="1",
        contact_id="20",
        allowed_fields=["value"],
        create_note=True,
        conversation={"kind": "call", "occurred_at": None, "duration_seconds": 0, "activity_id": "901"},
    )
    assert any(p[0] == "/activities/901" and "follow-up" in p[1]["note"] for p in client.patches)
    assert not any(p[0] == "/activities" and p[1].get("done") for p in client.posts)


@pytest.mark.asyncio
async def test_a_note_is_written_as_its_member_and_falls_back_when_pipedrive_refuses():
    from app.services.pipedrive.exceptions import PipedriveError
    from app.services.pipedrive.notes import PipedriveNoteService

    class _Client:
        def __init__(self, refuse):
            self.refuse, self.bodies = refuse, []

        async def post(self, path, json_body=None, version="v2"):
            self.bodies.append(json_body)
            if self.refuse and "user_id" in json_body:
                raise PipedriveError("forbidden", status_code=403)
            return {"data": {"id": 9}}

    ok = _Client(refuse=False)
    assert await PipedriveNoteService(ok).create("<p>x</p>", deal_id="1", author_id="15666515") == "9"
    assert ok.bodies == [{"content": "<p>x</p>", "deal_id": 1, "user_id": 15666515}]

    refused = _Client(refuse=True)
    assert await PipedriveNoteService(refused).create("<p>x</p>", deal_id="1", author_id="15666515") == "9"
    assert refused.bodies[-1] == {"content": "<p>x</p>", "deal_id": 1}
