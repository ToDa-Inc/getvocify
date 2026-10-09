"""HubSpot review: with DEAL_STAGE_CONFIRM_ENABLED the dealstage row is always offered."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.memo import MemoExtraction
from app.services.hubspot.deals import HubSpotDealService
from app.services.hubspot.preview import HubSpotPreviewService
from app.services.hubspot.sync import HubSpotSyncService
from app.services.hubspot.types import (
    CRMSchema,
    HubSpotDeal,
    HubSpotPipeline,
    HubSpotPipelineStage,
    HubSpotProperty,
    PropertyOption,
)

NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
DEFAULT_STAGES = [
    ("appointmentscheduled", "Cita agendada"),
    ("qualifiedtobuy", "Calificado"),
    ("closedwon", "Cerrado ganado"),
]
PARTNER_STAGES = [("p_new", "Nuevo partner"), ("p_meeting", "Reunión partner")]
MEETING_DEFAULT = {"pipeline_id": "default", "stage_id": "appointmentscheduled"}
MEETING_PARTNERS = {"pipeline_id": "partners", "stage_id": "p_meeting"}


def _pipeline(pid, stages, order):
    return HubSpotPipeline(
        id=pid,
        label=pid,
        displayOrder=order,
        stages=[HubSpotPipelineStage(id=s, label=l, displayOrder=i) for i, (s, l) in enumerate(stages)],
    )


class _Schema:
    async def get_deal_schema(self, use_cache=True):
        return CRMSchema(
            object_type="deals",
            properties=[
                HubSpotProperty(name="dealname", label="Deal name", type="string"),
                HubSpotProperty(name="amount", label="Amount", type="number"),
                HubSpotProperty(
                    name="dealstage",
                    label="Deal stage",
                    type="enumeration",
                    fieldType="select",
                    options=[
                        PropertyOption(label=l, value=s) for s, l in DEFAULT_STAGES + PARTNER_STAGES
                    ],
                ),
            ],
            pipelines=[_pipeline("default", DEFAULT_STAGES, 0), _pipeline("partners", PARTNER_STAGES, 1)],
        )

    async def get_multi_object_field_specs(self, **_k):
        return []


class _Deals(HubSpotDealService):
    def __init__(self, schema, deals):
        super().__init__(client=None, search=None, schema=schema)
        self._deals = deals

    async def get(self, deal_id, properties=None):
        return HubSpotDeal(id=deal_id, properties=dict(self._deals[deal_id]), createdAt=NOW, updatedAt=NOW)


def _svc(deals=None):
    schema = _Schema()
    return HubSpotPreviewService(
        client=None,
        deal_service=_Deals(schema, deals or {}),
        schema_service=schema,
    )


EXISTING = {
    "D1": {"dealname": "Acme", "pipeline": "default", "dealstage": "qualifiedtobuy", "amount": "100"},
    "P1": {"dealname": "Partner", "pipeline": "partners", "dealstage": "p_new"},
}


async def _preview(svc, *, extraction, deal_id=None, create_new_deal=False, skip_deal=False, **kw):
    return await svc.build_preview(
        memo_id=uuid4(),
        transcript="hola",
        extraction=extraction,
        matched_deals=[],
        selected_deal_id=deal_id,
        allowed_fields=["amount"],
        default_pipeline_id="default",
        default_stage_id="appointmentscheduled",
        allowed_contact_fields=[],
        allowed_company_fields=[],
        allowed_line_item_fields=[],
        create_new_deal=create_new_deal,
        skip_deal=skip_deal,
        **kw,
    )


def _stage_row(preview):
    rows = [u for u in preview.proposed_updates if u.field_name == "dealstage"]
    assert len(rows) <= 1
    return rows[0] if rows else None


@pytest.mark.asyncio
async def test_flag_off_existing_deal_without_editable_dealstage_has_no_stage_row():
    preview = await _preview(_svc(EXISTING), extraction=MemoExtraction(dealStage="closedwon"), deal_id="D1")
    assert _stage_row(preview) is None


@pytest.mark.asyncio
async def test_existing_deal_without_stage_signal_preselects_its_current_stage():
    preview = await _preview(
        _svc(EXISTING), extraction=MemoExtraction(companyName="Acme"), deal_id="D1", stage_confirm=True,
    )
    row = _stage_row(preview)
    assert row is not None
    assert row.new_value == "qualifiedtobuy"
    assert row.current_value == "qualifiedtobuy"
    assert [o["value"] for o in row.options] == [s for s, _ in DEFAULT_STAGES]
    assert preview.proposed_updates[0].field_name == "dealstage"


@pytest.mark.asyncio
async def test_agreed_meeting_in_the_same_pipeline_preselects_meeting_booked():
    preview = await _preview(
        _svc(EXISTING),
        extraction=MemoExtraction(dealStage="Cerrado ganado"),
        deal_id="D1",
        stage_confirm=True,
        meeting_booked_stage=MEETING_DEFAULT,
    )
    row = _stage_row(preview)
    assert row.new_value == "appointmentscheduled"
    assert row.current_value == "qualifiedtobuy"


@pytest.mark.asyncio
async def test_agreed_meeting_on_a_deal_in_another_pipeline_uses_inferred_then_current():
    inferred = await _preview(
        _svc(EXISTING),
        extraction=MemoExtraction(dealStage="Cerrado ganado"),
        deal_id="D1",
        stage_confirm=True,
        meeting_booked_stage=MEETING_PARTNERS,
    )
    assert _stage_row(inferred).new_value == "closedwon"

    current = await _preview(
        _svc(EXISTING),
        extraction=MemoExtraction(companyName="Partner"),
        deal_id="P1",
        stage_confirm=True,
        meeting_booked_stage=MEETING_DEFAULT,
    )
    row = _stage_row(current)
    assert row.new_value == "p_new"
    assert [o["value"] for o in row.options] == [s for s, _ in PARTNER_STAGES]


@pytest.mark.asyncio
async def test_without_a_meeting_suggestion_the_inferred_stage_is_preselected():
    preview = await _preview(
        _svc(EXISTING),
        extraction=MemoExtraction(dealStage="Cerrado ganado"),
        deal_id="D1",
        stage_confirm=True,
        meeting_booked_stage=None,
    )
    assert _stage_row(preview).new_value == "closedwon"


@pytest.mark.asyncio
async def test_new_deal_preselects_meeting_booked_or_the_default_stage():
    with_meeting = await _preview(
        _svc(),
        extraction=MemoExtraction(companyName="Nuevo", dealStage="Calificado"),
        create_new_deal=True,
        stage_confirm=True,
        meeting_booked_stage=MEETING_DEFAULT,
    )
    row = _stage_row(with_meeting)
    assert row.new_value == "appointmentscheduled"
    assert row.current_value is None

    no_signal = await _preview(
        _svc(),
        extraction=MemoExtraction(companyName="Nuevo"),
        create_new_deal=True,
        stage_confirm=True,
    )
    assert _stage_row(no_signal).new_value == "appointmentscheduled"


class _Anything:
    def __getattr__(self, _name):
        async def _call(*_a, **_k):
            return []
        return _call


class _Tracked:
    data = None
    resource_id = None


class _Updates(_Anything):
    @asynccontextmanager
    async def track(self, **_k):
        yield _Tracked()


class _SyncDeals(_Deals):
    def __init__(self, schema, deals):
        super().__init__(schema, deals)
        self.updates: list[dict] = []

    async def update(self, deal_id, properties, hubspot_owner_id=None):
        self.updates.append(dict(properties))
        return HubSpotDeal(id=deal_id, properties=dict(properties), createdAt=NOW, updatedAt=NOW)


async def _sync(extraction, *, allowed_fields, stage_confirm=None, deal_id="D1"):
    deals = _SyncDeals(_Schema(), EXISTING)
    svc = HubSpotSyncService(
        client=None,
        contacts=_Anything(),
        companies=_Anything(),
        deals=deals,
        associations=_Anything(),
        tasks=_Anything(),
        crm_updates=_Updates(),
        supabase=None,
    )
    kwargs = {} if stage_confirm is None else {"stage_confirm": stage_confirm}
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u-1",
        connection_id="conn-1",
        extraction=extraction,
        deal_id=deal_id,
        allowed_fields=allowed_fields,
        allowed_contact_fields=[],
        allowed_company_fields=[],
        allowed_line_item_fields=[],
        create_note=False,
        **kwargs,
    )
    assert result.success, result.error
    return deals.updates


@pytest.mark.asyncio
async def test_flag_off_sync_does_not_touch_a_stage_that_is_not_editable():
    updates = await _sync(MemoExtraction(dealAmount=200, dealStage="closedwon"), allowed_fields=["amount"])
    assert updates and all("dealstage" not in u for u in updates)


@pytest.mark.asyncio
async def test_the_stage_the_rep_picked_is_written():
    updates = await _sync(
        MemoExtraction(dealStage="closedwon"), allowed_fields=["amount", "dealstage"], stage_confirm=True,
    )
    assert updates[-1]["dealstage"] == "closedwon"


@pytest.mark.asyncio
async def test_approving_the_current_stage_unchanged_writes_no_stage():
    updates = await _sync(
        MemoExtraction(dealAmount=200, dealStage="qualifiedtobuy"),
        allowed_fields=["amount", "dealstage"],
        stage_confirm=True,
    )
    assert updates and all("dealstage" not in u for u in updates)


@pytest.mark.asyncio
async def test_a_removed_stage_row_leaves_the_stage_alone():
    updates = await _sync(
        MemoExtraction(dealAmount=200), allowed_fields=["amount", "dealstage"], stage_confirm=True,
    )
    assert updates and all("dealstage" not in u for u in updates)


@pytest.mark.asyncio
async def test_contact_only_review_has_no_stage_row():
    preview = await _preview(
        _svc(EXISTING),
        extraction=MemoExtraction(contactName="Ana", companyName="Acme", dealStage="closedwon"),
        skip_deal=True,
        stage_confirm=True,
        meeting_booked_stage=MEETING_DEFAULT,
    )
    assert _stage_row(preview) is None
