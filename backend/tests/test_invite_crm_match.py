"""Item 3: whether an invited email matches a connected CRM's owner. None/True/False,
never raises."""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-invite-crm-match")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-invite-crm-match")

from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
from app.services.invite_crm_match import crm_owner_match_for_invite


def test_null_when_no_crm_is_connected():
    with patch(
        "app.services.invite_crm_match.resolve_sync_connection_for_company",
        return_value=None,
    ):
        assert crm_owner_match_for_invite(MagicMock(), "company-1", "sdr@acme.com") is None


def test_null_when_two_crms_are_connected_with_no_primary():
    with patch(
        "app.services.invite_crm_match.resolve_sync_connection_for_company",
        side_effect=AmbiguousPrimaryCRMError(),
    ):
        assert crm_owner_match_for_invite(MagicMock(), "company-1", "sdr@acme.com") is None


def test_true_when_the_email_is_a_crm_owner():
    writer = MagicMock()
    writer.find_owner_id.return_value = "42"
    with patch(
        "app.services.invite_crm_match.resolve_sync_connection_for_company",
        return_value={"provider": "hubspot", "access_token": "tok"},
    ), patch("app.services.invite_crm_match.owner_writer_from_connection", return_value=writer):
        assert crm_owner_match_for_invite(MagicMock(), "company-1", "sdr@acme.com") is True


def test_false_when_the_email_is_not_a_crm_owner():
    writer = MagicMock()
    writer.find_owner_id.return_value = None
    with patch(
        "app.services.invite_crm_match.resolve_sync_connection_for_company",
        return_value={"provider": "hubspot", "access_token": "tok"},
    ), patch("app.services.invite_crm_match.owner_writer_from_connection", return_value=writer):
        assert crm_owner_match_for_invite(MagicMock(), "company-1", "sdr@acme.com") is False


def test_null_when_the_lookup_itself_raises():
    with patch(
        "app.services.invite_crm_match.resolve_sync_connection_for_company",
        return_value={"provider": "hubspot", "access_token": "tok"},
    ), patch(
        "app.services.invite_crm_match.owner_writer_from_connection",
        side_effect=RuntimeError("boom"),
    ):
        assert crm_owner_match_for_invite(MagicMock(), "company-1", "sdr@acme.com") is None
