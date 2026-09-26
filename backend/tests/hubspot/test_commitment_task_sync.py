"""HubSpot with COMMITMENT_TASKS_ENABLED: review rows and tasks come from C04 commitments."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.memo import MemoExtraction
from app.services.commitment_tasks import CommitmentTask
from app.services.hubspot import sync as sync_module
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


@pytest.mark.asyncio
async def test_without_commitment_tasks_the_rows_are_the_next_steps_of_before():
    before = await _preview(_svc(), extraction=LEGACY, create_new_deal=True)
    off = await _preview(_svc(), extraction=LEGACY, create_new_deal=True, commitment_tasks=None)
    assert [r.model_dump() for r in _task_rows(off)] == [r.model_dump() for r in _task_rows(before)]
    assert [r.new_value for r in _task_rows(before)] == ["Llamada con Ana"]


@pytest.mark.asyncio
async def test_current_c04_without_commitments_has_no_task_rows():
    preview = await _preview(_svc(), extraction=LEGACY, create_new_deal=True, commitment_tasks=[])
    assert _task_rows(preview) == []


class _Tasks(HubSpotTasksService):
    def __init__(self, existing=()):
        super().__init__(client=None)
        self.existing = [{"id": f"old-{i}", "subject": s, "due_date": None} for i, s in enumerate(existing)]
        self.created: list[dict] = []

    async def create_task(self, subject, due_date, deal_id=None, contact_id=None, company_id=None,
                          body=None, priority="MEDIUM", task_type="TODO", hubspot_owner_id=None):
        self.created.append({"subject": subject, "due": due_date, "type": task_type, "deal_id": deal_id})
        return f"T-{len(self.created)}"

    async def list_tasks_for_deal(self, deal_id, properties=None):
        return list(self.existing)

    async def list_tasks_for_contact(self, contact_id, properties=None):
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
async def test_tasks_are_written_with_the_commitment_text_and_date():
    tasks = _Tasks()
    result, updates = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[TIMED, DAY, UNDATED])
    assert [c["subject"] for c in tasks.created] == [TIMED.text, DAY.text, UNDATED.text]
    assert tasks.created[0]["due"] == TIMED.due_at
    assert tasks.created[1]["due"] == DAY.due_at
    default = tasks.created[2]["due"]
    assert (default.hour, default.minute) == (9, 0)
    assert default.date() == (datetime.now(MADRID) + timedelta(days=3)).date()
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
    tasks = _Tasks(existing=["enviar el caso de logística"])
    result, _ = await _sync(MemoExtraction(), tasks=tasks, commitment_tasks=[TIMED, DAY])
    assert [c["subject"] for c in tasks.created] == [TIMED.text]
    assert result.commitment_task_ids == {"com-1": "T-1"}


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
async def test_without_commitment_tasks_next_steps_are_written_as_before():
    tasks = _Tasks()
    result, _ = await _sync(
        MemoExtraction(contactName="Ana Pérez", nextSteps=["Llamar a Ana el jueves"]),
        tasks=tasks,
    )
    assert [c["subject"] for c in tasks.created] == ["Llamada con Ana"]
    assert result.commitment_task_ids == {}
