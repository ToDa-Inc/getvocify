"""HubSpot and Pipedrive share one read envelope. Empty is not 'no emails'."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

import pytest

from app.services.crm_providers.coverage import (
    deny_foreign,
    from_provider_error,
    means_no_activity,
    read_envelope,
)

OBSERVED = "2026-09-22T10:00:00Z"


def _forbidden(connection_id: str) -> dict:
    return from_provider_error(
        "email_scope_missing",
        observed_at=OBSERVED,
        connection_id=connection_id,
        object_type="email",
    )


def test_both_crms_report_a_missing_email_scope_the_same_way():
    hubspot = _forbidden("hs-1")
    pipedrive = _forbidden("pd-1")
    assert hubspot["coverage"] == pipedrive["coverage"] == "forbidden"
    assert hubspot["reason"] == pipedrive["reason"] == "email_scope_missing"
    assert hubspot["items"] == pipedrive["items"] == []
    assert hubspot["next_cursor"] is None
    assert means_no_activity(hubspot) is False
    assert means_no_activity(pipedrive) is False


def test_a_foreign_object_is_denied_before_its_items_are_returned():
    secret = [{"id": "email-9", "subject": "privado"}]
    with pytest.raises(PermissionError):
        deny_foreign("hs-1", "hs-2")
    allowed = read_envelope(
        items=secret,
        coverage="complete",
        observed_at=OBSERVED,
        connection_id="hs-1",
        object_type="email",
    )
    deny_foreign("hs-1", "hs-1")
    assert allowed["items"][0]["connection_id"] == "hs-1"
    assert allowed["items"][0]["subject"] == "privado"
    assert means_no_activity(read_envelope(
        items=[],
        coverage="complete",
        observed_at=OBSERVED,
        connection_id="hs-1",
        object_type="email",
    )) is True
