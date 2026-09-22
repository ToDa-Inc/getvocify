"""F12: meeting suggest SSE exposes playbook_ready and validated evidence_refs."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from app.services.copilot.grounding import SuggestGrounding, finalize_suggest_result

PLAYBOOK_SNAPSHOT = {
    "playbook_id": "pb-1",
    "version_id": "pv-2",
    "sales_motion_key": "discovery",
    "steps": [],
    "entries": [{"entry_id": "entry-2", "category": "price", "guidance": "Preguntar coste actual"}],
}


def _grounding(*, evidence_ids=("ev-1",)) -> SuggestGrounding:
    return SuggestGrounding(
        interaction_kind="meeting",
        playbook_version_id="pv-2",
        evidence_ids=frozenset(evidence_ids),
        playbook_snapshot=PLAYBOOK_SNAPSHOT,
    )


def test_grounded_meeting_result_carries_playbook_and_evidence():
    suggestion = {
        "is_objection": True,
        "objection_type": "price",
        "urgency": "medium",
        "say_this": "¿Qué coste tiene mantener el proceso actual?",
        "why_it_works": "Aísla presupuesto de valor.",
        "next_question": "",
        "dont_say": "",
        "evidence_refs": ["ev-1"],
        "source_id": "entry-2",
    }
    result = finalize_suggest_result(
        call_mode="meeting",
        suggestion=suggestion,
        grounding=_grounding(),
    )
    assert result["playbook_ready"] is True
    assert result["evidence_refs"] == ["ev-1"]
    assert result["playbook_version_id"] == "pv-2"
    assert result["grounded"] is True
    assert result["suggestion"]["say_this"].startswith("¿Qué coste")


def test_empty_evidence_stays_silent_without_advice_text():
    suggestion = {
        "is_objection": True,
        "objection_type": "price",
        "urgency": "medium",
        "say_this": "Pitch harder now.",
        "why_it_works": "Because.",
        "next_question": "Buy?",
        "dont_say": "Never",
        "evidence_refs": [],
    }
    result = finalize_suggest_result(
        call_mode="meeting",
        suggestion=suggestion,
        grounding=_grounding(),
    )
    assert result["playbook_ready"] is False
    assert result["evidence_refs"] == []
    assert result["suggestion"]["say_this"] == ""
    assert result["suggestion"]["why_it_works"] == ""


def test_invented_evidence_ref_is_not_published():
    suggestion = {
        "say_this": "Invented",
        "evidence_refs": ["ev-999"],
    }
    result = finalize_suggest_result(
        call_mode="meeting",
        suggestion=suggestion,
        grounding=_grounding(),
    )
    assert result["playbook_ready"] is False
    assert result["evidence_refs"] == []
    assert result["suggestion"]["say_this"] == ""


def test_non_meeting_mode_never_ships_live_assist_fields_as_ready():
    suggestion = {
        "say_this": "Cold call script",
        "evidence_refs": ["ev-1"],
    }
    result = finalize_suggest_result(
        call_mode="speakerphone",
        suggestion=suggestion,
        grounding=_grounding(),
    )
    assert result["playbook_ready"] is False
    assert result["evidence_refs"] == []
    assert result["suggestion"]["say_this"] == ""
