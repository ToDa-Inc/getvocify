"""Tests for company workspace seat logic."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.company import CompanyService, hash_token


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


def test_update_seat_limit_rejects_below_occupancy():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.seat_usage = MagicMock(return_value={"seats_used": 3})

    with pytest.raises(HTTPException) as exc:
        svc.update_seat_limit("company-1", 2)
    assert exc.value.status_code == 409
