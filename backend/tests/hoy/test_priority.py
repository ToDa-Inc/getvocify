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


def test_a_future_agreed_call_is_shown_without_an_invite_to_call_sooner():
    ranked = rank_candidates(
        [{
            "connection_id": "crm-A",
            "contact_id": "3",
            "coverage": "complete",
            "scheduled_at": "2026-09-30T10:00:00Z",
            "pain_confirmed": True,
            "pain_at": "2026-09-20T10:00:00Z",
        }],
        NOW,
    )
    assert ranked[0]["next_action"] is None
    assert ranked[0]["reason"] == "Llamada acordada; no llamar antes"


def test_empty_states_are_distinct():
    disconnected = empty_priority_copy(connected=False, coverage="complete", role="member")
    assert disconnected["title"] == "Conecta tu CRM para ver a quién contactar"
    assert disconnected["action"] is None
    assert empty_priority_copy(connected=False, coverage="complete", role="owner")["action"] == "Conectar CRM"
    assert empty_priority_copy(connected=True, coverage="complete")["title"].startswith("No hay contactos prioritarios ahora")
    assert empty_priority_copy(connected=True, coverage="complete", provider="pipedrive")["contacts_url"] == "https://app.pipedrive.com/persons"
    assert empty_priority_copy(connected=True, coverage="complete", provider="hubspot")["contacts_url"] is None
    assert empty_priority_copy(connected=True, coverage="complete", provider="hubspot", portal_id="99")["contacts_url"] == "https://app.hubspot.com/contacts/99/objects/0-1"
    assert empty_priority_copy(connected=True, coverage="partial")["title"] == "Falta parte del historial"
    member = empty_priority_copy(connected=True, coverage="complete", role="member", assigned=False)
    assert member["action"] == "Revisa tu asignación con el administrador"
