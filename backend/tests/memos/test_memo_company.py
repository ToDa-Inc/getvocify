"""Every memo carries its author's company, whatever the capture path."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-company-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-company-32")

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import captures

APP = Path(__file__).resolve().parents[2] / "app"


class _Insert:
    def __init__(self, store):
        self._store = store

    def insert(self, row):
        self._store.inserted.append(dict(row))
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": "memo-1", **self._store.inserted[-1]}])


class _Store:
    def __init__(self):
        self.inserted: list[dict] = []

    def table(self, _name):
        return _Insert(self)


@pytest.fixture
def companies(monkeypatch):
    lookups: list[str] = []

    def lookup(_supabase, user_id):
        lookups.append(user_id)
        return {"user-a": "co-1"}.get(user_id)

    monkeypatch.setattr("app.services.company.get_company_id_for_user", lookup)
    return lookups


def test_a_memo_without_company_gets_its_authors(companies):
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "user-a", "status": "uploading"})
    assert store.inserted[0]["company_id"] == "co-1"


def test_an_explicit_company_is_kept_and_not_looked_up(companies):
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "user-a", "company_id": "co-9"})
    assert store.inserted[0]["company_id"] == "co-9"
    assert companies == []


def test_a_user_without_company_still_gets_a_memo(companies):
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "user-x"})
    assert store.inserted[0].get("company_id") is None


def test_a_failed_lookup_does_not_block_the_memo(monkeypatch):
    def broken(_supabase, _user_id):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.services.company.get_company_id_for_user", broken)
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "user-a"})
    assert store.inserted[0].get("company_id") is None


@pytest.mark.parametrize(
    "path",
    [
        "services/whatsapp/processor.py",
        "services/telephony/call_processor.py",
        "services/hubspot/call_processor.py",
    ],
)
def test_every_direct_memo_insert_goes_through_the_company_stamp(path):
    source = (APP / path).read_text()
    inserts = source.count('table("memos").insert(')
    assert inserts > 0
    assert source.count("with_author_company(") >= inserts
