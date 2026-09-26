"""HubSpot with COMMITMENT_TASKS_ENABLED: review rows and tasks come from C04 commitments."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.memo import MemoExtraction
from app.services.commitment_tasks import CommitmentTask
from app.services.hubspot import sync as sync_module
from app.services.hubspot import tasks as tasks_module
from app.services.hubspot.sync import HubSpotSyncService
from app.services.hubspot.tasks import HubSpotTasksService
from tests.hubspot.test_stage_confirm import EXISTING, _Anything, _Schema, _SyncDeals, _preview, _svc

MADRID = ZoneInfo("Europe/Madrid")
TIMED = CommitmentTask("com-1", "call", "Llamar el martes a las 18:00", datetime(2026, 9, 29, 18, 0, tzinfo=MADRID))
DAY = CommitmentTask("com-2", "send", "Enviar el caso de logística", datetime(2026, 9, 24, 9, 0, tzinfo=MADRID))
UNDATED = CommitmentTask("com-3", "other", "Preparar la propuesta", None)
LEGACY = MemoExtraction(contactName="Ana Pérez", nextSteps=["Llamar a Ana el jueves"])


def _task_rows(preview):
    return [u for u in preview.proposed_updates if u.object_type == "task"]


@pytest.mark.asyncio
async def test_review_rows_come_from_the_commitments():
    preview = await _preview(
        _svc(), extraction=LEGACY, create_new_deal=True, commitment_tasks=[TIMED, DAY, UNDATED],
    )
    rows = _task_rows(preview)
    assert [r.field_name for r in rows] == ["next_step_task_0", "next_step_task_1", "next_step_task_2"]
    assert [r.new_value for r in rows] == [TIMED.text, DAY.text, UNDATED.text]
    assert [r.due_date for r in rows] == ["2026-09-29", "2026-09-24", None]
    assert rows[0].field_label == "Next Step (Task)"
    assert rows[1].field_label == "Next Step 2 (Task)"
    assert [r.commitment_id for r in rows] == ["com-1", "com-2", "com-3"]


@pytest.mark.asyncio
async def test_without_commitment_tasks_the_rows_are_the_next_steps_of_before():
    before = await _preview(_svc(), extraction=LEGACY, create_new_deal=True)
    off = await _preview(_svc(), extraction=LEGACY, create_new_deal=True, commitment_tasks=None)
    assert [r.model_dump() for r in _task_rows(off)] == [r.model_dump() for r in _task_rows(before)]
    assert [r.new_value for r in _task_rows(before)] == ["Llamada con Ana"]
    assert [r.commitment_id for r in _task_rows(before)] == [None]


def _existing(subject, due, status="NOT_STARTED"):
    """A task as _list_tasks_for_object returns it: due_date is naive UTC."""
    return {"subject": subject, "due_date": due.astimezone(timezone.utc).replace(tzinfo=None), "status": status}


class _Tasks(HubSpotTasksService):
    def __init__(self, existing=()):
        super().__init__(client=None)
        self.existing = [{"id": f"old-{i}", **task} for i, task in enumerate(existing)]
        self.created: list[dict] = []
        self.listed_properties: list = []

    async def create_task(self, subject, due_date, deal_id=None, contact_id=None, company_id=None,
                          body=None, priority="MEDIUM", task_type="TODO", hubspot_owner_id=None):
        self.created.append({"subject": subject, "due": due_date, "type": task_type, "deal_id": deal_id})
        return f"T-{len(self.created)}"

    async def list_tasks_for_deal(self, deal_id, properties=None):
        self.listed_properties.append(properties)
        return list(self.existing)

    async def list_tasks_for_contact(self, contact_id, properties=None):
        self.listed_properties.append(properties)
        return list(self.existing)


class _Tracked:
    data = None
    resource_id = None


class _Updates(_Anything):
    def __init__(self):
        self.tracked: list[_Tracked] = []

    @asynccontextmanager
    async def track(self, **_k):
        tracked = _Tracked()
        self.tracked.append(tracked)
        yield tracked


async def _sync(extraction, *, tasks, commitment_tasks=None, deal_id="D1"):
    updates = _Updates()
    svc = HubSpotSyncService(
        client=None,
        contacts=_Anything(),
        companies=_Anything(),
        deals=_SyncDeals(_Schema(), EXISTING),
        associations=_Anything(),
        tasks=tasks,
        crm_updates=updates,
        supabase=None,
    )
    kwargs = {} if commitment_tasks is None else {"commitment_tasks": commitment_tasks}
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u-1",
        connection_id="conn-1",
        extraction=extraction,
        deal_id=deal_id,
        allowed_fields=["amount"],
        allowed_contact_fields=[],
        allowed_company_fields=[],
        allowed_line_item_fields=[],
        create_note=False,
        **kwargs,
    )
    assert result.success, result.error
    return result, updates


@pytest.mark.asyncio
async def test_tasks_are_written_with_the_commitment_text_and_date(monkeypatch):
    monkeypatch.setattr(tasks_module, "_task_tz_now", lambda: datetime(2026, 9, 22, 10, 0, tzinfo=MADRID))
    tasks = _Tasks()
    result, updates = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[TIMED, DAY, UNDATED])
    assert [c["subject"] for c in tasks.created] == [TIMED.text, DAY.text, UNDATED.text]
    assert tasks.created[0]["due"] == TIMED.due_at
    assert tasks.created[1]["due"] == DAY.due_at
    assert tasks.created[2]["due"] == datetime(2026, 9, 25, 9, 0, tzinfo=MADRID)
    assert [c["type"] for c in tasks.created] == ["CALL", "EMAIL", "TODO"]
    assert result.commitment_task_ids == {"com-1": "T-1", "com-2": "T-2", "com-3": "T-3"}
    assert result.tasks_requested_count == 3
    assert result.tasks_created_count == 3
    assert updates.tracked[-1].data["commitment_task_ids"] == result.commitment_task_ids


@pytest.mark.asyncio
async def test_an_edited_row_is_still_written_as_a_next_step():
    tasks = _Tasks()
    result, _ = await _sync(
        MemoExtraction(contactName="Ana Pérez", nextSteps=["Llamar a Ana el jueves"]),
        tasks=tasks,
        commitment_tasks=[DAY],
    )
    assert [c["subject"] for c in tasks.created] == [DAY.text, "Llamada con Ana"]
    assert result.commitment_task_ids == {"com-2": "T-1"}
    assert result.tasks_created_count == 2


@pytest.mark.asyncio
async def test_an_existing_deal_is_not_merged_and_a_same_subject_is_not_duplicated(monkeypatch):
    class _NoMerge:
        def __init__(self, *_a, **_k):
            raise AssertionError("commitment tasks must not go through the task merge")

    monkeypatch.setattr(sync_module, "TaskMergeService", _NoMerge)
    tasks = _Tasks(existing=[_existing("enviar el caso de logística", datetime(2026, 9, 24, 17, 0, tzinfo=MADRID))])
    result, _ = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[TIMED, DAY])
    assert [c["subject"] for c in tasks.created] == [TIMED.text]
    assert result.commitment_task_ids == {"com-1": "T-1", "com-2": "old-0"}
    assert "hs_task_status" in tasks.listed_properties[0]


@pytest.mark.asyncio
async def test_a_completed_task_with_the_same_subject_gets_a_new_task():
    tasks = _Tasks(existing=[_existing(DAY.text, DAY.due_at, status="COMPLETED")])
    result, _ = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[DAY])
    assert [c["subject"] for c in tasks.created] == [DAY.text]
    assert result.commitment_task_ids == {"com-2": "T-1"}


@pytest.mark.asyncio
async def test_an_open_task_with_the_same_subject_on_another_day_gets_a_new_task():
    tasks = _Tasks(existing=[_existing(DAY.text, datetime(2026, 9, 17, 9, 0, tzinfo=MADRID))])
    result, _ = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[DAY])
    assert [c["subject"] for c in tasks.created] == [DAY.text]
    assert result.commitment_task_ids == {"com-2": "T-1"}


@pytest.mark.asyncio
async def test_an_undated_commitment_matches_an_open_task_on_the_default_day(monkeypatch):
    monkeypatch.setattr(tasks_module, "_task_tz_now", lambda: datetime(2026, 9, 22, 10, 0, tzinfo=MADRID))
    tasks = _Tasks(existing=[
        _existing(UNDATED.text, datetime(2026, 9, 23, 9, 0, tzinfo=MADRID)),
        _existing(UNDATED.text, datetime(2026, 9, 25, 9, 0, tzinfo=MADRID)),
    ])
    result, _ = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[UNDATED])
    assert tasks.created == []
    assert result.commitment_task_ids == {"com-3": "old-1"}


@pytest.mark.asyncio
async def test_identical_texts_with_different_dates_are_two_tasks():
    thursday = CommitmentTask("com-a", "call", "Llamar a Ana", datetime(2026, 9, 24, 9, 0, tzinfo=MADRID))
    tuesday = CommitmentTask("com-b", "call", "Llamar a Ana", datetime(2026, 9, 29, 9, 0, tzinfo=MADRID))
    tasks = _Tasks()
    result, _ = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[thursday, tuesday])
    assert [c["due"] for c in tasks.created] == [thursday.due_at, tuesday.due_at]
    assert result.commitment_task_ids == {"com-a": "T-1", "com-b": "T-2"}


@pytest.mark.asyncio
async def test_a_retry_after_a_failed_write_relinks_the_tasks_it_already_created():
    class _Failed(_Updates):
        async def get_memo_updates(self, _memo_id):
            return [{"action_type": "create_tasks", "status": "failed", "data": {}}]

    tasks = _Tasks(existing=[_existing(TIMED.text, TIMED.due_at), _existing(DAY.text, DAY.due_at, "IN_PROGRESS")])
    svc = HubSpotSyncService(
        client=None, contacts=_Anything(), companies=_Anything(), deals=_SyncDeals(_Schema(), EXISTING),
        associations=_Anything(), tasks=tasks, crm_updates=_Failed(), supabase=object(),
    )
    result = await svc.sync_memo(
        memo_id=uuid4(), user_id="u-1", connection_id="conn-1",
        extraction=MemoExtraction(contactName="Ana Pérez", nextSteps=["Llamar a Ana el jueves"]), deal_id="D1",
        allowed_fields=["amount"], allowed_contact_fields=[], allowed_company_fields=[],
        allowed_line_item_fields=[], create_note=False, commitment_tasks=[TIMED, DAY],
    )
    assert result.success, result.error
    assert [c["subject"] for c in tasks.created] == ["Llamada con Ana"]
    assert result.commitment_task_ids == {"com-1": "old-0", "com-2": "old-1"}


@pytest.mark.asyncio
async def test_a_retry_does_not_write_the_tasks_again_and_keeps_their_ids():
    class _Retried(_Updates):
        async def get_memo_updates(self, _memo_id):
            return [{
                "action_type": "create_tasks", "status": "success",
                "data": {"task_ids": ["T-1"], "commitment_task_ids": {"com-1": "T-1"}},
            }]

    tasks = _Tasks()
    svc = HubSpotSyncService(
        client=None, contacts=_Anything(), companies=_Anything(), deals=_SyncDeals(_Schema(), EXISTING),
        associations=_Anything(), tasks=tasks, crm_updates=_Retried(), supabase=object(),
    )
    result = await svc.sync_memo(
        memo_id=uuid4(), user_id="u-1", connection_id="conn-1", extraction=MemoExtraction(), deal_id="D1",
        allowed_fields=["amount"], allowed_contact_fields=[], allowed_company_fields=[],
        allowed_line_item_fields=[], create_note=False, commitment_tasks=[TIMED],
    )
    assert result.success, result.error
    assert tasks.created == []
    assert result.commitment_task_ids == {"com-1": "T-1"}


@pytest.mark.asyncio
async def test_on_hold_follow_up_uses_the_earliest_dated_kept_commitment(monkeypatch):
    seen = []

    async def _capture(ctx, **_k):
        seen.append(tasks_module._next_step_schedule_hints(ctx.extraction))
        return type("R", (), {"warning": None, "failed": None})()

    monkeypatch.setattr(sync_module, "apply_call_outcome", _capture)
    extraction = MemoExtraction(nextSteps=["Llamar a Ana"], raw_extraction={"nextStepSchedules": ["viernes"]})
    svc = HubSpotSyncService(
        client=None, contacts=_Anything(), companies=_Anything(), deals=_SyncDeals(_Schema(), EXISTING),
        associations=_Anything(), tasks=_Tasks(), crm_updates=_Updates(), supabase=None,
    )
    result = await svc.sync_memo(
        memo_id=uuid4(), user_id="u-1", connection_id="conn-1", extraction=extraction, deal_id="D1",
        allowed_fields=["amount"], allowed_contact_fields=[], allowed_company_fields=[],
        allowed_line_item_fields=[], create_note=False, commitment_tasks=[TIMED, UNDATED, DAY],
        call_outcome="on_hold",
    )
    assert result.success, result.error
    assert seen == [["2026-09-24"]]


@pytest.mark.asyncio
async def test_without_commitment_tasks_next_steps_are_written_as_before():
    tasks = _Tasks()
    result, _ = await _sync(
        MemoExtraction(contactName="Ana Pérez", nextSteps=["Llamar a Ana el jueves"]),
        tasks=tasks,
    )
    assert [c["subject"] for c in tasks.created] == ["Llamada con Ana"]
    assert result.commitment_task_ids == {}


class _BatchClient:
    async def get(self, _path):
        return {"results": [{"to": [{"toObjectId": 7}]}]}

    async def post(self, _path, data):
        self.properties = data["properties"]
        return {"results": [{"id": "7", "properties": {
            "hs_task_subject": "Enviar el caso", "hs_timestamp": "1790233200000", "hs_task_status": "COMPLETED",
        }}]}


@pytest.mark.asyncio
async def test_listing_tasks_can_read_their_status():
    client = _BatchClient()
    service = HubSpotTasksService(client=client)
    listed = await service.list_tasks_for_deal("D1", properties=["hs_task_subject", "hs_timestamp", "hs_task_status"])
    assert client.properties == ["hs_task_subject", "hs_timestamp", "hs_task_status"]
    assert listed[0]["status"] == "COMPLETED"
    assert "status" not in (await service.list_tasks_for_deal("D1"))[0]
