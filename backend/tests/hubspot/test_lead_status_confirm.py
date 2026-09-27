"""HubSpot review lead mode (F16): hs_lead_status row is always first when options exist."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.approval import ContactMatch
from app.models.memo import MemoExtraction
from app.services.hubspot.deals import HubSpotDealService
from app.services.hubspot.preview import HubSpotPreviewService
from app.services.hubspot.types import (
    CRMSchema,
    HubSpotContact,
    HubSpotDeal,
    HubSpotPipeline,
    HubSpotPipelineStage,
    HubSpotProperty,
    PropertyOption,
)

NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
LEAD_OPTIONS = [
    ("NEW", "Nuevo"),
    ("CONNECTED", "Conectado"),
    ("IN_PROGRESS", "En progreso"),
    ("UNQUALIFIED", "No cualificado"),
]
DEFAULT_STAGES = [
    ("appointmentscheduled", "Cita agendada"),
    ("qualifiedtobuy", "Calificado"),
]
BOOKED = ["CONNECTED", "IN_PROGRESS"]
CONTACT = ContactMatch(contact_id="C1", email="ana@acme.test", name="Ana")


def _pipeline(pid, stages, order):
    return HubSpotPipeline(
        id=pid,
        label=pid,
        displayOrder=order,
        stages=[HubSpotPipelineStage(id=s, label=l, displayOrder=i) for i, (s, l) in enumerate(stages)],
    )


class _Schema:
    def __init__(self, *, lead_options=True):
        self._lead_options = lead_options

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
                    options=[PropertyOption(label=l, value=s) for s, l in DEFAULT_STAGES],
                ),
            ],
            pipelines=[_pipeline("default", DEFAULT_STAGES, 0)],
        )

    async def get_multi_object_field_specs(self, **_k):
        specs = [
            {"object_type": "deals", "name": "amount", "label": "Amount", "type": "number"},
            {
                "object_type": "deals",
                "name": "dealstage",
                "label": "Deal Stage",
                "type": "enumeration",
                "options": [{"value": s, "label": l} for s, l in DEFAULT_STAGES],
            },
        ]
        if self._lead_options:
            specs.append({
                "object_type": "contacts",
                "name": "hs_lead_status",
                "label": "Lead Status",
                "type": "enumeration",
                "options": [{"value": s, "label": l} for s, l in LEAD_OPTIONS],
            })
        else:
            specs.append({
                "object_type": "contacts",
                "name": "hs_lead_status",
                "label": "Lead Status",
                "type": "enumeration",
                "options": [],
            })
        return specs


class _Deals(HubSpotDealService):
    def __init__(self, schema, deals):
        super().__init__(client=None, search=None, schema=schema)
        self._deals = deals

    async def get(self, deal_id, properties=None):
        return HubSpotDeal(id=deal_id, properties=dict(self._deals[deal_id]), createdAt=NOW, updatedAt=NOW)


class _Contacts:
    def __init__(self, props: dict):
        self._props = props

    async def get(self, contact_id, properties=None):
        return HubSpotContact(id=contact_id, properties=dict(self._props), createdAt=NOW, updatedAt=NOW)

    def map_extraction_to_properties(self, extraction):
        return {}


def _svc(*, contact_props=None, lead_options=True):
    schema = _Schema(lead_options=lead_options)
    return HubSpotPreviewService(
        client=None,
        deal_service=_Deals(schema, {
            "D1": {"dealname": "Acme", "pipeline": "default", "dealstage": "qualifiedtobuy", "amount": "100"},
        }),
        schema_service=schema,
        contact_service=_Contacts(contact_props or {"hs_lead_status": "NEW", "firstname": "Ana"}),
    )


def _extraction(*, lead=None, **kwargs) -> MemoExtraction:
    raw = dict(kwargs.pop("raw_extraction", None) or {})
    if lead is not None:
        contact = dict(raw.get("contact_properties") or {})
        contact["hs_lead_status"] = lead
        raw["contact_properties"] = contact
    return MemoExtraction(raw_extraction=raw or None, **kwargs)


async def _preview(svc, *, extraction, **kw):
    return await svc.build_preview(
        memo_id=uuid4(),
        transcript="hola",
        extraction=extraction,
        matched_deals=[],
        selected_deal_id="D1",
        allowed_fields=["amount"],
        default_pipeline_id="default",
        default_stage_id="appointmentscheduled",
        allowed_contact_fields=[],
        allowed_company_fields=[],
        allowed_line_item_fields=[],
        selected_contact=CONTACT,
        **kw,
    )


def _lead_row(preview):
    rows = [
        u for u in preview.proposed_updates
        if u.field_name == "hs_lead_status" and (u.object_type or "contacts") == "contacts"
    ]
    assert len(rows) <= 1
    return rows[0] if rows else None


@pytest.mark.asyncio
async def test_lead_status_row_is_always_present_and_first_in_lead_mode():
    preview = await _preview(
        _svc(),
        extraction=_extraction(companyName="Acme"),
        stage_confirm=True,
        lead_status_confirm=True,
        queue_booked_states=BOOKED,
    )
    row = _lead_row(preview)
    assert row is not None
    assert preview.proposed_updates[0].field_name == "hs_lead_status"
    assert [o["value"] for o in row.options] == [s for s, _ in LEAD_OPTIONS]


@pytest.mark.asyncio
async def test_meeting_agreed_preselects_first_booked_lead_state():
    preview = await _preview(
        _svc(contact_props={"hs_lead_status": "NEW"}),
        extraction=_extraction(lead="IN_PROGRESS"),
        stage_confirm=True,
        lead_status_confirm=True,
        queue_booked_states=BOOKED,
        meeting_agreed_for_lead=True,
    )
    row = _lead_row(preview)
    assert row.new_value == "CONNECTED"
    assert row.current_value == "NEW"


@pytest.mark.asyncio
async def test_without_meeting_preselects_extraction_suggestion():
    preview = await _preview(
        _svc(contact_props={"hs_lead_status": "NEW"}),
        extraction=_extraction(lead="IN_PROGRESS"),
        stage_confirm=True,
        lead_status_confirm=True,
        queue_booked_states=BOOKED,
        meeting_agreed_for_lead=False,
    )
    assert _lead_row(preview).new_value == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_without_meeting_or_suggestion_preselects_current_contact_status():
    preview = await _preview(
        _svc(contact_props={"hs_lead_status": "NEW"}),
        extraction=_extraction(companyName="Acme"),
        stage_confirm=True,
        lead_status_confirm=True,
        queue_booked_states=BOOKED,
        meeting_agreed_for_lead=False,
    )
    row = _lead_row(preview)
    assert row.new_value == "NEW"
    assert row.current_value == "NEW"


@pytest.mark.asyncio
async def test_portal_without_lead_status_options_has_no_row():
    preview = await _preview(
        _svc(lead_options=False),
        extraction=_extraction(lead="CONNECTED"),
        stage_confirm=True,
        lead_status_confirm=True,
        queue_booked_states=BOOKED,
        meeting_agreed_for_lead=True,
    )
    assert _lead_row(preview) is None


@pytest.mark.asyncio
async def test_flag_off_does_not_force_a_lead_status_row():
    """Without lead_status_confirm, behaviour matches pre-F16 (no forced first lead row)."""
    preview = await _preview(
        _svc(),
        extraction=_extraction(companyName="Acme"),
        stage_confirm=True,
    )
    assert _lead_row(preview) is None
    assert preview.proposed_updates[0].field_name == "dealstage"
