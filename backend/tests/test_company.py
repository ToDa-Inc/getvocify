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


def test_a_missing_sales_role_column_is_not_a_missing_company_table():
    from postgrest.exceptions import APIError

    err = APIError(
        {
            "message": "Could not find the 'sales_role' column of 'company_members' in the schema cache",
            "code": "PGRST204",
            "details": None,
            "hint": None,
        }
    )
    assert _missing_company_schema(err) is False


def test_get_membership_reads_without_sales_role_when_the_column_is_missing():
    from postgrest.exceptions import APIError

    missing_col = APIError(
        {
            "message": "Could not find the 'sales_role' column of 'company_members' in the schema cache",
            "code": "PGRST204",
            "details": None,
            "hint": None,
        }
    )
    row = {
        "id": "m1",
        "company_id": "co-1",
        "user_id": "user-1",
        "role": "owner",
        "status": "active",
    }
    first = MagicMock()
    first.select.return_value.eq.return_value.limit.return_value.execute.side_effect = missing_col
    second = MagicMock()
    second.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[row])
    supabase = MagicMock()
    supabase.table.side_effect = [first, second]

    membership = CompanyService(supabase).get_membership("user-1")
    assert membership is not None
    assert membership.company_id == "co-1"
    assert membership.sales_role == "general"
    assert "sales_role" not in second.select.call_args.args[0]


def test_ensure_company_workspace_does_not_fail_when_the_member_already_exists():
    from postgrest.exceptions import APIError

    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_membership = MagicMock(return_value=None)
    svc.create_company_for_owner = MagicMock(
        side_effect=APIError(
            {
                "message": 'duplicate key value violates unique constraint "company_members_user_id_key"',
                "code": "23505",
                "details": "Key (user_id)=(user-1) already exists.",
                "hint": None,
            }
        )
    )

    svc.ensure_company_workspace("user-1", name="My workspace")
