"""T4 (D8): the AE-readable handoff map, off by default and never a 500."""

from app.services import feature_flags
from app.services.handoff_visibility import (
    active_member_ids,
    handoff_reads_enabled,
    handoff_sdr_map_for_ae,
    handoff_sdr_map_for_viewer,
    sdr_ids_for_contact,
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

    def __init__(self):
        super().__init__('relation "deal_handoffs" does not exist')


class _Store:
    def __init__(self, tables=None, broken=()):
        self.tables_data = tables or {}
        self.broken = set(broken)

    def table(self, name):
        if name in self.broken:
            raise _MissingTableError()
        return _Query(self.tables_data.get(name, []))


def _flag_on(monkeypatch, value=True):
    feature_flags.clear_cache()
    monkeypatch.setattr(feature_flags, "is_enabled", lambda *_a, **_k: value)


def test_handoff_sdr_map_groups_multiple_sdrs_by_connection_and_contact():
    store = _Store(tables={"deal_handoffs": [
        {"company_id": "co-1", "connection_id": "conn-1", "contact_id": "c1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active"},
        {"company_id": "co-1", "connection_id": "conn-1", "contact_id": "c1", "sdr_user_id": "sdr-2", "ae_user_id": "ae-1", "status": "closed"},
        {"company_id": "co-1", "connection_id": "conn-1", "contact_id": "c2", "sdr_user_id": "sdr-3", "ae_user_id": "ae-1", "status": "cancelled"},
        {"company_id": "co-1", "connection_id": "conn-2", "contact_id": "c4", "sdr_user_id": "sdr-4", "ae_user_id": "ae-2", "status": "active"},
    ]})
    result = handoff_sdr_map_for_ae(store, company_id="co-1", ae_user_id="ae-1")
    assert result == {("conn-1", "c1"): {"sdr-1", "sdr-2"}}


def test_missing_table_returns_empty_not_raise():
    store = _Store(broken={"deal_handoffs"})
    assert handoff_sdr_map_for_ae(store, company_id="co-1", ae_user_id="ae-1") == {}


def test_any_other_error_also_returns_empty_not_raise():
    class _BrokenQuery:
        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def in_(self, *_a, **_k):
            return self

        def execute(self):
            raise RuntimeError("db timeout")

    class _BrokenStore:
        def table(self, _name):
            return _BrokenQuery()

    assert handoff_sdr_map_for_ae(_BrokenStore(), company_id="co-1", ae_user_id="ae-1") == {}


def test_handoff_reads_enabled_requires_company_id():
    assert handoff_reads_enabled(object(), None) is False


def test_handoff_sdr_map_for_viewer_empty_when_flag_off(monkeypatch):
    _flag_on(monkeypatch, False)
    store = _Store(tables={"deal_handoffs": [
        {"company_id": "co-1", "connection_id": "conn-1", "contact_id": "c1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active"},
    ]})
    assert handoff_sdr_map_for_viewer(store, company_id="co-1", viewer_id="ae-1") == {}


def test_handoff_sdr_map_for_viewer_reads_when_flag_on(monkeypatch):
    _flag_on(monkeypatch, True)
    store = _Store(tables={"deal_handoffs": [
        {"company_id": "co-1", "connection_id": "conn-1", "contact_id": "c1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active"},
    ]})
    assert handoff_sdr_map_for_viewer(store, company_id="co-1", viewer_id="ae-1") == {("conn-1", "c1"): {"sdr-1"}}


def test_sdr_ids_for_contact_with_connection_is_exact():
    handoff_map = {("conn-1", "c1"): {"sdr-1"}, ("conn-2", "c1"): {"sdr-9"}}
    assert sdr_ids_for_contact(handoff_map, "c1", connection_id="conn-1") == {"sdr-1"}
    assert sdr_ids_for_contact(handoff_map, "c1", connection_id="conn-3") == set()


def test_sdr_ids_for_contact_without_connection_unions_across_connections():
    handoff_map = {("conn-1", "c1"): {"sdr-1"}, ("conn-2", "c1"): {"sdr-9"}, (None, "c2"): {"sdr-2"}}
    assert sdr_ids_for_contact(handoff_map, "c1") == {"sdr-1", "sdr-9"}
    assert sdr_ids_for_contact(handoff_map, "c2") == {"sdr-2"}
    assert sdr_ids_for_contact(handoff_map, None) == set()


def test_active_member_ids_filters_removed_members():
    store = _Store(tables={"company_members": [
        {"company_id": "co-1", "user_id": "sdr-1", "status": "active"},
        {"company_id": "co-1", "user_id": "sdr-2", "status": "removed"},
    ]})
    assert active_member_ids(store, company_id="co-1", user_ids={"sdr-1", "sdr-2"}) == {"sdr-1"}


def test_active_member_ids_empty_inputs_short_circuit():
    assert active_member_ids(object(), company_id=None, user_ids={"sdr-1"}) == set()
    assert active_member_ids(object(), company_id="co-1", user_ids=set()) == set()
