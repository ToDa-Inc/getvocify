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


def test_callback_after_days_reads_the_company_column():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={"id": "company-1", "callback_after_days": 5})
    assert svc.callback_after_days("company-1") == 5


def test_callback_after_days_falls_back_before_migration_057():
    """Before 057_callback_after_days.sql runs, the row simply lacks the column (get_company
    reads select("*"), so no 42703 is even raised) - the default of 2 applies."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={"id": "company-1"})
    assert svc.callback_after_days("company-1") == 2


def test_callback_after_days_falls_back_when_the_company_read_fails():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(side_effect=RuntimeError("boom"))
    assert svc.callback_after_days("company-1") == 2


# --- callback_after_days (T5 setting, Lista 3 fix: it had no way to be changed) ---


def test_update_callback_after_days_writes_the_value():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.update_callback_after_days("company-1", 5)
    written = supabase.table.return_value.update.call_args[0][0]
    assert written["callback_after_days"] == 5


def test_update_callback_after_days_never_raises_before_migration_057():
    supabase = MagicMock()
    supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("42703")
    CompanyService(supabase).update_callback_after_days("company-1", 5)


def test_callback_after_days_request_is_bounded():
    from pydantic import ValidationError

    from app.api.company import UpdateCompanyRequest

    assert UpdateCompanyRequest(callback_after_days=5).callback_after_days == 5
    for bad in (0, 31, -1):
        with pytest.raises(ValidationError):
            UpdateCompanyRequest(callback_after_days=bad)


@pytest.mark.parametrize("flag_on,expected_calls", [(True, 1), (False, 0)])
def test_patch_company_only_saves_callback_days_with_lead_tiers_on(flag_on, expected_calls):
    import asyncio

    from app.api import company as company_api

    svc = MagicMock()
    svc.require_manage_role.return_value = MagicMock(company_id="company-1")
    svc.lead_tiers_enabled.return_value = flag_on
    svc.sales_strategy_enabled.return_value = False
    with (
        patch.object(company_api, "CompanyService", return_value=svc),
        patch.object(company_api, "get_company", new=MagicMock(return_value=asyncio.sleep(0, result={}))),
    ):
        asyncio.run(company_api.update_company(
            company_api.UpdateCompanyRequest(callback_after_days=4), user_id="u1", supabase=MagicMock(),
        ))
    assert svc.update_callback_after_days.call_count == expected_calls


# --- followup_cadence (Lista 4 T2, E8: companies.followup_cadence, migration 062) ---


def test_followup_cadence_reads_only_valid_overrides():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={"id": "company-1", "followup_cadence": {"price": 3, "timing": 0, "x": 4}})
    assert svc.followup_cadence("company-1") == {"price": 3}


def test_followup_cadence_is_empty_before_migration_062_or_when_the_read_fails():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={"id": "company-1"})
    assert svc.followup_cadence("company-1") == {}
    svc.get_company = MagicMock(side_effect=RuntimeError("boom"))
    assert svc.followup_cadence("company-1") == {}


def test_the_sdr_sections_flag_reaches_the_client():
    from app.services.feature_flags import CLIENT_FLAGS

    assert "HOY_SDR_SECTIONS_ENABLED" in CLIENT_FLAGS
    assert "HOY_LEAD_TIERS_ENABLED" in CLIENT_FLAGS


def test_the_brief_company_hook_flag_reaches_the_client():
    from app.config import settings
    from app.services.feature_flags import CLIENT_FLAGS

    assert "BRIEF_COMPANY_HOOK_ENABLED" in CLIENT_FLAGS
    assert settings.BRIEF_COMPANY_HOOK_ENABLED is False


class _InviteChain:
    """Any query method returns self; execute() serves rows and can reject sales_role."""

    def __init__(self, rows, *, reject_sales_role=False):
        self.rows = rows
        self.reject_sales_role = reject_sales_role
        self.selects: list[str] = []
        self.updates: list[dict] = []
        self._cols = ""
        self._updated = False

    def table(self, _name):
        return self

    def select(self, cols):
        self._cols = cols
        self.selects.append(cols)
        return self

    def update(self, values):
        self.updates.append(values)
        self._updated = True
        return self

    def single(self):
        return self

    def __getattr__(self, _name):
        return lambda *args, **kwargs: self

    def execute(self):
        if self.reject_sales_role and "sales_role" in self._cols:
            raise Exception("42703 column company_invitations.sales_role does not exist")
        result = MagicMock()
        result.data = [self.rows] if self._updated and isinstance(self.rows, dict) else self.rows
        self._updated = False
        return result


_INVITE_ROW = {
    "id": "inv-1",
    "email": "a@b.co",
    "role": "member",
    "expires_at": "2099-01-01T00:00:00Z",
    "created_at": "2026-01-01T00:00:00Z",
    "invited_by": None,
    "sales_role": "sdr",
}


def test_list_pending_invites_returns_sales_role():
    chain = _InviteChain([dict(_INVITE_ROW)])
    invites = CompanyService(chain).list_pending_invites("company-1")
    assert invites[0]["sales_role"] == "sdr"
    assert "sales_role" in chain.selects[0]


def test_list_pending_invites_tolerates_missing_sales_role_column():
    row = {k: v for k, v in _INVITE_ROW.items() if k != "sales_role"}
    chain = _InviteChain([row], reject_sales_role=True)
    invites = CompanyService(chain).list_pending_invites("company-1")
    assert invites[0]["email"] == "a@b.co"
    assert invites[0]["sales_role"] is None
    assert len(chain.selects) == 2


@pytest.mark.asyncio
async def test_resend_invite_keeps_sales_role():
    chain = _InviteChain(dict(_INVITE_ROW))
    svc = CompanyService(chain)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)
        return True

    svc._send_invite_email = fake_send
    invite, _url, _sent = await svc.resend_invite("inv-1", "company-1")
    assert invite["sales_role"] == "sdr"
    assert sent["sales_role"] == "sdr"
