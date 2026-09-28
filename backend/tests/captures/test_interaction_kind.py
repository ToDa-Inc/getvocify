"""interaction_kind says the channel of every capture: call, meeting or visit."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-interaction-kind-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-interaction-kind-32")

from types import SimpleNamespace

import pytest

from app.services import captures
from app.services.captures import interaction_kind_for, interaction_kind_of


@pytest.mark.parametrize(
    ("source", "source_type", "expected"),
    [
        ("vocify_call", None, "call"),
        ("vocify_call", "meeting_transcript", "call"),
        ("hubspot_call", None, "call"),
        ("whatsapp", None, "visit"),
        (None, "voice_memo", "call"),
        ("web", "voice_memo", "call"),
        (None, "meeting_transcript", "meeting"),
        ("desktop", "meeting_transcript", "meeting"),
        (None, None, "call"),
    ],
)
def test_each_origin_maps_to_its_channel(source, source_type, expected):
    assert interaction_kind_for(source, source_type, None) == expected


def test_an_existing_valid_value_is_always_respected():
    assert interaction_kind_for("desktop", "voice_memo", "meeting") == "meeting"
    assert interaction_kind_for("whatsapp", None, "call") == "call"
    assert interaction_kind_for("vocify_call", None, "voice_note") == "voice_note"


def test_an_unknown_existing_value_falls_back_to_the_mapping():
    assert interaction_kind_for("whatsapp", None, "in_person") == "visit"
    assert interaction_kind_for("vocify_call", None, "  ") == "call"


def test_a_legacy_row_without_kind_is_classified_by_source():
    assert interaction_kind_of({"source": "whatsapp"}) == "visit"
    assert interaction_kind_of({"source": "hubspot_call", "interaction_kind": None}) == "call"
    assert interaction_kind_of({"source_type": "meeting_transcript"}) == "meeting"
    assert interaction_kind_of({"source": "desktop", "interaction_kind": "meeting"}) == "meeting"


class _Insert:
    def __init__(self, store):
        self._store = store

    def insert(self, row):
        self._store.inserted.append(dict(row))
        return self

    def select(self, *_a, **_k):
        return self

    def update(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if not self._store.inserted:
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[{"id": "memo-1", **self._store.inserted[-1]}])


class _Store:
    def __init__(self):
        self.inserted: list[dict] = []

    def table(self, _name):
        return _Insert(self)


@pytest.fixture(autouse=True)
def _no_company(monkeypatch):
    monkeypatch.setattr("app.services.company.get_company_id_for_user", lambda *_a: None)


def test_shared_insert_stamps_upload_and_extension_captures():
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "u1", "source_type": "voice_memo"})
    captures.insert_memo_row(store, {"user_id": "u1", "source_type": "meeting_transcript"})
    assert [row["interaction_kind"] for row in store.inserted] == ["call", "meeting"]


def test_shared_insert_keeps_the_desktop_value():
    store = _Store()
    captures.insert_memo_row(
        store, {"user_id": "u1", "source": "desktop", "source_type": "voice_memo", "interaction_kind": "visit"}
    )
    assert store.inserted[0]["interaction_kind"] == "visit"


async def test_dialer_insert_stamps_call():
    from app.services.telephony.call_processor import initiate_vocify_call_memo

    store = _Store()
    await initiate_vocify_call_memo(store, {"user_id": "u1", "recording_duration": 3, "carrier_call_id": "c1"})
    assert store.inserted[0]["interaction_kind"] == "call"


async def test_hubspot_call_insert_stamps_call(monkeypatch):
    from app.services.hubspot import call_processor

    async def associations(_client, _cid):
        return [], []

    monkeypatch.setattr(call_processor, "get_call_associations", associations)
    monkeypatch.setattr(call_processor, "HubSpotClient", lambda *_a, **_k: object())

    store = _Store()
    await call_processor.initiate_hubspot_call_memo(store, "u1", "call-1", "token")
    assert store.inserted[0]["interaction_kind"] == "call"
