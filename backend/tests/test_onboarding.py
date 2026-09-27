"""T9: Head of Sales onboarding wizard - the pure "which step is next" helper and the
CompanyService/API glue around onboarding_completed_at (migration 059)."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.company import CompanyService, Membership, _missing_onboarding_column
from app.services.onboarding import STEPS, next_onboarding_step


def _state(**done: bool) -> dict:
    state = {step: False for step in STEPS}
    state.update(done)
    return state


def test_next_onboarding_step_is_the_first_incomplete_one():
    assert next_onboarding_step(_state()) == "crm"
    assert next_onboarding_step(_state(crm=True)) == "team"
    assert next_onboarding_step(_state(crm=True, team=True)) == "handoff"
    assert next_onboarding_step(_state(crm=True, team=True, handoff=True)) == "playbooks"
    assert next_onboarding_step(_state(crm=True, team=True, handoff=True, playbooks=True)) == "strategy"


def test_next_onboarding_step_is_none_once_everything_is_done():
    assert next_onboarding_step(_state(**{s: True for s in STEPS})) is None


def test_next_onboarding_step_ignores_unknown_keys_and_missing_keys_count_as_pending():
    assert next_onboarding_step({"crm": True, "bogus": True}) == "team"
    assert next_onboarding_step({}) == STEPS[0]


def _membership(*, role="owner", company_id="company-1") -> Membership:
    return Membership(
        id="member-1",
        company_id=company_id,
        user_id="user-1",
        role=role,
        status="active",
    )


def test_needs_onboarding_false_without_the_flag():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.onboarding_wizard_enabled = MagicMock(return_value=False)
    svc.get_company = MagicMock(return_value={"onboarding_completed_at": None})
    assert svc.needs_onboarding(_membership()) is False


def test_needs_onboarding_false_for_a_member():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.onboarding_wizard_enabled = MagicMock(return_value=True)
    svc.get_company = MagicMock(return_value={"onboarding_completed_at": None})
    assert svc.needs_onboarding(_membership(role="member")) is False


def test_needs_onboarding_true_for_owner_when_not_completed():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.onboarding_wizard_enabled = MagicMock(return_value=True)
    svc.get_company = MagicMock(return_value={"onboarding_completed_at": None})
    assert svc.needs_onboarding(_membership()) is True


def test_needs_onboarding_false_before_migration_059_when_the_column_is_missing():
    """The row simply has no `onboarding_completed_at` key pre-migration - that must read as
    "nothing to ask for", not as "incomplete", or every company would be forced into the
    wizard the moment the flag flips on ahead of the migration running."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.onboarding_wizard_enabled = MagicMock(return_value=True)
    svc.get_company = MagicMock(return_value={"id": "company-1", "name": "Acme"})
    assert svc.needs_onboarding(_membership()) is False


def test_needs_onboarding_accepts_an_already_fetched_company_row():
    """company_summary_for_user and GET /company already have the row - passing it in skips
    a second get_company call."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.onboarding_wizard_enabled = MagicMock(return_value=True)
    svc.get_company = MagicMock(side_effect=AssertionError("should not re-fetch"))
    assert svc.needs_onboarding(_membership(), {"onboarding_completed_at": None}) is True
    assert svc.needs_onboarding(_membership(), {"onboarding_completed_at": "2026-09-27T00:00:00Z"}) is False
    assert svc.needs_onboarding(_membership(), {"id": "company-1"}) is False


def test_needs_onboarding_false_once_completed():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.onboarding_wizard_enabled = MagicMock(return_value=True)
    svc.get_company = MagicMock(return_value={"onboarding_completed_at": "2026-09-27T00:00:00Z"})
    assert svc.needs_onboarding(_membership()) is False


def test_complete_onboarding_writes_the_timestamp():
    supabase = MagicMock()
    supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "company-1", "onboarding_completed_at": "2026-09-27T00:00:00Z"}]
    )
    svc = CompanyService(supabase)
    row = svc.complete_onboarding("company-1")
    assert row["onboarding_completed_at"]
    written = supabase.table.return_value.update.call_args[0][0]
    assert "onboarding_completed_at" in written


def test_complete_onboarding_falls_back_before_migration_059():
    """Pre-migration behaviour, not a 500: swallow (log) and return the company as-is."""
    from postgrest.exceptions import APIError

    supabase = MagicMock()
    err = APIError(
        {
            "message": "column companies.onboarding_completed_at does not exist",
            "code": "42703",
            "details": None,
            "hint": None,
        }
    )
    supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = err
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={"id": "company-1", "name": "Acme"})
    row = svc.complete_onboarding("company-1")
    assert row == {"id": "company-1", "name": "Acme"}


def test_complete_onboarding_reraises_other_errors():
    supabase = MagicMock()
    supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("boom")
    svc = CompanyService(supabase)
    with pytest.raises(RuntimeError):
        svc.complete_onboarding("company-1")


def test_missing_onboarding_column_detects_the_42703():
    from postgrest.exceptions import APIError

    err = APIError(
        {
            "message": "column companies.onboarding_completed_at does not exist",
            "code": "42703",
            "details": None,
            "hint": None,
        }
    )
    assert _missing_onboarding_column(err) is True
    assert _missing_onboarding_column(RuntimeError("column companies.sales_strategy does not exist")) is False


def test_onboarding_state_reads_crm_team_and_strategy():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(
        return_value={"primary_crm_connection_id": "conn-1", "sales_strategy": "  Land and expand  "}
    )
    svc.count_active_members = MagicMock(return_value=2)
    svc.list_pending_invites = MagicMock(return_value=[])
    svc.list_members = MagicMock(
        return_value=[
            {"sales_role": "sdr", "handoff_ae_user_id": "ae-1"},
            {"sales_role": "ae", "handoff_ae_user_id": None},
        ]
    )
    state = svc.onboarding_state("company-1")
    assert state == {
        "crm": True,
        "team": True,
        "handoff": True,
        "playbooks": False,
        "strategy": True,
    }


def test_onboarding_state_handoff_pending_when_no_sdr_has_an_ae():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={})
    svc.count_active_members = MagicMock(return_value=1)
    svc.list_pending_invites = MagicMock(return_value=[])
    svc.list_members = MagicMock(
        return_value=[{"sales_role": "sdr", "handoff_ae_user_id": None}]
    )
    state = svc.onboarding_state("company-1")
    assert state["handoff"] is False
    assert state["team"] is False


def test_onboarding_state_handoff_done_without_any_sdr():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_company = MagicMock(return_value={})
    svc.count_active_members = MagicMock(return_value=1)
    svc.list_pending_invites = MagicMock(return_value=[])
    svc.list_members = MagicMock(return_value=[{"sales_role": "ae", "handoff_ae_user_id": None}])
    state = svc.onboarding_state("company-1")
    assert state["handoff"] is True


def test_require_manage_role_blocks_a_member_from_completing_onboarding():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_membership = MagicMock(return_value=_membership(role="member"))
    with pytest.raises(HTTPException) as exc:
        svc.require_manage_role("user-1")
    assert exc.value.status_code == 403
