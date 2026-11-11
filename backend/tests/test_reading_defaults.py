"""The reading of a call after it ends is on for every company: a new company's Equipo and Coaching are built from it, and
they stayed empty while it was switched on by hand per company (Movertis, 11 Nov 2026)."""

from app.config import Settings
from app.services import feature_flags
from tests.conftest import READING_FLAGS


def test_the_reading_is_on_by_default_for_every_company():
    for flag in READING_FLAGS:
        assert Settings.model_fields[flag].default is True, flag


def test_a_company_without_a_row_gets_the_default_and_a_row_still_switches_it_off(monkeypatch):
    from app.config import settings

    class Table:
        def __init__(self, rows):
            self.rows = rows

        def select(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def execute(self):
            return type("R", (), {"data": self.rows})()

    class Supabase:
        def __init__(self, rows):
            self.rows = rows

        def table(self, _name):
            return Table(self.rows)

    for flag in READING_FLAGS:
        monkeypatch.setattr(settings, flag, Settings.model_fields[flag].default)
    feature_flags.clear_cache()
    assert all(feature_flags.is_enabled(Supabase([]), "new-company", flag) for flag in READING_FLAGS)
    feature_flags.clear_cache()
    off = Supabase([{"flag": "INTELLIGENCE_EXTRACT_ENABLED", "enabled": False}])
    assert feature_flags.is_enabled(off, "switched-off", "INTELLIGENCE_EXTRACT_ENABLED") is False
    feature_flags.clear_cache()
