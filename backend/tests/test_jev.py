"""Unit tests for TypeSafe Jev System One integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.llm.jev import JevClient
from app.services.extraction import ExtractionService


@pytest.fixture
def sample_enum_specs():
    return [
        {
            "name": "crm_utilizado",
            "label": "CRM Utilizado",
            "type": "enumeration",
            "object_type": "companies",
            "options": [
                {"value": "hubspot", "label": "HubSpot"},
                {"value": "salesforce", "label": "Salesforce"},
                {"value": "zoho", "label": "Zoho"},
            ],
        },
        {
            "name": "vocify_sales_motion",
            "label": "Sales Motion",
            "type": "enumeration",
            "object_type": "contacts",
            "options": [
                {"value": "field_sales", "label": "Field Sales"},
                {"value": "inside_sales", "label": "Inside Sales"},
            ],
        },
        {
            "name": "dealstage",
            "label": "Deal Stage",
            "type": "enumeration",
            "object_type": "deals",
            "options": [
                {"value": "appointmentscheduled", "label": "Appointment Scheduled"},
                {"value": "closedwon", "label": "Closed Won"},
            ],
        },
    ]


@pytest.mark.asyncio
async def test_jev_client_availability():
    client_with_key = JevClient(api_key="test-key")
    assert client_with_key.is_available is True

    client_without_key = JevClient(api_key="")
    assert client_without_key.is_available is False


@pytest.mark.asyncio
async def test_jev_classify_enums_success(sample_enum_specs):
    client = JevClient(api_key="test-key")

    mock_answers = {
        "companies__crm_utilizado": {
            "type": "choice",
            "choice": "hubspot",
            "confidence": 0.95,
        },
        "contacts__vocify_sales_motion": {
            "type": "choice",
            "choice": "field_sales",
            "confidence": 0.88,
        },
        "deals__dealstage": {
            "type": "choice",
            "choice": "appointmentscheduled",
            "confidence": 0.90,
        },
    }

    with patch.object(client, "_post_systemone", new=AsyncMock(return_value=mock_answers)):
        patch_result = await client.classify_enums("Hablan de comerciales de calle usando HubSpot", sample_enum_specs)

    assert patch_result["company_properties"]["crm_utilizado"] == "hubspot"
    assert patch_result["contact_properties"]["vocify_sales_motion"] == "field_sales"
    assert patch_result["deals"]["dealstage"] == "appointmentscheduled"
    assert patch_result["dealstage"] == "appointmentscheduled"


@pytest.mark.asyncio
async def test_jev_classify_enums_filters_low_confidence_and_not_stated(sample_enum_specs):
    client = JevClient(api_key="test-key")

    mock_answers = {
        "companies__crm_utilizado": {
            "type": "choice",
            "choice": "hubspot",
            "confidence": 0.35,  # Below threshold 0.50
        },
        "contacts__vocify_sales_motion": {
            "type": "choice",
            "choice": "not_stated",  # Explicit not_stated
            "confidence": 0.99,
        },
    }

    with patch.object(client, "_post_systemone", new=AsyncMock(return_value=mock_answers)):
        patch_result = await client.classify_enums("Texto sin datos", sample_enum_specs)

    assert "crm_utilizado" not in patch_result.get("company_properties", {})
    assert "vocify_sales_motion" not in patch_result.get("contact_properties", {})


@pytest.mark.asyncio
async def test_jev_classify_enums_handles_api_failure(sample_enum_specs):
    client = JevClient(api_key="test-key")

    with patch.object(client, "_post_systemone", new=AsyncMock(return_value=None)):
        patch_result = await client.classify_enums("Algún texto", sample_enum_specs)

    assert patch_result == {}


@pytest.mark.asyncio
async def test_jev_detect_language_success():
    client = JevClient(api_key="test-key")

    mock_answers = {
        "spoken_language": {
            "type": "choice",
            "choice": "ca",
            "confidence": 0.85,
        }
    }

    with patch.object(client, "_post_systemone", new=AsyncMock(return_value=mock_answers)):
        lang = await client.detect_language("Bon dia, com va tot? Ens veiem demà", ["es", "ca"])

    assert lang == "ca"


@pytest.mark.asyncio
async def test_jev_detect_language_fallback_on_low_confidence():
    client = JevClient(api_key="test-key")

    mock_answers = {
        "spoken_language": {
            "type": "choice",
            "choice": "ca",
            "confidence": 0.30,  # Below threshold
        }
    }

    with patch.object(client, "_post_systemone", new=AsyncMock(return_value=mock_answers)):
        lang = await client.detect_language("Texto confuso", ["es", "ca"])

    assert lang is None


@pytest.mark.asyncio
async def test_extraction_service_hybrid_integration(sample_enum_specs):
    mock_llm = AsyncMock()
    mock_llm.chat_json.return_value = {
        "companyName": "Acme Corp",
        "summary": "### Resumen\n- Llamada comercial.",
        "nextSteps": ["Enviar propuesta"],
    }

    mock_jev = AsyncMock()
    mock_jev.is_available = True
    mock_jev.classify_enums.return_value = {
        "company_properties": {"crm_utilizado": "hubspot"},
        "contact_properties": {"vocify_sales_motion": "field_sales"},
    }

    service = ExtractionService(llm_client=mock_llm, jev_client=mock_jev)

    extracted = await service.extract(
        transcript="Hablamos con Acme Corp sobre comerciales de calle usando HubSpot",
        field_specs=sample_enum_specs,
    )

    assert extracted.companyName == "Acme Corp"
    assert extracted.summary == "### Resumen\n- Llamada comercial."
    assert extracted.nextSteps == ["Enviar propuesta"]
    # Verify Jev values were applied into extraction
    raw = extracted.raw_extraction or {}
    assert raw.get("company_properties", {}).get("crm_utilizado") == "hubspot"
    assert raw.get("contact_properties", {}).get("vocify_sales_motion") == "field_sales"


def _lead_status_spec():
    return {
        "name": "hs_lead_status",
        "label": "Lead Status",
        "type": "enumeration",
        "object_type": "contacts",
        "options": [
            {"value": "NEW", "label": "New"},
            {"value": "ATTEMPTED_TO_CONTACT", "label": "Attempted to Contact"},
            {"value": "UNQUALIFIED", "label": "Unqualified"},
            {"value": "CONNECTED", "label": "Connected"},
            {"value": "BAD_TIMING", "label": "Bad Timing"},
        ],
    }


@pytest.mark.asyncio
async def test_jev_lead_status_uses_outcome_casuistry_and_blocks_weak_disqualify():
    client = JevClient(api_key="test-key")
    spec = _lead_status_spec()
    captured = {}

    async def fake_post(state, questions):
        captured["questions"] = questions
        return {
            "contacts__hs_lead_status__reach": {
                "choice": "live_conversation",
                "confidence": 0.81,
            },
            "contacts__hs_lead_status__stance": {
                "choice": "rejected",
                "confidence": 0.62,
            },
        }

    with patch.object(client, "_post_systemone", new=fake_post):
        patch_result = await client.classify_enums("Creo que no les encaja, no quedó claro", [spec])

    stance = captured["questions"]["contacts__hs_lead_status__stance"]
    reach = captured["questions"]["contacts__hs_lead_status__reach"]
    assert "never disqualified" in stance["instructions"]
    assert "Not being available" in reach["criteria"]["no_live_conversation"]
    assert "can't talk" in stance["criteria"]["rejected"]
    assert "hs_lead_status" not in patch_result["contact_properties"]
    assert patch_result["_abstained"] == ["hs_lead_status"]


@pytest.mark.asyncio
async def test_jev_lead_status_accepts_a_confident_attempt():
    client = JevClient(api_key="test-key")

    async def fake_post(state, questions):
        return {
            "contacts__hs_lead_status__reach": {
                "choice": "no_live_conversation",
                "confidence": 0.93,
            },
            "contacts__hs_lead_status__stance": {
                "choice": "unavailable",
                "confidence": 0.9,
            },
        }

    with patch.object(client, "_post_systemone", new=fake_post):
        patch_result = await client.classify_enums("Buzón de voz, no contesta", [_lead_status_spec()])

    assert patch_result["contact_properties"]["hs_lead_status"] == "ATTEMPTED_TO_CONTACT"
    assert "_abstained" not in patch_result


@pytest.mark.asyncio
async def test_jev_lead_status_does_not_disqualify_someone_who_could_not_talk():
    client = JevClient(api_key="test-key")

    async def fake_post(state, questions):
        return {
            "contacts__hs_lead_status__reach": {
                "choice": "no_live_conversation",
                "confidence": 0.92,
            },
            "contacts__hs_lead_status__stance": {
                "choice": "rejected",
                "confidence": 0.95,
            },
        }

    with patch.object(client, "_post_systemone", new=fake_post):
        patch_result = await client.classify_enums(
            "S2: Ahora no puedo hablar, estoy en una reunión.",
            [_lead_status_spec()],
        )

    assert patch_result["contact_properties"]["hs_lead_status"] == "ATTEMPTED_TO_CONTACT"


@pytest.mark.asyncio
async def test_extraction_drops_lead_status_when_jev_abstains():
    mock_llm = AsyncMock()
    mock_llm.chat_json.return_value = {
        "summary": "### Llamada\n- No pudo hablar.",
        "nextSteps": [],
        "contact_properties": {"hs_lead_status": "UNQUALIFIED"},
    }
    mock_jev = AsyncMock()
    mock_jev.is_available = True
    mock_jev.classify_enums.return_value = {
        "contact_properties": {},
        "company_properties": {},
        "deals": {},
        "_abstained": ["hs_lead_status"],
    }
    service = ExtractionService(llm_client=mock_llm, jev_client=mock_jev)
    extracted = await service.extract(
        transcript="S2: Ahora no puedo hablar, estoy en una reunión. Llámame luego.",
        field_specs=[_lead_status_spec()],
    )
    contact = (extracted.raw_extraction or {}).get("contact_properties") or {}
    assert contact.get("hs_lead_status") in (None, "")
    assert mock_llm.chat_json.await_count == 1


@pytest.mark.asyncio
async def test_extraction_keeps_jev_attempt_over_a_generative_disqualification():
    mock_llm = AsyncMock()
    mock_llm.chat_json.return_value = {
        "summary": "### Llamada\n- No pudo hablar.",
        "nextSteps": [],
        "contact_properties": {"hs_lead_status": "UNQUALIFIED"},
    }
    mock_jev = AsyncMock()
    mock_jev.is_available = True
    mock_jev.classify_enums.return_value = {
        "contact_properties": {"hs_lead_status": "ATTEMPTED_TO_CONTACT"},
        "company_properties": {},
        "deals": {},
    }
    service = ExtractionService(llm_client=mock_llm, jev_client=mock_jev)
    extracted = await service.extract(
        transcript="S2: Estoy conduciendo, llámame luego. No puedo hablar.",
        field_specs=[_lead_status_spec()],
    )
    contact = (extracted.raw_extraction or {}).get("contact_properties") or {}
    assert contact.get("hs_lead_status") == "ATTEMPTED_TO_CONTACT"
    assert mock_llm.chat_json.await_count == 1


@pytest.mark.asyncio
async def test_extraction_drops_generative_lead_status_when_jev_errors():
    mock_llm = AsyncMock()
    mock_llm.chat_json.return_value = {
        "summary": "### Llamada\n- No pudo hablar.",
        "nextSteps": [],
        "contact_properties": {"hs_lead_status": "UNQUALIFIED"},
    }
    mock_jev = AsyncMock()
    mock_jev.is_available = True
    mock_jev.classify_enums.side_effect = RuntimeError("jev down")
    service = ExtractionService(llm_client=mock_llm, jev_client=mock_jev)
    extracted = await service.extract(
        transcript="S2: Ahora no puedo hablar, estoy en una reunión.",
        field_specs=[_lead_status_spec()],
    )
    contact = (extracted.raw_extraction or {}).get("contact_properties") or {}
    assert contact.get("hs_lead_status") in (None, "")
    assert mock_llm.chat_json.await_count == 1
