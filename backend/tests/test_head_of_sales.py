"""Founder request: the first account of a company is always the Head of Sales
(owner) - self-signup, or created/invited from the super-admin console - and an
invite tells the rep it goes for CRM owner matching (item 3), never blocking on it."""

import asyncio
import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-head-of-sales")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-head-of-sales")

import pytest
from fastapi import HTTPException

from app.api.admin import AdminAddMemberRequest, AdminInviteRequest, add_member_to_company_admin, invite_to_company_admin
from app.emails.templates import build_invite_email_html
from app.services.company import CompanyService


def _svc() -> CompanyService:
    return CompanyService(MagicMock())


# --- CompanyService.is_first_invite / create_invite(role="owner") -----------------


def test_is_first_invite_true_with_no_members_and_no_invites():
    svc = _svc()
    svc.count_active_members = MagicMock(return_value=0)
    svc.list_pending_invites = MagicMock(return_value=[])
    assert svc.is_first_invite("company-1") is True


def test_is_first_invite_false_once_someone_is_active():
    svc = _svc()
    svc.count_active_members = MagicMock(return_value=1)
    svc.list_pending_invites = MagicMock(return_value=[])
    assert svc.is_first_invite("company-1") is False


def test_is_first_invite_false_with_a_pending_invite():
    svc = _svc()
    svc.count_active_members = MagicMock(return_value=0)
    svc.list_pending_invites = MagicMock(return_value=[{"id": "inv-1"}])
    assert svc.is_first_invite("company-1") is False


def test_create_invite_accepts_owner_role_for_the_first_invite():
    svc = _svc()
    svc.is_first_invite = MagicMock(return_value=True)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "email": "owner@acme.com", "role": "owner", "expires_at": "2026-01-01T00:00:00Z"}]
    )

    invite, invite_url, email_sent, crm_owner_match = asyncio.run(
        svc.create_invite(company_id="company-1", email="owner@acme.com", role="owner", send_email=False)
    )
    assert invite["role"] == "owner"
    assert crm_owner_match is None  # no CRM connection resolvable from a bare mock


def test_create_invite_rejects_owner_role_once_a_head_of_sales_exists():
    svc = _svc()
    svc.is_first_invite = MagicMock(return_value=False)
    svc.ensure_seat_available = MagicMock()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc.create_invite(company_id="company-1", email="second@acme.com", role="owner"))
    assert exc.value.status_code == 400


# --- crm_owner_match true/false/null ------------------------------------------


def test_create_invite_reports_crm_owner_match_true():
    svc = _svc()
    svc.is_first_invite = MagicMock(return_value=False)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "email": "sdr@acme.com", "role": "member", "expires_at": "2026-01-01T00:00:00Z"}]
    )
    with patch("app.services.invite_crm_match.crm_owner_match_for_invite", return_value=True):
        _invite, _url, _sent, crm_owner_match = asyncio.run(
            svc.create_invite(company_id="company-1", email="sdr@acme.com", role="member", send_email=False)
        )
    assert crm_owner_match is True


def test_create_invite_reports_crm_owner_match_false():
    svc = _svc()
    svc.is_first_invite = MagicMock(return_value=False)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "email": "sdr@acme.com", "role": "member", "expires_at": "2026-01-01T00:00:00Z"}]
    )
    with patch("app.services.invite_crm_match.crm_owner_match_for_invite", return_value=False):
        _invite, _url, _sent, crm_owner_match = asyncio.run(
            svc.create_invite(company_id="company-1", email="sdr@acme.com", role="member", send_email=False)
        )
    assert crm_owner_match is False


def test_create_invite_reports_crm_owner_match_null_without_a_crm():
    svc = _svc()
    svc.is_first_invite = MagicMock(return_value=False)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "email": "sdr@acme.com", "role": "member", "expires_at": "2026-01-01T00:00:00Z"}]
    )
    with patch("app.services.invite_crm_match.crm_owner_match_for_invite", return_value=None):
        _invite, _url, _sent, crm_owner_match = asyncio.run(
            svc.create_invite(company_id="company-1", email="sdr@acme.com", role="member", send_email=False)
        )
    assert crm_owner_match is None


