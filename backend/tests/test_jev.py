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
