from app.services.llm.lead_status import (
    decide_lead_bucket,
    extraction_has_lead_status,
    lead_status_bucket,
    option_for_bucket,
    strip_lead_status_for_unattended_sync,
)


def _portal_options():
    return {
        "name": "hs_lead_status",
        "label": "Lead Status",
        "object_type": "contacts",
        "options": [
            {"value": "NEW", "label": "New"},
            {"value": "OPEN", "label": "Open"},
            {"value": "IN_PROGRESS", "label": "In Progress"},
            {"value": "OPEN_DEAL", "label": "Open Deal"},
            {"value": "UNQUALIFIED", "label": "Unqualified"},
            {"value": "ATTEMPTED_TO_CONTACT", "label": "Attempted to Contact"},
            {"value": "CONNECTED", "label": "Connected"},
            {"value": "BAD_TIMING", "label": "Bad Timing"},
        ],
    }


def test_unavailable_is_attempted_and_rejection_is_disqualified():
    assert lead_status_bucket("ATTEMPTED_TO_CONTACT", "Attempted to Contact") == "attempted"
    assert lead_status_bucket("UNQUALIFIED", "Unqualified") == "disqualified"
    assert lead_status_bucket("DISQUALIFIED", "Disqualified") == "disqualified"
    assert lead_status_bucket("BAD_TIMING", "Bad Timing") == "bad_timing"
    assert lead_status_bucket("CONNECTED", "Connected") == "connected"
    assert lead_status_bucket("IN_PROGRESS", "In Progress") == "in_progress"
    assert lead_status_bucket("OPEN_DEAL", "Open Deal") == "open_deal"
    assert lead_status_bucket("NEW", "New") == "new"
    assert lead_status_bucket("OPEN", "Open") == "open"
    assert lead_status_bucket("NOT_INTERESTED", "Not interested") == "disqualified"
    assert option_for_bucket(
        {"options": [{"value": "NOT_INTERESTED", "label": "Not interested"}]},
        "disqualified",
    ) == "NOT_INTERESTED"


def test_not_available_is_attempted_and_never_disqualified():
    assert decide_lead_bucket(
        reach="no_live_conversation",
        reach_confidence=0.9,
        stance="unavailable",
        stance_confidence=0.88,
    ) == "attempted"
    assert decide_lead_bucket(
        reach="no_live_conversation",
        reach_confidence=0.91,
        stance="rejected",
        stance_confidence=0.93,
    ) == "attempted"
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.4,
        stance="unavailable",
        stance_confidence=0.8,
    ) == "attempted"


def test_explicit_rejection_on_a_live_call_is_disqualified_only_when_confident():
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.8,
        stance="rejected",
        stance_confidence=0.91,
    ) == "disqualified"
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.8,
        stance="rejected",
        stance_confidence=0.62,
    ) is None


def test_bad_timing_and_next_step_are_not_a_rejection_or_a_failed_dial():
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.7,
        stance="bad_timing",
        stance_confidence=0.8,
    ) == "bad_timing"
    assert decide_lead_bucket(
        reach="no_live_conversation",
        reach_confidence=0.8,
        stance="bad_timing",
        stance_confidence=0.77,
    ) == "bad_timing"
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.8,
        stance="next_step",
        stance_confidence=0.7,
    ) == "in_progress"
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.84,
        stance="meeting_booked",
        stance_confidence=0.9,
    ) == "open_deal"
    assert decide_lead_bucket(
        reach="live_conversation",
        reach_confidence=0.8,
        stance="open",
        stance_confidence=0.6,
    ) == "connected"


def test_option_mapping_never_uses_unqualified_for_a_missed_call():
    spec = _portal_options()
    assert option_for_bucket(spec, "attempted") == "ATTEMPTED_TO_CONTACT"
    assert option_for_bucket(spec, "disqualified") == "UNQUALIFIED"
    assert option_for_bucket(spec, "bad_timing") == "BAD_TIMING"
    assert option_for_bucket(spec, "open_deal") == "OPEN_DEAL"
    only_unqualified = {
        "options": [{"value": "UNQUALIFIED", "label": "Unqualified"}, {"value": "NEW", "label": "New"}],
    }
    assert option_for_bucket(only_unqualified, "attempted") is None
    assert option_for_bucket(only_unqualified, "bad_timing") is None
    assert option_for_bucket(only_unqualified, "new") is None


def test_unattended_sync_strips_lead_status_but_keeps_other_contact_fields():
    stored = {
        "summary": "No answer",
        "raw_extraction": {
            "contact_properties": {
                "hs_lead_status": "ATTEMPTED_TO_CONTACT",
                "jobtitle": "Ops",
            }
        },
    }
    stripped = strip_lead_status_for_unattended_sync(stored)
    assert "hs_lead_status" not in stripped["raw_extraction"]["contact_properties"]
    assert stripped["raw_extraction"]["contact_properties"]["jobtitle"] == "Ops"
    assert stored["raw_extraction"]["contact_properties"]["hs_lead_status"] == "ATTEMPTED_TO_CONTACT"
    assert extraction_has_lead_status(stored) is True
    assert extraction_has_lead_status(stripped) is False
