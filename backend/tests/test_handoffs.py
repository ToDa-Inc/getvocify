"""T3: resolve_ae, create_handoff (idempotent), close_handoff, stage_ends_deal, and the
42P01/table-missing fallback (migration 056 not applied yet -> old behaviour, never a 500)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-handoffs-32c")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-handoffs-32c")

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.services.handoffs import (
    ACTIVE,
    HandoffError,
    active_handoffs_for_ae,
    active_handoffs_for_sdr,
    ae_membership_row,
    close_handoff,
    create_handoff,
    resolve_ae,
    resolve_owner_for_general,
    stage_ends_deal,
    valid_ae,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _MissingTableError(Exception):
    code = "42P01"
    message = 'relation "deal_handoffs" does not exist'

    def __init__(self):
        super().__init__(self.message)


class _UniqueViolationError(Exception):
    code = "23505"
    message = 'duplicate key value violates unique constraint "idx_deal_handoffs_active_unique"'

    def __init__(self):
        super().__init__(self.message)


class _Query:
    def __init__(self, store, table, *, missing=False, race=None):
        self._store = store
        self._table = table
        self._filters = []
        self._mode = "select"
        self._payload = None
        self._missing = missing
        self._race = race

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def execute(self):
        if self._missing:
            raise _MissingTableError()
        rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            if self._race is not None and self._race["armed"]:
                # Simulate another request's insert landing first, between our
                # "no active row yet" read and our own insert.
                self._race["armed"] = False
                rows.append(dict(self._race["winner"]))
                raise _UniqueViolationError()
            row = {"id": f"row-{len(rows) + 1}", **self._payload}
            rows.append(row)
            return _Result([row])
        if self._mode == "update":
            updated = []
            for row in rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
                    updated.append(dict(row))
            return _Result(updated)
        filtered = list(rows)
        for c, v in self._filters:
            filtered = [row for row in filtered if row.get(c) == v]
        return _Result(filtered)


class _Supabase:
    def __init__(self, *, missing_tables=(), race_winner=None):
        self.tables: dict[str, list] = {}
        self._missing_tables = set(missing_tables)
        self._race = {"armed": True, "winner": race_winner} if race_winner else None

    def table(self, name):
        race = self._race if name == "deal_handoffs" else None
        return _Query(self.tables, name, missing=name in self._missing_tables, race=race)


@dataclass
class _SdrMembership:
    handoff_ae_user_id: str | None = None


def test_resolve_ae_prefers_explicit_choice_over_the_routed_one():
    sdr = _SdrMembership(handoff_ae_user_id="ae-routed")
    assert resolve_ae(sdr, "ae-explicit") == "ae-explicit"


def test_resolve_ae_falls_back_to_the_routed_ae():
    sdr = _SdrMembership(handoff_ae_user_id="ae-routed")
    assert resolve_ae(sdr, None) == "ae-routed"


def test_resolve_ae_needs_ae_when_neither_is_set():
    sdr = _SdrMembership(handoff_ae_user_id=None)
    with pytest.raises(HandoffError) as exc:
        resolve_ae(sdr, None)
    assert exc.value.code == "needs_ae"


def test_resolve_ae_auto_picks_the_sole_active_ae_when_unrouted():
    supabase = _Supabase()
    supabase.tables["company_members"] = [
        {"user_id": "ae-1", "company_id": "co-1", "sales_role": "ae", "status": "active"},
        {"user_id": "sdr-1", "company_id": "co-1", "sales_role": "sdr", "status": "active"},
    ]
    sdr = _SdrMembership(handoff_ae_user_id=None)
    assert resolve_ae(sdr, None, supabase=supabase, company_id="co-1") == "ae-1"


def test_resolve_ae_still_needs_ae_with_two_active_aes():
    supabase = _Supabase()
    supabase.tables["company_members"] = [
        {"user_id": "ae-1", "company_id": "co-1", "sales_role": "ae", "status": "active"},
        {"user_id": "ae-2", "company_id": "co-1", "sales_role": "ae", "status": "active"},
    ]
    sdr = _SdrMembership(handoff_ae_user_id=None)
    with pytest.raises(HandoffError) as exc:
        resolve_ae(sdr, None, supabase=supabase, company_id="co-1")
    assert exc.value.code == "needs_ae"


def test_resolve_ae_still_needs_ae_with_zero_active_aes():
    supabase = _Supabase()
    supabase.tables["company_members"] = [
        {"user_id": "ae-1", "company_id": "co-1", "sales_role": "ae", "status": "removed"},
    ]
    sdr = _SdrMembership(handoff_ae_user_id=None)
    with pytest.raises(HandoffError) as exc:
        resolve_ae(sdr, None, supabase=supabase, company_id="co-1")
    assert exc.value.code == "needs_ae"


def test_resolve_ae_prefers_explicit_and_routed_over_auto_pick():
    supabase = _Supabase()
    supabase.tables["company_members"] = [
        {"user_id": "ae-1", "company_id": "co-1", "sales_role": "ae", "status": "active"},
    ]
    sdr = _SdrMembership(handoff_ae_user_id="ae-routed")
    assert resolve_ae(sdr, None, supabase=supabase, company_id="co-1") == "ae-routed"
    assert resolve_ae(sdr, "ae-explicit", supabase=supabase, company_id="co-1") == "ae-explicit"


def test_resolve_owner_for_general_is_none_without_a_route():
    general = _SdrMembership(handoff_ae_user_id=None)
    assert resolve_owner_for_general(general, None) is None
    assert resolve_owner_for_general(general, "ae-1") == "ae-1"


def test_valid_ae_accepts_ae_and_general_not_sdr():
    assert valid_ae({"status": "active", "sales_role": "ae"}) is True
    assert valid_ae({"status": "active", "sales_role": None}) is True
    assert valid_ae({"status": "active", "sales_role": "general"}) is True
    assert valid_ae({"status": "active", "sales_role": "sdr"}) is False
    assert valid_ae({"status": "removed", "sales_role": "ae"}) is False
    assert valid_ae(None) is False


def test_ae_membership_row_reads_by_user_id():
    supabase = _Supabase()
    supabase.tables["company_members"] = [
        {"user_id": "ae-1", "company_id": "co-1", "sales_role": "ae", "status": "active"},
    ]
    row = ae_membership_row(supabase, company_id="co-1", ae_user_id="ae-1")
    assert row["sales_role"] == "ae"
    assert ae_membership_row(supabase, company_id="co-1", ae_user_id="nope") is None


def test_create_handoff_is_idempotent_even_with_a_different_ae():
    supabase = _Supabase()
    first = create_handoff(
        supabase,
        company_id="co-1",
        connection_id="conn-1",
        contact_id="contact-1",
        sdr_user_id="sdr-1",
        ae_user_id="ae-1",
    )
    assert first["created"] is True
    assert first["status"] == ACTIVE

    replay = create_handoff(
        supabase,
        company_id="co-1",
        connection_id="conn-1",
        contact_id="contact-1",
        sdr_user_id="sdr-1",
        ae_user_id="ae-2",
    )
    assert replay["created"] is False
    assert replay["ae_user_id"] == "ae-1"
    assert len(supabase.tables["deal_handoffs"]) == 1


def test_create_handoff_survives_a_concurrent_insert_race():
    """Two requests both read 'no active row yet', then both insert: the loser's insert
    hits the partial unique index (23505) instead of racing past it, and re-selects the
    winner's row as a replay - never a 500, and never two active rows."""
    winner = {
        "id": "row-winner",
        "company_id": "co-1",
        "connection_id": "conn-1",
        "contact_id": "c1",
        "sdr_user_id": "sdr-1",
        "ae_user_id": "ae-winner",
        "status": ACTIVE,
    }
    supabase = _Supabase(race_winner=winner)
    result = create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c1",
        sdr_user_id="sdr-1", ae_user_id="ae-loser",
    )
    assert result["created"] is False
    assert result["ae_user_id"] == "ae-winner"
    assert len(supabase.tables["deal_handoffs"]) == 1


