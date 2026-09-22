"""F04 ranking: pain before never-called, and an agreed meeting is not prospecting."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")

from app.services.hoy.priority import empty_priority_copy, rank_candidates

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def test_recent_pain_without_a_meeting_outranks_a_complete_never_called():
    ranked = rank_candidates(
        [
            {
                "connection_id": "crm-A",
                "contact_id": "1",
                "deal_id": "d1",
                "coverage": "complete",
                "last_call_at": None,
                "pain_confirmed": False,
            },
            {
                "connection_id": "crm-A",
                "contact_id": "42",
                "deal_id": "deal-7",
                "coverage": "complete",
                "pain_confirmed": True,
                "pain_at": "2026-09-20T10:00:00Z",
                "meeting_agreed": False,
                "evidence_refs": ["ev-1"],
            },
        ],
        NOW,
    )
    assert ranked[0]["id"] == "crm-A:42:deal-7"
    assert ranked[0]["tier"] == 1
    assert ranked[0]["reason"] == "Confirmó el problema; falta acordar el siguiente paso"
    assert ranked[1]["never_called"] is True


def test_agreed_meeting_is_not_a_prospecting_call_and_incomplete_history_is_not_never_called():
    ranked = rank_candidates(
        [
            {
                "connection_id": "crm-A",
                "contact_id": "9",
                "coverage": "complete",
                "meeting_agreed": True,
                "pain_confirmed": True,
                "pain_at": "2026-09-21T10:00:00Z",
            },
            {
                "connection_id": "crm-A",
                "contact_id": "8",
                "coverage": "partial",
                "last_call_at": None,
            },
        ],
        NOW,
    )
    assert all(row["contact_id"] != "9" for row in ranked)
    assert ranked[0]["never_called"] is False
    assert ranked[0]["reason"] == "Falta parte del historial"


def test_two_connections_and_a_closed_deal_stay_apart():
    ranked = rank_candidates(
        [
            {"connection_id": "crm-A", "contact_id": "42", "deal_id": "open", "coverage": "complete", "deal_status": "open", "last_call_at": "2026-09-01T00:00:00Z"},
            {"connection_id": "crm-B", "contact_id": "42", "deal_id": "open", "coverage": "complete", "deal_status": "open", "last_call_at": "2026-09-01T00:00:00Z"},
            {"connection_id": "crm-A", "contact_id": "42", "deal_id": "closed", "coverage": "complete", "deal_status": "closed", "last_call_at": None},
        ],
        NOW,
    )
    assert [row["id"] for row in ranked] == ["crm-A:42:open", "crm-B:42:open"]


def test_empty_states_are_distinct():
    assert empty_priority_copy(connected=False, coverage="complete")["title"] == "Conecta tu CRM"
    assert empty_priority_copy(connected=True, coverage="complete")["title"] == "No hay contactos prioritarios ahora"
    assert empty_priority_copy(connected=True, coverage="partial")["title"] == "Falta parte del historial"
