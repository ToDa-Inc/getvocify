"""Tests for company workspace seat logic."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.company import CompanyService, _missing_company_schema, _missing_sales_strategy_column, hash_token


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


def test_update_sales_strategy_writes_the_trimmed_value():
    supabase = MagicMock()
    supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "company-1", "sales_strategy": "Land and expand"}]
    )
    svc = CompanyService(supabase)
    row = svc.update_sales_strategy("company-1", "  Land and expand  ")
    assert row["sales_strategy"] == "Land and expand"
    written = supabase.table.return_value.update.call_args[0][0]
    assert written["sales_strategy"] == "Land and expand"


def test_update_sales_strategy_blank_clears_it():
    supabase = MagicMock()
    supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    svc = CompanyService(supabase)
    svc.update_sales_strategy("company-1", "   ")
    written = supabase.table.return_value.update.call_args[0][0]
    assert written["sales_strategy"] is None


def test_update_sales_strategy_falls_back_before_migration_058():
    """D10/T8: before 058_sales_strategy.sql runs, the write is swallowed (logged) and the
    company row is returned as-is - pre-migration behaviour, not a 500."""
    from postgrest.exceptions import APIError

    supabase = MagicMock()
    err = APIError(
        {
            "message": "column companies.sales_strategy does not exist",
            "code": "42703",
            "details": None,
            "hint": None,
        }
    )
    supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = err
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={"id": "company-1", "name": "Acme"})
    row = svc.update_sales_strategy("company-1", "Land and expand")
    assert row == {"id": "company-1", "name": "Acme"}
    svc.get_company.assert_called_once_with("company-1")


def test_update_sales_strategy_reraises_other_errors():
    supabase = MagicMock()
    supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("boom")
    svc = CompanyService(supabase)
    with pytest.raises(RuntimeError):
        svc.update_sales_strategy("company-1", "Land and expand")


def test_missing_sales_strategy_column_detects_the_42703():
    from postgrest.exceptions import APIError

    err = APIError(
        {
            "message": "column companies.sales_strategy does not exist",
            "code": "42703",
            "details": None,
            "hint": None,
        }
    )
    assert _missing_sales_strategy_column(err) is True
    assert _missing_sales_strategy_column(RuntimeError("column company_members.sales_role does not exist")) is False
