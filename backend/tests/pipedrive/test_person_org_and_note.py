from uuid import uuid4

import pytest

from app.models.approval import DealMatch
from app.models.memo import MemoExtraction
from app.services.extraction import _normalize_raw_extraction
from app.services.pipedrive.sync import note_includes_transcript
from app.services.preview_targets import open_linked_deal_ids, resolve_preview_deal_selection

from .test_sync import _FakeClient, _svc

ORG_FIELD = "6a7d9c34b1fa5a64ef27b7dd285b5603dafc4174"


class _PersonInOrg(_FakeClient):
    async def get(self, path, *, version="v2", params=None):
        if path == "/persons/20":
            return {"data": {"id": 20, "name": "Alex", "org_id": 66}}
        if path == "/organizations/66":
            return {"data": {"id": 66, "name": "Rosca"}}
        return await super().get(path, version=version, params=params)


@pytest.mark.asyncio
async def test_organization_fields_go_to_the_persons_own_organization_when_none_is_named():
    svc, client = _svc(_PersonInOrg())
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(
            summary="Usan Novatrans como ERP",
            raw_extraction={"company_properties": {ORG_FIELD: "Novatrans"}},
        ),
        skip_deal=True,
        contact_id="20",
        auto_create_companies=True,
        allowed_company_fields=["name", ORG_FIELD],
        create_note=True,
    )
    assert result.success is True
    assert result.company_id == "66"
    assert "/organizations" not in [p[0] for p in client.posts]
    org_patch = next(p for p in client.patches if p[0] == "/organizations/66")
    assert org_patch[1]["custom_fields"][ORG_FIELD] == "Novatrans"
    note = next(p for p in client.posts if p[0] == "/notes")
    assert note[1]["org_id"] == 66


def _deal(deal_id, is_open):
    return DealMatch(
        deal_id=deal_id, deal_name="d", last_updated="", match_confidence=0.95, match_reason="Linked", is_open=is_open
    )


class _Anchor:
    def __init__(self, deals):
        self.deal_matches = deals


def _select(deals, **k):
    return resolve_preview_deal_selection(
        deal_id=k.get("deal_id"),
        create_new_deal=k.get("create_new_deal", False),
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=k.get("skip_deal", False),
        linked_open_deal_ids=open_linked_deal_ids(_Anchor(deals)),
    )


def test_a_contact_with_one_open_deal_lands_on_it():
    assert _select([_deal("58874", True), _deal("1", False)]) == ("58874", False)


def test_several_open_deals_or_an_unknown_state_leave_the_choice_to_the_rep():
    assert _select([_deal("1", True), _deal("2", True)]) == (None, False)
    assert _select([_deal("1", None)]) == (None, False)


def test_no_deal_and_new_deal_still_win_over_the_default():
    assert _select([_deal("1", True)], skip_deal=True) == (None, False)
    assert _select([_deal("1", True)], create_new_deal=True) == (None, True)


SPECS = [
    {"name": "sector", "object_type": "companies", "type": "enumeration",
     "options": [{"value": "12", "label": "Distribución"}, {"value": "13", "label": "Otro"}]},
    {"name": "pains", "object_type": "deals", "type": "enumeration",
     "options": [{"value": "1", "label": "No le interesa"}, {"value": "2", "label": "Mal soporte a cliente"}]},
    {"name": "stage_id", "object_type": "deals", "type": "enumeration", "options": [{"value": "196", "label": "Contacto"}]},
]


def test_a_value_that_is_not_one_of_the_crms_options_is_not_proposed():
    out = _normalize_raw_extraction(
        {
            "pains": "No tienen una solución",
            "stage_id": "Contacto importado",
            "company_properties": {"sector": "Transporte en general"},
        },
        SPECS,
    )
    assert out["pains"] is None
    assert out["company_properties"]["sector"] is None
    assert out["stage_id"] == "Contacto importado"


def test_option_labels_still_map_to_their_values_and_lists_keep_the_real_ones():
    out = _normalize_raw_extraction(
        {"pains": ["no le interesa", "inventado"], "company_properties": {"sector": "Distribución"}}, SPECS
    )
    assert out["pains"] == ["1"]
    assert out["company_properties"]["sector"] == "12"


def test_the_note_carries_the_transcript_unless_switched_off():
    assert note_includes_transcript(None) is True
    assert note_includes_transcript({}) is True
    assert note_includes_transcript({"note_includes_transcript": False}) is False


@pytest.mark.asyncio
async def test_summary_only_note_leaves_the_transcript_out(monkeypatch):
    svc, client = _svc()

    async def off(_connection_id):
        return False

    monkeypatch.setattr(svc, "_note_includes_transcript", off)
    await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", summary="Resumen de la llamada"),
        skip_deal=True,
        contact_id="20",
        create_note=True,
        transcript="S1: una frase muy reconocible del transcript",
    )
    note = next(p for p in client.posts if p[0] == "/notes")
    assert "Resumen de la llamada" in note[1]["content"]
    assert "reconocible" not in note[1]["content"]
