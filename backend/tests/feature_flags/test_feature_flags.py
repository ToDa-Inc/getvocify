import os

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import feature_flags  # noqa: E402
from app.services.feature_flags import is_enabled  # noqa: E402

FLAG = "INTELLIGENCE_EXTRACT_ENABLED"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        self.db.calls.append((self.table, dict(self.filters)))
        if self.db.error:
            raise self.db.error
        return _Result([
            row for row in self.db.rows
            if all(row.get(column) == value for column, value in self.filters.items())
        ])


class FakeSupabase:
    def __init__(self, rows=(), error=None):
        self.rows = list(rows)
        self.error = error
        self.calls = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def fresh_cache():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


@pytest.mark.parametrize("global_value", [True, False])
def test_override_on_wins_over_global(monkeypatch, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    db = FakeSupabase([{"company_id": "co-1", "flag": FLAG, "enabled": True}])
    assert is_enabled(db, "co-1", FLAG) is True


@pytest.mark.parametrize("global_value", [True, False])
def test_override_off_wins_over_global(monkeypatch, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    db = FakeSupabase([{"company_id": "co-1", "flag": FLAG, "enabled": False}])
    assert is_enabled(db, "co-1", FLAG) is False


@pytest.mark.parametrize("global_value", [True, False])
def test_no_override_uses_global(monkeypatch, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    db = FakeSupabase([
        {"company_id": "co-2", "flag": FLAG, "enabled": not global_value},
        {"company_id": "co-1", "flag": "FOLLOWUP_ENABLED", "enabled": not global_value},
    ])
    assert is_enabled(db, "co-1", FLAG) is global_value


@pytest.mark.parametrize("global_value", [True, False])
def test_lookup_error_uses_global_and_does_not_raise(monkeypatch, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    db = FakeSupabase(error=RuntimeError("supabase down"))
    assert is_enabled(db, "co-1", FLAG) is global_value


@pytest.mark.parametrize("company_id", [None, ""])
def test_no_company_uses_global_without_a_lookup(monkeypatch, company_id):
    monkeypatch.setattr(settings, FLAG, True)
    db = FakeSupabase([{"company_id": "co-1", "flag": FLAG, "enabled": False}])
    assert is_enabled(db, company_id, FLAG) is True
    assert db.calls == []


def test_one_lookup_per_company_within_a_minute(monkeypatch):
    monkeypatch.setattr(settings, FLAG, False)
    now = [1000.0]
    monkeypatch.setattr(feature_flags, "_now", lambda: now[0])
    db = FakeSupabase([{"company_id": "co-1", "flag": FLAG, "enabled": True}])
    assert is_enabled(db, "co-1", FLAG) is True
    db.rows = [{"company_id": "co-1", "flag": FLAG, "enabled": False}]
    now[0] += 59
    assert is_enabled(db, "co-1", FLAG) is True
    assert is_enabled(db, "co-1", "FOLLOWUP_ENABLED") is settings.FOLLOWUP_ENABLED
    assert len(db.calls) == 1
    now[0] += 2
    assert is_enabled(db, "co-1", FLAG) is False
    assert len(db.calls) == 2
    assert db.calls[0] == ("company_feature_flags", {"company_id": "co-1"})


def test_a_failed_lookup_is_not_cached(monkeypatch):
    monkeypatch.setattr(settings, FLAG, False)
    db = FakeSupabase([{"company_id": "co-1", "flag": FLAG, "enabled": True}], error=RuntimeError("blip"))
    assert is_enabled(db, "co-1", FLAG) is False
    db.error = None
    assert is_enabled(db, "co-1", FLAG) is True


def test_unknown_flag_without_override_is_off():
    assert is_enabled(FakeSupabase(), "co-1", "NOT_A_REAL_FLAG") is False
