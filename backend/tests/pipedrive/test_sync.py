from uuid import uuid4

import pytest

from app.models.approval import CallOutcomeAvailability
from app.models.memo import MemoExtraction
from app.services.crm_providers.pipedrive_provider import PipedriveCRMProvider
from app.services.pipedrive.sync import PipedriveSyncService


class _Updates:
    async def create_update(self, **k):
        return "u1"


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


def _svc(client=None):
    c = client or _FakeClient()
    return PipedriveSyncService(c, None, _Updates()), c


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
async def test_new_deal_requires_stage():
    svc, client = _svc()
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme"),
        is_new_deal=True,
        auto_create_companies=True,
    )
    assert result.success is False
    assert result.error_code == "PIPEDRIVE_STAGE_REQUIRED"
    assert result.deal_url is None
    assert client.posts == []


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