def test_create_handoff_opens_a_new_row_for_a_different_contact():
    supabase = _Supabase()
    create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c1",
        sdr_user_id="sdr-1", ae_user_id="ae-1",
    )
    create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c2",
        sdr_user_id="sdr-1", ae_user_id="ae-1",
    )
    assert len(supabase.tables["deal_handoffs"]) == 2


def test_create_handoff_falls_back_when_the_table_is_missing():
    supabase = _Supabase(missing_tables={"deal_handoffs"})
    result = create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c1",
        sdr_user_id="sdr-1", ae_user_id="ae-1",
    )
    assert result["skipped"] == "table_missing"
    assert result["created"] is False


def test_close_handoff_closes_the_active_row_and_is_a_noop_without_one():
    supabase = _Supabase()
    create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c1",
        sdr_user_id="sdr-1", ae_user_id="ae-1",
    )
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    closed = close_handoff(supabase, company_id="co-1", connection_id="conn-1", contact_id="c1", now=now)
    assert closed["status"] == "closed"
    assert closed["closed_at"] == now.isoformat()

    again = close_handoff(supabase, company_id="co-1", connection_id="conn-1", contact_id="c1", now=now)
    assert again is None


def test_close_handoff_cancelled_reason_sets_cancelled_status():
    supabase = _Supabase()
    create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c1",
        sdr_user_id="sdr-1", ae_user_id="ae-1",
    )
    closed = close_handoff(supabase, company_id="co-1", connection_id="conn-1", contact_id="c1", reason="cancelled")
    assert closed["status"] == "cancelled"


def test_close_handoff_falls_back_when_the_table_is_missing():
    supabase = _Supabase(missing_tables={"deal_handoffs"})
    assert close_handoff(supabase, company_id="co-1", connection_id="conn-1", contact_id="c1") is None


@pytest.mark.parametrize(
    "provider,kwargs,expected",
    [
        ("hubspot", {"stage_id": "closedwon"}, True),
        ("hubspot", {"stage_id": "closedlost"}, True),
        ("hubspot", {"stage_id": "appointmentscheduled"}, False),
        ("pipedrive", {"status": "won"}, True),
        ("pipedrive", {"status": "lost"}, True),
        ("pipedrive", {"status": "open"}, False),
        ("hubspot", {"stage_id": "qualified", "is_closed": True}, True),
        ("salesforce", {"stage_id": "closedwon"}, False),
    ],
)
def test_stage_ends_deal(provider, kwargs, expected):
    assert stage_ends_deal(provider, **kwargs) is expected


def test_active_handoffs_for_ae_and_sdr_and_missing_table_fallback():
    supabase = _Supabase()
    create_handoff(
        supabase, company_id="co-1", connection_id="conn-1", contact_id="c1",
        sdr_user_id="sdr-1", ae_user_id="ae-1",
    )
    assert len(active_handoffs_for_ae(supabase, company_id="co-1", ae_user_id="ae-1")) == 1
    assert len(active_handoffs_for_sdr(supabase, company_id="co-1", sdr_user_id="sdr-1")) == 1
    assert active_handoffs_for_ae(supabase, company_id="co-1", ae_user_id="ae-2") == []

    missing = _Supabase(missing_tables={"deal_handoffs"})
    assert active_handoffs_for_ae(missing, company_id="co-1", ae_user_id="ae-1") == []
    assert active_handoffs_for_sdr(missing, company_id="co-1", sdr_user_id="sdr-1") == []
