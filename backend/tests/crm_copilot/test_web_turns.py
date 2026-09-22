"""Ask turns stay idempotent, and a changed contact does not receive the old write."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

import pytest

from app.services.crm_copilot.web_sessions import (
    TurnConflict,
    UncertainOperation,
    accept_turn,
    confirm_operation,
)


def test_repeating_a_client_turn_returns_the_same_turn():
    store = {}
    first = accept_turn(store, conversation_id="conv-1", client_turn_id="web-2", text="¿Qué sigue?")
    second = accept_turn(store, conversation_id="conv-1", client_turn_id="web-2", text="otra pregunta")
    assert first["turn_id"] == second["turn_id"]
    assert first["status"] == "pending"
    assert second["replayed"] is True
    assert second["text"] == "¿Qué sigue?"
    assert len(store) == 1


def test_changing_contact_before_confirm_writes_nothing():
    operation = {
        "operation_id": "op-1",
        "revision": 3,
        "contact_id": "contact-a",
        "applied": False,
        "status": "proposed",
    }
    with pytest.raises(TurnConflict):
        confirm_operation(operation, operation_id="op-1", revision=3, contact_id="contact-b")
    assert operation["applied"] is False


def test_an_uncertain_remote_result_is_not_retried_blindly():
    operation = {
        "operation_id": "op-1",
        "revision": 3,
        "contact_id": "contact-a",
        "applied": False,
        "status": "uncertain",
    }
    with pytest.raises(UncertainOperation):
        confirm_operation(operation, operation_id="op-1", revision=3, contact_id="contact-a")
    assert operation["applied"] is False
