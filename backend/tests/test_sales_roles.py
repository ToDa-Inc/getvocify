"""Tests for T1: sales_role, SDR->AE routing and visibility per member (D1-D3)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-sales-roles")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-sales-roles")

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.company import CompanyService, Membership


def _actor(role: str = "owner") -> Membership:
    return Membership(
        id="actor-member",
        company_id="company-1",
        user_id="actor-user",
        role=role,
        status="active",
    )


def test_update_member_profile_requires_manage_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor("member"),
            member_id="m1",
            sales_role="sdr",
        )
    assert exc.value.status_code == 403


def test_update_member_profile_rejects_invalid_sales_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "u1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            sales_role="closer",
        )
    assert exc.value.status_code == 400


def test_update_member_profile_rejects_invalid_visibility():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "u1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            visibility="everyone",
        )
    assert exc.value.status_code == 400


def test_update_member_profile_rejects_self_handoff():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            handoff_ae_user_id="sdr-1",
        )
    assert exc.value.status_code == 400
    assert "themselves" in exc.value.detail


def test_update_member_profile_rejects_ae_not_ae_or_general():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    svc._get_member_row_by_user_id = MagicMock(
        return_value={"id": "m2", "user_id": "sdr-2", "sales_role": "sdr"}
    )
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            handoff_ae_user_id="sdr-2",
        )
    assert exc.value.status_code == 400
    assert "AE" in exc.value.detail


def test_update_member_profile_accepts_valid_handoff_and_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    svc._get_member_row_by_user_id = MagicMock(
        return_value={"id": "m2", "user_id": "ae-1", "sales_role": "ae"}
    )
    update_mock = supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    update_mock.return_value = MagicMock(
        data=[{"id": "m1", "sales_role": "sdr", "handoff_ae_user_id": "ae-1", "visibility": "own"}]
    )

    result = svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
        sales_role="sdr",
        handoff_ae_user_id="ae-1",
        visibility="team",
    )

    assert result["handoff_ae_user_id"] == "ae-1"
    called_payload = supabase.table.return_value.update.call_args[0][0]
    assert called_payload["sales_role"] == "sdr"
    assert called_payload["handoff_ae_user_id"] == "ae-1"
    assert called_payload["visibility"] == "team"


def test_update_member_profile_can_clear_handoff():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    update_mock = supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    update_mock.return_value = MagicMock(data=[{"id": "m1", "handoff_ae_user_id": None}])

    svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
        handoff_ae_user_id=None,
    )
    called_payload = supabase.table.return_value.update.call_args[0][0]
    assert called_payload["handoff_ae_user_id"] is None


def test_update_member_profile_noop_when_nothing_provided():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    target = {"id": "m1", "user_id": "sdr-1", "role": "member"}
    svc._get_member_row = MagicMock(return_value=target)

    result = svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
    )
    assert result == target
    supabase.table.return_value.update.assert_not_called()


def test_create_invite_rejects_invalid_sales_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            svc.create_invite(
                company_id="company-1",
                email="new@acme.com",
                role="member",
                sales_role="closer",
            )
        )
    assert exc.value.status_code == 400


def test_accept_invite_copies_sales_role_to_membership():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_invite_by_token = MagicMock(
        return_value={
            "id": "invite-1",
            "company_id": "company-1",
            "email": "sdr@acme.com",
            "role": "member",
            "sales_role": "sdr",
        }
    )
    svc._email_exists_in_auth = MagicMock(return_value=None)

    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = MagicMock(user=MagicMock(id="new-user-1"))

    svc.accept_invite(
        raw_token="raw-token",
        password="a-long-password",
        full_name="New SDR",
        auth_client=auth_client,
    )

    insert_calls = supabase.table.return_value.insert.call_args_list
    member_insert = next(
        call.args[0] for call in insert_calls if call.args[0].get("role") == "member"
    )
    assert member_insert["sales_role"] == "sdr"
