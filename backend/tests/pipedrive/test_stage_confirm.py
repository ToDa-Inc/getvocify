"""Pipedrive review: with DEAL_STAGE_CONFIRM_ENABLED the stage_id row is always offered and the rep decides."""

from uuid import uuid4

import pytest

from app.models.memo import MemoExtraction
from app.services.pipedrive.preview import PipedrivePreviewService
from app.services.pipedrive.schema import PipedriveSchemaService
from app.services.pipedrive.search import PipedriveSearchService
from app.services.pipedrive.sync import PipedriveSyncService

STAGES = [
    {"id": 11, "name": "Lead", "pipeline_id": 1},
    {"id": 12, "name": "Reunión agendada", "pipeline_id": 1},
    {"id": 13, "name": "Propuesta", "pipeline_id": 1},
    {"id": 21, "name": "Partner lead", "pipeline_id": 2},
    {"id": 22, "name": "Partner meeting", "pipeline_id": 2},
]
DEALS = {
    "7": {"id": 7, "title": "Acme", "stage_id": 11, "pipeline_id": 1, "value": 100},
    "8": {"id": 8, "title": "Partner", "stage_id": 21, "pipeline_id": 2},
}
MEETING_P1 = {"pipeline_id": "1", "stage_id": "12"}
MEETING_P2 = {"pipeline_id": "2", "stage_id": "22"}


class _Updates:
    async def create_update(self, **_k):
        return "u1"


class _Client:
    connection_id = "c1"
    api_domain = "https://acme.pipedrive.com"

    def __init__(self):
        self.posts: list = []
        self.patches: list = []

    async def get(self, path, *, version="v2", params=None):
        if path == "/stages":
            pid = (params or {}).get("pipeline_id")
            return {"data": [s for s in STAGES if pid is None or str(s["pipeline_id"]) == str(pid)]}
        if path == "/dealFields":
            return {"data": [
                {"field_code": "value", "field_name": "Value", "field_type": "monetary"},
                {"field_code": "stage_id", "field_name": "Stage", "field_type": "stage"},
            ]}
        if path.startswith("/deals/"):
            return {"data": dict(DEALS[path.rsplit("/", 1)[1]])}
        if path == "/activityTypes":
            return {"data": [{"key_string": "task", "icon_key": "task"}]}
        return {"data": []}

    async def post(self, path, json_body=None, *, version="v2"):
        self.posts.append((path, json_body))
        return {"data": {"id": 30, "title": (json_body or {}).get("title")}}

    async def patch(self, path, json_body, *, version="v2"):
        self.patches.append((path, json_body))
        return {"data": {"id": 7}}


def _preview_svc():
    client = _Client()
    return PipedrivePreviewService(PipedriveSearchService(client), PipedriveSchemaService(client))


async def _preview(extraction, *, deal_id=None, skip_deal=False, allowed=("value",), **kw):
    return await _preview_svc().build_preview(
        memo_id=uuid4(),
        transcript="hola",
        extraction=extraction,
        matched_deals=[],
        selected_deal_id=deal_id,
        allowed_fields=list(allowed),
        default_pipeline_id="1",
        default_stage_id="11",
        skip_deal=skip_deal,
        **kw,
    )


def _stage_row(preview):
    rows = [u for u in preview.proposed_updates if u.field_name == "stage_id"]
    assert len(rows) <= 1
    return rows[0] if rows else None


@pytest.mark.asyncio
async def test_flag_off_existing_deal_without_editable_stage_has_no_stage_row():
    preview = await _preview(MemoExtraction(dealStage="Propuesta"), deal_id="7")
    assert _stage_row(preview) is None


@pytest.mark.asyncio
async def test_existing_deal_without_stage_signal_preselects_its_current_stage():
    preview = await _preview(MemoExtraction(companyName="Acme"), deal_id="7", stage_confirm=True)
    row = _stage_row(preview)
    assert row.new_value == "11"
    assert row.current_value == "11"
    assert [o["value"] for o in row.options] == ["11", "12", "13"]
    assert [o["label"] for o in row.options] == ["Lead", "Reunión agendada", "Propuesta"]