def test_crm_owner_match_never_blocks_the_invite_even_if_the_lookup_raises():
    svc = _svc()
    svc.is_first_invite = MagicMock(return_value=False)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "email": "sdr@acme.com", "role": "member", "expires_at": "2026-01-01T00:00:00Z"}]
    )
    with patch(
        "app.services.invite_crm_match.crm_owner_match_for_invite",
        side_effect=RuntimeError("boom"),
    ):
        # Even if the lookup itself blows up, the invite is still created - null,
        # not a 500.
        invite, _url, _sent, crm_owner_match = asyncio.run(
            svc.create_invite(company_id="company-1", email="sdr@acme.com", role="member", send_email=False)
        )
    assert invite["id"] == "inv-1"
    assert crm_owner_match is None


# --- Admin console: first account created/invited is the Head of Sales ------------


def test_admin_add_member_forces_owner_role_for_the_first_company_member():
    supabase = MagicMock()
    company_id = uuid4()
    user_id = uuid4()
    with patch.object(CompanyService, "ensure_seat_available", return_value=None), patch.object(
        CompanyService, "get_membership", return_value=None
    ), patch.object(CompanyService, "is_first_invite", return_value=True):
        asyncio.run(
            add_member_to_company_admin(
                company_id=company_id,
                body=AdminAddMemberRequest(user_id=user_id, role="member"),
                supabase=supabase,
                _="test-key",
            )
        )
    member_insert = next(
        call.args[0]
        for call in supabase.table.return_value.insert.call_args_list
        if "role" in call.args[0] and "user_id" in call.args[0]
    )
    assert member_insert["role"] == "owner"


def test_admin_add_member_keeps_ordinary_role_once_a_head_of_sales_exists():
    supabase = MagicMock()
    company_id = uuid4()
    user_id = uuid4()
    with patch.object(CompanyService, "ensure_seat_available", return_value=None), patch.object(
        CompanyService, "get_membership", return_value=None
    ), patch.object(CompanyService, "is_first_invite", return_value=False):
        asyncio.run(
            add_member_to_company_admin(
                company_id=company_id,
                body=AdminAddMemberRequest(user_id=user_id, role="member"),
                supabase=supabase,
                _="test-key",
            )
        )
    member_insert = next(
        call.args[0]
        for call in supabase.table.return_value.insert.call_args_list
        if "role" in call.args[0] and "user_id" in call.args[0]
    )
    assert member_insert["role"] == "member"


def test_admin_invite_forces_owner_role_for_the_first_invite():
    supabase = MagicMock()
    company_id = uuid4()
    with patch.object(CompanyService, "is_first_invite", return_value=True), patch.object(
        CompanyService,
        "create_invite",
        return_value=(
            {"id": "inv-1", "email": "founder@acme.com", "role": "owner", "expires_at": "2026-01-01T00:00:00Z"},
            "https://vocify.app/invite/tok",
            False,
            None,
        ),
    ) as create_invite:
        asyncio.run(
            invite_to_company_admin(
                company_id=company_id,
                body=AdminInviteRequest(email="founder@acme.com", role="member"),
                supabase=supabase,
                _="test-key",
            )
        )
    assert create_invite.call_args.kwargs["role"] == "owner"


# --- Invite email content (item 4) -------------------------------------------------


def test_invite_email_names_the_commercial_type_and_the_inviter():
    html = build_invite_email_html(
        company_name="Acme",
        invite_url="https://vocify.app/invite/tok",
        sales_role="sdr",
        inviter_name="Dana Head",
    )
    assert "SDR" in html
    assert "Dana Head" in html
    assert "Acme" in html


def test_invite_email_omits_type_and_inviter_when_not_given():
    html = build_invite_email_html(company_name="Acme", invite_url="https://vocify.app/invite/tok")
    assert "as a <strong>" not in html
    assert "your Head of Sales" not in html
