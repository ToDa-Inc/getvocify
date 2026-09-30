"""T2 review fix: a Vocify call is pinned to the caller's flow (D5), read tolerantly
from company_members.sales_role, not just the single-published-playbook default."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-call-processor-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-call-processor-32b+")

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.telephony.call_processor import initiate_vocify_call_memo
from tests.playbooks.live_double import TablesWithLiveView


@pytest.fixture(autouse=True)
def _clear_flag_cache():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


class _Query:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: list[tuple[str, str]] = []
        self._op: tuple[str, dict | None] = ("select", None)

    def select(self, *_a, **_k):
        self._op = ("select", None)
        return self

    def insert(self, payload: dict):
        self._op = ("insert", payload)
        return self

    def update(self, payload: dict):
        self._op = ("update", payload)
        return self

    def eq(self, column: str, value):
        self._filters.append((column, value))
        return self

    def in_(self, column: str, values):
        wanted = {str(v) for v in values}
        self._filters.append((column, wanted))
        return self

    def limit(self, *_a, **_k):
        return self

    def _matches(self, row: dict) -> bool:
        return all(
            str(row.get(column)) in value if isinstance(value, set) else str(row.get(column)) == str(value)
            for column, value in self._filters
        )

    def execute(self):
        kind, payload = self._op
        if kind == "select":
            return type("R", (), {"data": [row for row in self._rows if self._matches(row)]})()
        if kind == "insert":
            row = {**payload}
            row.setdefault("id", f"row-{len(self._rows) + 1}")
            self._rows.append(row)
            return type("R", (), {"data": [row]})()
        if kind == "update":
            matched = [row for row in self._rows if self._matches(row)]
            for row in matched:
                row.update(payload)
            return type("R", (), {"data": matched})()
        raise AssertionError(kind)


class _Supabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = TablesWithLiveView({name: list(rows) for name, rows in tables.items()})

    def table(self, name: str):
        return _Query(self._tables.setdefault(name, []))


def _company(sales_role: str | None) -> dict:
    return {
        "company_members": [
            {
                "id": "m1",
                "company_id": "co-1",
                "user_id": "u1",
                "role": "member",
                "status": "active",
                "sales_role": sales_role,
                "handoff_ae_user_id": None,
                "visibility": "own",
            }
        ],
        "playbooks": [
            {"id": "pb-d", "company_id": "co-1", "sales_motion_key": "discovery", "active_version_id": "pv-d"},
            {"id": "pb-c", "company_id": "co-1", "sales_motion_key": "closing", "active_version_id": "pv-c"},
        ],
        "playbook_versions": [
            {"id": "pv-d", "playbook_id": "pb-d", "status": "published", "steps": [], "entries": []},
            {"id": "pv-c", "playbook_id": "pb-c", "status": "published", "steps": [], "entries": []},
        ],
        "outbound_calls": [{"carrier_call_id": "call-1", "user_id": "u1", "status": "recording"}],
        "company_feature_flags": [],
    }


def test_sdr_vocify_call_with_two_published_playbooks_is_pinned_to_discovery(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _Supabase(_company("sdr"))
    memo_id, created = asyncio.run(
        initiate_vocify_call_memo(
            supabase,
            {"user_id": "u1", "carrier_call_id": "call-1", "recording_duration": 12},
        )
    )
    assert created is True
    row = supabase._tables["memos"][0]
    assert row["sales_motion_key"] == "discovery"
    assert row["playbook_version_id"] == "pv-d"


def test_ae_vocify_call_is_pinned_to_closing(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _Supabase(_company("ae"))
    asyncio.run(
        initiate_vocify_call_memo(
            supabase,
            {"user_id": "u1", "carrier_call_id": "call-1", "recording_duration": 12},
        )
    )
    row = supabase._tables["memos"][0]
    assert row["sales_motion_key"] == "closing"
    assert row["playbook_version_id"] == "pv-c"


def test_flag_off_ignores_role_and_keeps_the_default_rule(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    supabase = _Supabase(_company("sdr"))
    asyncio.run(
        initiate_vocify_call_memo(
            supabase,
            {"user_id": "u1", "carrier_call_id": "call-1", "recording_duration": 12},
        )
    )
    row = supabase._tables["memos"][0]
    # Two motions published -> the pre-existing "single published playbook" default
    # does not apply either (it requires exactly one); nothing gets pinned.
    assert "sales_motion_key" not in row
