"""A step about booking the meeting is settled by the rep's declared outcome, not by a model."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from app.services.playbooks.outcome_steps import MEETING_BOOKED, status_from_rep_outcome, step_outcome
from app.services.playbooks.structured import normalize_steps


def test_meeting_steps_are_recognised_by_what_they_ask_for():
    assert step_outcome({"label": "Cerrar la meeting", "criterion": "El prospecto acepta día y hora"}) == MEETING_BOOKED
    assert step_outcome({"label": "Cierre", "criterion": "Agenda una reunión con el AE"}) == MEETING_BOOKED
    assert step_outcome({"label": "Book the demo", "criterion": "The prospect accepts a slot"}) == MEETING_BOOKED
    assert step_outcome({"label": "Apertura con motivo", "criterion": "Se presenta y da un motivo"}) is None
    assert step_outcome({"label": "Descubrir el pain", "criterion": "Pregunta por su reunión semanal de ventas"}) is None


def test_an_explicit_outcome_wins_and_an_unknown_one_is_ignored():
    assert step_outcome({"label": "Siguiente paso", "criterion": "x", "outcome": "meeting_booked"}) == MEETING_BOOKED
    assert step_outcome({"label": "Cerrar la meeting", "criterion": "acepta", "outcome": "invented"}) is None


def test_status_waits_for_the_rep():
    assert status_from_rep_outcome(MEETING_BOOKED, None) == "unknown"
    assert status_from_rep_outcome(MEETING_BOOKED, "meeting_booked") == "met"
    assert status_from_rep_outcome(MEETING_BOOKED, "not_interested") == "missed"


def test_normalize_steps_keeps_a_known_outcome_only():
    steps = normalize_steps([
        {"label": "Cerrar", "criterion": "x", "outcome": "meeting_booked"},
        {"label": "Abrir", "criterion": "y", "outcome": "nope"},
    ])
    assert steps[0]["outcome"] == "meeting_booked"
    assert "outcome" not in steps[1]