@pytest.mark.asyncio
async def test_agreed_meeting_in_the_same_pipeline_preselects_meeting_booked():
    preview = await _preview(
        MemoExtraction(dealStage="Propuesta"), deal_id="7", stage_confirm=True, meeting_booked_stage=MEETING_P1,
    )
    assert _stage_row(preview).new_value == "12"


@pytest.mark.asyncio
async def test_agreed_meeting_on_a_deal_in_another_pipeline_uses_inferred_then_current():
    inferred = await _preview(
        MemoExtraction(dealStage="Propuesta"), deal_id="7", stage_confirm=True, meeting_booked_stage=MEETING_P2,
    )
    assert _stage_row(inferred).new_value == "13"

    current = await _preview(
        MemoExtraction(companyName="Partner"), deal_id="8", stage_confirm=True, meeting_booked_stage=MEETING_P1,
    )
    row = _stage_row(current)
    assert row.new_value == "21"
    assert [o["value"] for o in row.options] == ["21", "22"]


@pytest.mark.asyncio
async def test_new_deal_preselects_meeting_booked_or_the_default_stage():
    with_meeting = await _preview(
        MemoExtraction(companyName="Nuevo", dealStage="Propuesta"), stage_confirm=True, meeting_booked_stage=MEETING_P1,
    )
    row = _stage_row(with_meeting)
    assert row.new_value == "12"
    assert row.current_value is None

    no_signal = await _preview(MemoExtraction(companyName="Nuevo"), stage_confirm=True)
    assert _stage_row(no_signal).new_value == "11"


@pytest.mark.asyncio
async def test_contact_only_review_has_no_stage_row():
    preview = await _preview(
        MemoExtraction(contactName="Ana", dealStage="Propuesta"),
        skip_deal=True,
        stage_confirm=True,
        meeting_booked_stage=MEETING_P1,
    )
    assert _stage_row(preview) is None


async def _sync(extraction, *, deal_id="7", allowed=("value",), stage_confirm=None, is_new_deal=False):
    client = _Client()
    svc = PipedriveSyncService(client, None, _Updates())
    kwargs = {} if stage_confirm is None else {"stage_confirm": stage_confirm}
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u-1",
        connection_id="c1",
        extraction=extraction,
        deal_id=deal_id,
        is_new_deal=is_new_deal,
        allowed_fields=list(allowed),
        default_pipeline_id="1",
        default_stage_id="11",
        create_note=False,
        **kwargs,
    )
    assert result.success, result.error
    return client


def _patched_stage(client):
    return [body.get("stage_id") for path, body in client.patches if path.startswith("/deals/")]


@pytest.mark.asyncio
async def test_flag_off_sync_does_not_touch_a_stage_that_is_not_editable():
    client = await _sync(MemoExtraction(dealAmount=200, dealStage="Propuesta"))
    assert _patched_stage(client) == [None]


@pytest.mark.asyncio
async def test_the_stage_the_rep_picked_is_written_even_if_not_editable():
    client = await _sync(
        MemoExtraction(dealStage="Lead", raw_extraction={"stage_id": "13"}),
        allowed=("value", "stage_id"),
        stage_confirm=True,
    )
    assert _patched_stage(client) == [13]


@pytest.mark.asyncio
async def test_approving_the_current_stage_unchanged_writes_no_stage():
    client = await _sync(
        MemoExtraction(dealAmount=200, raw_extraction={"stage_id": "11"}),
        allowed=("value", "stage_id"),
        stage_confirm=True,
    )
    assert _patched_stage(client) == [None]


@pytest.mark.asyncio
async def test_a_removed_stage_row_leaves_the_stage_alone():
    client = await _sync(
        MemoExtraction(dealAmount=200, dealStage="Propuesta"),
        allowed=("value", "stage_id"),
        stage_confirm=True,
    )
    assert _patched_stage(client) == [None]


@pytest.mark.asyncio
async def test_a_new_deal_is_created_in_the_stage_the_rep_picked():
    client = await _sync(
        MemoExtraction(companyName="Nuevo", dealStage="Lead", raw_extraction={"stage_id": "12"}),
        deal_id=None,
        is_new_deal=True,
        allowed=("value", "stage_id"),
        stage_confirm=True,
    )
    deal_post = next(body for path, body in client.posts if path == "/deals")
    assert deal_post["stage_id"] == 12
