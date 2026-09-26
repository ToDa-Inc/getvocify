"""Pipedrive with COMMITMENT_TASKS_ENABLED: review rows and activities come from C04 commitments."""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.memo import MemoExtraction
from app.services.commitment_tasks import CommitmentTask
from app.services.pipedrive.sync import PipedriveSyncService
from tests.pipedrive.test_stage_confirm import _Client, _preview, _Updates

MADRID = ZoneInfo("Europe/Madrid")
TIMED = CommitmentTask("com-1", "call", "Llamar el martes a las 18:00", datetime(2026, 9, 29, 18, 0, tzinfo=MADRID))
LATE = CommitmentTask("com-2", "email", "Mandar el resumen esta noche", datetime(2026, 9, 29, 1, 30, tzinfo=MADRID))
UNDATED = CommitmentTask("com-3", "other", "Preparar la propuesta", None)


class _ActivityClient(_Client):
    """Each activity gets its own id, so a commitment linked to the wrong activity shows."""

    async def post(self, path, json_body=None, *, version="v2"):
        if path != "/activities":
            return await super().post(path, json_body, version=version)
        self.posts.append((path, json_body))
        return {"data": {"id": 100 + sum(1 for p, _ in self.posts if p == "/activities")}}


def _task_rows(preview):
    return [u for u in preview.proposed_updates if u.object_type == "task"]


@pytest.mark.asyncio
async def test_review_rows_come_from_the_commitments():
    preview = await _preview(
        MemoExtraction(nextSteps=["Llamar a Ana"]), deal_id="7", commitment_tasks=[TIMED, UNDATED],
    )
    rows = _task_rows(preview)
    assert [r.field_name for r in rows] == ["next_step_task_0", "next_step_task_1"]
    assert [r.new_value for r in rows] == [TIMED.text, UNDATED.text]
    assert [r.due_date for r in rows] == ["2026-09-29", None]
    assert {r.field_label for r in rows} == {"Next step"}
    assert [r.commitment_id for r in rows] == ["com-1", "com-3"]


@pytest.mark.asyncio
async def test_without_commitment_tasks_the_rows_are_the_next_steps_of_before():
    before = await _preview(MemoExtraction(nextSteps=["Llamar a Ana"]), deal_id="7")
    off = await _preview(MemoExtraction(nextSteps=["Llamar a Ana"]), deal_id="7", commitment_tasks=None)
    assert [r.model_dump() for r in _task_rows(off)] == [r.model_dump() for r in _task_rows(before)]
    assert [r.new_value for r in _task_rows(before)] == ["Llamar a Ana"]
    assert [r.commitment_id for r in _task_rows(before)] == [None]


async def _sync(extraction, **kwargs):
    client = _ActivityClient()
    svc = PipedriveSyncService(client, None, _Updates())
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u-1",
        connection_id="c1",
        extraction=extraction,
        deal_id="7",
        allowed_fields=["value"],
        default_pipeline_id="1",
        default_stage_id="11",
        create_note=False,
        **kwargs,
    )
    assert result.success, result.error
    return result, [body for path, body in client.posts if path == "/activities"]


@pytest.mark.asyncio
async def test_activities_carry_the_commitment_date_and_time_in_utc():
    result, posts = await _sync(MemoExtraction(), commitment_tasks=[TIMED, LATE, UNDATED])
    assert [p["subject"] for p in posts] == [TIMED.text, LATE.text, UNDATED.text]
    assert (posts[0]["due_date"], posts[0]["due_time"]) == ("2026-09-29", "16:00")
    assert (posts[1]["due_date"], posts[1]["due_time"]) == ("2026-09-28", "23:30")
    assert "due_date" not in posts[2] and "due_time" not in posts[2]
    assert result.commitment_task_ids == {"com-1": "101", "com-2": "102", "com-3": "103"}
    assert result.tasks_requested_count == 3
    assert result.tasks_created_count == 3


@pytest.mark.asyncio
async def test_an_edited_row_is_still_written_as_a_next_step():
    result, posts = await _sync(MemoExtraction(nextSteps=["Llamar a Ana el viernes"]), commitment_tasks=[TIMED])
    assert [p["subject"] for p in posts] == [TIMED.text, "Llamar a Ana el viernes"]
    assert "due_date" not in posts[1]
    assert result.commitment_task_ids == {"com-1": "101"}
    assert result.tasks_created_count == 2


@pytest.mark.asyncio
async def test_without_commitment_tasks_next_steps_are_written_as_before():
    result, posts = await _sync(MemoExtraction(nextSteps=["Llamar a Ana"]))
    assert [p["subject"] for p in posts] == ["Llamar a Ana"]
    assert "due_date" not in posts[0]
    assert result.commitment_task_ids == {}
