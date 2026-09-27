"""T4 (D8): the AE-readable map of contact_id -> sdr_user_id, off by default."""

from app.services import feature_flags
from app.services.handoff_visibility import (
    handoff_reads_enabled,
    handoff_sdr_ids_for_ae,
    handoff_sdr_ids_for_viewer,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def execute(self):
        rows = list(self.rows)
        for op, column, value in self.filters:
            if op == "eq":
                rows = [r for r in rows if r.get(column) == value]
            elif op == "in":
                rows = [r for r in rows if r.get(column) in value]
        return _Result(rows)


class _MissingTableError(Exception):
    code = "42P01"
    message = 'relation "deal_handoffs" does not exist'

    def __init__(self):
        super().__init__(self.message)


class _Store:
    def __init__(self, rows=None, broken=False):
        self.rows = rows or []
        self.broken = broken

    def table(self, name):
        assert name == "deal_handoffs"
        if self.broken:
            raise _MissingTableError()
        return _Query(self.rows)


def _flag_on(monkeypatch, value=True):
    feature_flags.clear_cache()
    monkeypatch.setattr(feature_flags, "is_enabled", lambda *_a, **_k: value)


def test_handoff_sdr_ids_for_ae_maps_active_and_closed_only_for_this_ae():
    store = _Store(rows=[
        {"company_id": "co-1", "contact_id": "c1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active"},
        {"company_id": "co-1", "contact_id": "c2", "sdr_user_id": "sdr-2", "ae_user_id": "ae-1", "status": "closed"},
        {"company_id": "co-1", "contact_id": "c3", "sdr_user_id": "sdr-3", "ae_user_id": "ae-1", "status": "cancelled"},
        {"company_id": "co-1", "contact_id": "c4", "sdr_user_id": "sdr-4", "ae_user_id": "ae-2", "status": "active"},
    ])
    result = handoff_sdr_ids_for_ae(store, company_id="co-1", ae_user_id="ae-1")
    assert result == {"c1": "sdr-1", "c2": "sdr-2"}


def test_handoff_sdr_ids_for_ae_missing_table_returns_empty():
    store = _Store(broken=True)
    assert handoff_sdr_ids_for_ae(store, company_id="co-1", ae_user_id="ae-1") == {}


def test_handoff_reads_enabled_requires_company_id():
    assert handoff_reads_enabled(object(), None) is False


def test_handoff_sdr_ids_for_viewer_empty_when_flag_off(monkeypatch):
    _flag_on(monkeypatch, False)
    store = _Store(rows=[{"company_id": "co-1", "contact_id": "c1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active"}])
    assert handoff_sdr_ids_for_viewer(store, company_id="co-1", viewer_id="ae-1") == {}


def test_handoff_sdr_ids_for_viewer_reads_when_flag_on(monkeypatch):
    _flag_on(monkeypatch, True)
    store = _Store(rows=[{"company_id": "co-1", "contact_id": "c1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active"}])
    assert handoff_sdr_ids_for_viewer(store, company_id="co-1", viewer_id="ae-1") == {"c1": "sdr-1"}
