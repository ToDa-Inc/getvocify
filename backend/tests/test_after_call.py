"""Lista 4 T4 (E10, E11): what each after-call outcome means. Pure - services/after_call.py."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-after-call-32c")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-after-call-32c")

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.crm_config import CRMConfigurationRequest
from app.models.memo import ApproveMemoRequest, RecordOutcomeRequest
from app.services import after_call as ac

NOW = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
CONFIG = SimpleNamespace(on_hold_lead_status_value="IN_PROGRESS", lost_lead_status_value="UNQUALIFIED")
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _memo(intelligence=None, created_at="2026-09-28T09:00:00Z"):
    return {"id": "m1", "created_at": created_at, "extraction": {"intelligence": intelligence} if intelligence else {}}


# --- call_outcome_for ---------------------------------------------------------


@pytest.mark.parametrize(
    "rep_outcome,call_outcome",
    [
        ("meeting_booked", "converted"),
        ("follow_up", "on_hold"),
        ("not_interested", "lost"),
        ("disqualified", "lost"),
    ],
)
def test_every_rep_outcome_maps_to_a_call_outcome(rep_outcome, call_outcome):
    assert ac.call_outcome_for(rep_outcome) == call_outcome


def test_an_unknown_outcome_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        ac.call_outcome_for("maybe")


# --- deal rule matrix (E11) -------------------------------------------------------

ALLOWED = {
    "always": {"meeting_booked", "follow_up", "not_interested", "disqualified"},
    "meeting_booked": {"meeting_booked"},
    "follow_up_or_meeting": {"meeting_booked", "follow_up"},
    "never": set(),
}


@pytest.mark.parametrize("rule", list(ALLOWED))
@pytest.mark.parametrize("rep_outcome", list(ac.REP_OUTCOMES))
def test_deal_rule_matrix(rule, rep_outcome):
    allowed = rep_outcome in ALLOWED[rule]
    assert ac.deal_allowed(rule, rep_outcome) is allowed
    # Without a deal, the rule decides; an existing deal is always updated.
    assert ac.must_skip_deal(rule, rep_outcome, has_deal=False) is (not allowed)
    assert ac.must_skip_deal(rule, rep_outcome, has_deal=True) is False


def test_without_an_outcome_only_always_creates_a_deal():
    assert ac.deal_allowed("always", None) is True
    for rule in ("meeting_booked", "follow_up_or_meeting", "never"):
        assert ac.deal_allowed(rule, None) is False


def test_an_unknown_or_missing_rule_is_todays_behaviour():
    assert ac.normalize_rule(None) == "always"
    assert ac.normalize_rule("sometimes") == "always"
    assert ac.deal_allowed(None, "not_interested") is True


# --- suggested follow-up (E8) -------------------------------------------------------


def test_the_suggested_date_is_the_call_plus_its_stoppers_wait():
    memo = _memo({"interest": "medium", "objections": [{"category": "price", "state": "open", "quote": "caro"}]})
    assert ac.memo_stopper(memo, NOW) == "price"
    assert ac.suggested_followup_at(memo, {}, NOW) == datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)


def test_the_company_override_wins_over_the_default_wait():
    memo = _memo({"interest": "medium", "objections": [{"category": "timing", "state": "open"}]})
    assert ac.suggested_followup_at(memo, {"timing": 3}, NOW) == datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def test_an_unknown_stopper_comes_back_in_a_week():
    assert ac.memo_stopper(_memo(), NOW) is None
    assert ac.suggested_followup_at(_memo(), {}, NOW) == datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
    # interest "none" never comes back on its own, but the rep chose to follow up: a week.
    none = _memo({"interest": "none"})
    assert ac.suggested_followup_at(none, {}, NOW) == datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)


def test_an_old_call_counts_from_now_never_suggests_the_past():
    memo = _memo({"interest": "high"}, created_at="2026-09-01T09:00:00Z")
    assert ac.suggested_followup_at(memo, {}, NOW) == NOW + timedelta(days=2)


# --- proposed lead status -----------------------------------------------------------


def test_proposed_lead_status_uses_only_values_the_account_has():
    assert ac.proposed_lead_status("meeting_booked", None, CONFIG) == "OPEN_DEAL"
    assert ac.proposed_lead_status("follow_up", "timing", CONFIG) == "IN_PROGRESS"
    assert ac.proposed_lead_status("not_interested", None, CONFIG) == "UNQUALIFIED"
    assert ac.proposed_lead_status("disqualified", None, CONFIG) == "UNQUALIFIED"
    unmapped = SimpleNamespace(on_hold_lead_status_value=None, lost_lead_status_value="")
    assert ac.proposed_lead_status("follow_up", "timing", unmapped) is None
    assert ac.proposed_lead_status("disqualified", None, unmapped) is None
    assert ac.proposed_lead_status("follow_up", None, None) is None


# --- promised email ------------------------------------------------------------------


def test_an_email_commitment_the_rep_made_is_a_promised_email():
    assert ac.promised_email({"commitments": [{"kind": "email", "origin": "rep_promise", "text": "x"}]}) is True
    assert ac.promised_email({"commitments": [{"kind": "send", "origin": "rep_promise", "text": "deck"}]}) is True


def test_a_commitment_clearly_about_sending_info_counts_too():
    assert ac.promised_email({"commitments": [{"kind": "other", "origin": "rep_promise", "text": "Te envío la propuesta por correo"}]})
    assert ac.promised_email({"commitments": [{"kind": "other", "origin": "prospect_request", "text": "Send over the pricing"}]})


def test_calls_meetings_and_nothing_are_not_emails():
    assert ac.promised_email(None) is False
    assert ac.promised_email({}) is False
    assert ac.promised_email({"commitments": [{"kind": "call", "origin": "rep_promise", "text": "llamo el jueves"}]}) is False
    assert ac.promised_email({"commitments": [{"kind": "email", "origin": "prospect_request", "text": "x"}]}) is False
    assert ac.promised_email({"commitments": [{"kind": "meeting", "origin": "rep_promise", "text": "te mando la invitación"}]}) is False


# --- approval plan ---------------------------------------------------------------------


def _plan(**kwargs):
    base = dict(rep_outcome="follow_up", reason=None, lead_status=None, provider="hubspot",
                rule="always", has_deal=False, config=CONFIG)
    base.update(kwargs)
    return ac.approval_plan(**base)


def test_hubspot_gets_the_call_outcome_and_the_reason():
    assert _plan() == {"skip_deal": False, "call_outcome": "on_hold", "lost_reason": None}
    lost = _plan(rep_outcome="disqualified", reason=" Not a fit ")
    assert lost["call_outcome"] == "lost" and lost["lost_reason"] == "Not a fit"


@pytest.mark.parametrize("provider", ["pipedrive", "salesforce"])
def test_other_crms_never_get_a_call_outcome(provider):
    plan = _plan(provider=provider, rep_outcome="disqualified", reason="x")
    assert plan["call_outcome"] is None and plan["lost_reason"] is None


def test_the_deal_rule_forces_skip_deal_except_on_salesforce():
    assert _plan(rule="meeting_booked")["skip_deal"] is True
    assert _plan(rule="meeting_booked", provider="pipedrive")["skip_deal"] is True
    assert _plan(rule="meeting_booked", provider="salesforce")["skip_deal"] is False
    assert _plan(rule="meeting_booked", has_deal=True)["skip_deal"] is False
    assert _plan(rule="meeting_booked", rep_outcome="meeting_booked")["skip_deal"] is False


def test_an_edited_lead_status_is_honoured_only_from_the_mapped_values():
    assert _plan(lead_status="UNQUALIFIED")["on_hold_lead_status_value"] == "UNQUALIFIED"
    assert _plan(rep_outcome="not_interested", reason="x", lead_status="IN_PROGRESS")["lost_lead_status_value"] == "IN_PROGRESS"
    assert "on_hold_lead_status_value" not in _plan(lead_status="MADE_UP")
    assert "lost_lead_status_value" not in _plan(rep_outcome="meeting_booked", lead_status="UNQUALIFIED")


# --- request validation (422s) -----------------------------------------------------------


@pytest.mark.parametrize("rep_outcome", ["not_interested", "disqualified"])
def test_closing_a_contact_out_requires_a_reason(rep_outcome):
    with pytest.raises(ValidationError):
        ApproveMemoRequest(rep_outcome=rep_outcome)
    with pytest.raises(ValidationError):
        ApproveMemoRequest(rep_outcome=rep_outcome, disqualify_reason="  ")
    with pytest.raises(ValidationError):
        RecordOutcomeRequest(rep_outcome=rep_outcome)
    assert ApproveMemoRequest(rep_outcome=rep_outcome, disqualify_reason="No budget").rep_outcome == rep_outcome
    assert RecordOutcomeRequest(rep_outcome=rep_outcome, disqualify_reason="No budget").disqualify_reason == "No budget"


def test_booked_and_follow_up_need_no_reason_and_unknown_outcomes_are_rejected():
    assert ApproveMemoRequest(rep_outcome="meeting_booked").rep_outcome == "meeting_booked"
    assert ApproveMemoRequest(rep_outcome="follow_up").followup_at is None
    with pytest.raises(ValidationError):
        ApproveMemoRequest(rep_outcome="won")


def test_an_old_approve_body_is_unchanged():
    body = ApproveMemoRequest(deal_id="D1")
    assert body.rep_outcome is None and body.followup_at is None and body.disqualify_reason is None


# --- CRM configuration + migration 063 ------------------------------------------------------


def test_the_rule_is_optional_in_the_configuration_request_and_validated():
    base = dict(default_pipeline_id="p", default_pipeline_name="P", default_stage_id="s", default_stage_name="S")
    assert CRMConfigurationRequest(**base).deal_creation_rule is None
    assert CRMConfigurationRequest(**base, deal_creation_rule="never").deal_creation_rule == "never"
    with pytest.raises(ValidationError):
        CRMConfigurationRequest(**base, deal_creation_rule="sometimes")


def test_migration_063_adds_the_rule_with_its_check_and_a_rollback():
    up = (MIGRATIONS / "063_deal_creation_rule.sql").read_text()
    down = (MIGRATIONS / "063_deal_creation_rule.down.sql").read_text()
    assert "deal_creation_rule TEXT NOT NULL DEFAULT 'always'" in up
    assert "('always', 'meeting_booked', 'follow_up_or_meeting', 'never')" in up
    assert "DROP COLUMN IF EXISTS deal_creation_rule" in down


def test_the_after_call_flag_reaches_the_client_and_is_off_by_default():
    from app.config import settings
    from app.services.feature_flags import CLIENT_FLAGS

    assert "AFTER_CALL_FLOW_ENABLED" in CLIENT_FLAGS
    assert settings.AFTER_CALL_FLOW_ENABLED is False


def _saved_row(**extra):
    return {
        "id": "11111111-1111-1111-1111-111111111111", "connection_id": "22222222-2222-2222-2222-222222222222",
        "default_pipeline_id": "p", "default_pipeline_name": "P", "default_stage_id": "s", "default_stage_name": "S",
        "allowed_deal_fields": [], "allowed_contact_fields": [], "allowed_company_fields": [],
        "auto_create_contacts": True, "auto_create_companies": True, "created_at": "x", "updated_at": "y", **extra,
    }


@pytest.mark.parametrize("rule,written", [(None, False), ("meeting_booked", True)])
def test_saving_the_configuration_writes_the_rule_only_when_sent(monkeypatch, rule, written):
    import asyncio
    from unittest.mock import MagicMock

    from app.services import company as company_service
    from app.services.crm_config import CRMConfigurationService

    monkeypatch.setattr(company_service, "get_company_id_for_user", lambda *_a: "co-1")
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = SimpleNamespace(data={"id": "conn"})
    supabase.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(
        data=[_saved_row(**({"deal_creation_rule": rule} if rule else {}))]
    )
    body = CRMConfigurationRequest(
        default_pipeline_id="p", default_pipeline_name="P", default_stage_id="s", default_stage_name="S",
        deal_creation_rule=rule,
    )
    saved = asyncio.run(CRMConfigurationService(supabase).save_configuration("u-1", "conn", body))
    upserted = supabase.table.return_value.upsert.call_args[0][0]
    assert ("deal_creation_rule" in upserted) is written
    assert saved.deal_creation_rule == rule
