"""Spoken follow-up timing resolved by code, so the CRM task date never depends on the model."""

import os
from datetime import date

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from app.services.relative_dates import resolve_schedule

CALL = date(2026, 9, 30)  # a Wednesday


@pytest.mark.parametrize("phrase, expected", [
    ("mañana", "2026-10-01"),
    ("mañana por la mañana", "2026-10-01"),
    ("por la mañana", None),
    ("pasado mañana", "2026-10-02"),
    ("hoy a las 12:30", "2026-09-30"),
    ("el viernes", "2026-10-02"),
    ("el lunes", "2026-10-05"),
    ("el miércoles", "2026-10-07"),
    ("a finales de semana", "2026-10-02"),
    ("dentro de 2 semanas", "2026-10-14"),
    ("en tres meses", "2026-12-30"),
    ("en un par de meses", "2026-11-30"),
    ("en un año", "2027-09-30"),
    ("en enero", "2027-01-01"),
    ("a finales de octubre", "2026-10-25"),
    ("a partir del 15 de enero", "2027-01-15"),
    ("el 9 de octubre", "2026-10-09"),
    ("más adelante", None),
    ("ahora", "2026-09-30"),
    ("en un rato", "2026-09-30"),
    ("el divendres", "2026-10-02"),
    ("dilluns", "2026-10-05"),
    ("demà", "2026-10-01"),
])
def test_spoken_timing(phrase, expected):
    assert resolve_schedule(phrase, CALL) == expected
