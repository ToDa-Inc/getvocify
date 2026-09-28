"""Tests for company workspace seat logic."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.company import CompanyService, _missing_company_schema, hash_token


def test_hash_token_deterministic():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("def")


def test_seat_usage_math():
    supabase = MagicMock()
    svc = CompanyService(supabase)

    svc.get_company = MagicMock(return_value={"seat_limit": 5})
    svc.count_active_members = MagicMock(return_value=2)
    svc.count_pending_invites = MagicMock(return_value=1)

    usage = svc.seat_usage("company-1")
    assert usage["seat_limit"] == 5
    assert usage["seats_active"] == 2
    assert usage["seats_pending"] == 1
    assert usage["seats_used"] == 3
    assert usage["seats_available"] == 2


def test_ensure_seat_available_raises_when_full():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.seat_usage = MagicMock(return_value={"seats_available": 0})

    with pytest.raises(HTTPException) as exc:
        svc.ensure_seat_available("company-1")
    assert exc.value.status_code == 409


def test_update_access_mode_rejects_unknown():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    with pytest.raises(HTTPException) as exc:
        svc.update_access_mode("company-1", "vip")
    assert exc.value.status_code == 400


def test_update_seat_limit_rejects_below_occupancy():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.seat_usage = MagicMock(return_value={"seats_used": 3})

    with pytest.raises(HTTPException) as exc:
        svc.update_seat_limit("company-1", 2)
    assert exc.value.status_code == 409


def test_get_membership_returns_none_when_schema_missing():
    from postgrest.exceptions import APIError

    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = APIError(
        {
            "message": "Could not find the table 'public.company_members' in the schema cache",
            "code": "PGRST205",
            "details": None,
            "hint": None,
        }
    )
    svc = CompanyService(supabase)
    assert svc.get_membership("user-1") is None


def test_admin_set_member_role_rejects_last_owner_demotion():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "role": "owner", "user_id": "u1"})
    svc.count_owners = MagicMock(return_value=1)

    with pytest.raises(HTTPException) as exc:
        svc.admin_set_member_role("c1", "m1", "admin")
    assert exc.value.status_code == 409


def test_missing_company_schema_detects_postgrest_error():
    from postgrest.exceptions import APIError

    err = APIError(
        {
            "message": "Could not find the table 'public.company_members' in the schema cache",
            "code": "PGRST205",
            "details": None,
            "hint": None,
        }
    )
    assert _missing_company_schema(err) is True


def test_update_member_sales_profile_rejects_unknown_role():
    svc = CompanyService(MagicMock())
    svc._get_member_row = MagicMock(return_value={"id": "m1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_sales_profile(company_id="c1", member_id="m1", sales_role="closer")
    assert exc.value.status_code == 400


def test_update_member_sales_profile_writes_role_and_clears_date():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "role": "member"})
    svc.update_member_sales_profile(
        company_id="c1", member_id="m1", sales_role="sdr", clear_started_on=True
    )
    patch = supabase.table.return_value.update.call_args.args[0]
    assert patch["sales_role"] == "sdr"
    assert patch["started_on"] is None


def test_list_members_falls_back_when_sales_columns_missing():
    from postgrest.exceptions import APIError

    supabase = MagicMock()
    select = supabase.table.return_value.select
    old_shape = MagicMock()
    old_shape.eq.return_value.order.return_value.execute.return_value.data = [
        {"id": "m1", "user_id": "u1", "role": "owner", "status": "active"}
    ]

    def fake_select(cols, *args, **kwargs):
        if "sales_role" in cols:
            raise APIError(
                {"message": "column company_members.sales_role does not exist", "code": "42703", "details": None, "hint": None}
            )
        return old_shape

    select.side_effect = fake_select
    svc = CompanyService(supabase)
    svc._auth_emails_by_ids = MagicMock(return_value={"u1": "a@x.com"})
    rows = svc._member_rows("c1")
    assert rows[0]["user_id"] == "u1"
