"""A call never moves a contact's lead status back, and a salesperson's pause is not a missed contact."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-lead-status-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-lead-status-32")

from app.services.extraction_policy import drop_call_unsafe_props  # noqa: E402
from app.services.llm.lead_status import (  # noqa: E402
    REACH_CRITERIA,
    REACH_INSTRUCTIONS,
    STANCE_CRITERIA,
    is_lead_status_regression,
)


def test_attempted_after_a_later_stage_is_a_regression():
    for current in ("CONNECTED", "IN_PROGRESS", "OPEN_DEAL", "BAD_TIMING"):
        assert is_lead_status_regression("ATTEMPTED_TO_CONTACT", current)
    assert is_lead_status_regression("NEW", "ATTEMPTED_TO_CONTACT")


def test_forward_moves_and_disqualified_are_never_blocked():
    assert not is_lead_status_regression("ATTEMPTED_TO_CONTACT", "NEW")
    assert not is_lead_status_regression("OPEN_DEAL", "CONNECTED")
    assert not is_lead_status_regression("UNQUALIFIED", "OPEN_DEAL")
    assert not is_lead_status_regression("ATTEMPTED_TO_CONTACT", None)
    assert not is_lead_status_regression("SOMETHING_CUSTOM", "OPEN_DEAL")


def test_the_write_gate_drops_a_backward_lead_status_only():
    kept = drop_call_unsafe_props(
        {"hs_lead_status": "ATTEMPTED_TO_CONTACT", "jobtitle": "CEO"},
        existing_record=True,
        current={"hs_lead_status": "OPEN_DEAL"},
        object_type="contacts",
    )
    assert "hs_lead_status" not in kept and kept.get("jobtitle") == "CEO"
    forward = drop_call_unsafe_props(
        {"hs_lead_status": "CONNECTED"},
        existing_record=True,
        current={"hs_lead_status": "NEW"},
        object_type="contacts",
    )
    assert forward == {"hs_lead_status": "CONNECTED"}


def test_the_classifier_is_told_a_rep_pause_or_logistics_is_not_a_missed_contact():
    assert "salesperson" in REACH_INSTRUCTIONS and "not_stated" in REACH_INSTRUCTIONS
    assert "logistics" in REACH_CRITERIA["not_stated"]
    assert "salesperson" in STANCE_CRITERIA["unavailable"]
