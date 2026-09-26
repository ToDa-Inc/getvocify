"""Salesforce with COMMITMENT_TASKS_ENABLED: review rows come from C04 commitments."""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.memo import MemoExtraction
from app.services.commitment_tasks import CommitmentTask
from app.services.salesforce.preview import SalesforcePreviewService

TIMED = CommitmentTask(
    "com-1", "call", "Llamar el martes a las 18:00", datetime(2026, 9, 29, 18, 0, tzinfo=ZoneInfo("Europe/Madrid")),
)
UNDATED = CommitmentTask("com-3", "other", "Preparar la propuesta", None)


class _Schema:
    async def resolve_stage_name(self, stage, default):
        return default

    async def get_curated_field_specs(self, names):
        return [{"name": n, "label": n, "type": "string"} for n in names]


class _Opportunities:
    def map_extraction_to_fields(self, extraction, stage_name=None):
        return {"Name": extraction.companyName}


async def _preview(**kwargs):
    svc = SalesforcePreviewService(client=None, opportunities=_Opportunities(), schema=_Schema(), search=None)
    return await svc.build_preview(
        memo_id=uuid4(),
        transcript="hola",
        extraction=MemoExtraction(companyName="Acme", nextSteps=["Llamar a Ana"]),
        matched_deals=[],
        selected_deal_id=None,
        allowed_fields=["Name"],
        **kwargs,
    )


def _task_rows(preview):
    return [u for u in preview.proposed_updates if u.object_type == "task"]


@pytest.mark.asyncio
async def test_review_rows_come_from_the_commitments():
    rows = _task_rows(await _preview(commitment_tasks=[TIMED, UNDATED]))
    assert [r.field_name for r in rows] == ["next_step_task_0", "next_step_task_1"]
    assert [r.new_value for r in rows] == [TIMED.text, UNDATED.text]
    assert [r.due_date for r in rows] == ["2026-09-29", None]


@pytest.mark.asyncio
async def test_without_commitment_tasks_the_review_is_as_before():
    before = await _preview()
    off = await _preview(commitment_tasks=None)
    assert [u.model_dump() for u in off.proposed_updates] == [u.model_dump() for u in before.proposed_updates]
    assert _task_rows(before) == []
