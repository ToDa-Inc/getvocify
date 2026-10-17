"""With the editable sales process on, a recording can be any type the person runs, whatever its channel; with it off
(or nothing assigned) everything works as it did."""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.playbooks import channel_types
from app.services.playbooks.type_classifier import reading_playbooks
from app.services.sales_process.members import assigned_for
from app.services.sales_process.store import InMemorySalesProcessStore, set_sales_process_store
from tests.reporting.fake_db import FakeDB

CO = "co-1"
RULE = {"role": "any", "channels": ["meeting"], "contact": "any", "deal_stages": []}
TYPES = {
    "cold": {"status": "published", "label": "Llamada en frío", "applies_to": None, "recognize": "Primer contacto."},
    "demo": {"status": "published", "label": "Demo", "applies_to": RULE, "recognize": None},
    "paused": {"status": "paused", "label": "Pausado", "applies_to": None, "recognize": None},
}


def fake_db():
    """A database where the company has the call reading on (the editable process rides on it)."""
    return FakeDB({"company_feature_flags": [{"company_id": CO, "flag": "INTELLIGENCE_CALL_READING_ENABLED", "enabled": True}]})


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(settings, "SALES_PROCESS_ENABLED", True)
    feature_flags.clear_cache()
    store = InMemorySalesProcessStore()
    set_sales_process_store(store)
    yield store
    feature_flags.clear_cache()
    set_sales_process_store(None)


def keys(db, kind, user_id=None):
    return channel_types.candidate_keys(db, CO, TYPES, kind, user_id=user_id)


def test_with_the_process_on_every_type_is_a_candidate_whatever_its_channel(_flags):
    db = fake_db()
    assert channel_types.enabled(db, CO)
    assert keys(db, "call") == ["cold", "demo"] and keys(db, "meeting") == ["cold", "demo"]
    assert keys(db, "voice_note") == []  # only calls and meetings have types


def test_what_a_person_runs_limits_their_candidates_and_nothing_assigned_means_all(_flags):
    db = fake_db()
    _flags.set_member_types(CO, ["demo"], user_id="u1")
    assert keys(db, "call", "u1") == ["demo"]
    assert keys(db, "call", "u2") == ["cold", "demo"]
    _flags.set_member_types(CO, ["paused"], user_id="u3")  # runs only what is switched off: better all than none
    assert keys(db, "call", "u3") == ["cold", "demo"]


def test_a_person_with_a_single_type_starts_every_recording_on_it(_flags, monkeypatch):
    db = fake_db()
    _flags.set_member_types(CO, ["cold"], user_id="u1")
    monkeypatch.setattr(channel_types, "_types", lambda company_id: TYPES)
    assert channel_types.resolve_at_capture(db, CO, kind="meeting", user_id="u1") == ("cold", "single")
    assert channel_types.resolve_at_capture(db, CO, kind="meeting", user_id="u2") == (None, None)


def test_the_call_reading_is_only_offered_the_types_the_person_runs(_flags, monkeypatch):
    db = fake_db()
    monkeypatch.setattr(channel_types, "_types", lambda company_id: TYPES)
    monkeypatch.setattr(channel_types, "live_snapshots", lambda supabase, company_id: [])
    _flags.set_member_types(CO, ["demo"], user_id="u1")
    assert set(reading_playbooks(CO, kind="call", supabase=db, user_id="u1")) == {"demo", "internal"}
    assert set(reading_playbooks(CO, kind="call", supabase=db)) == {"cold", "demo", "internal"}
    assert "Primer contacto." in reading_playbooks(CO, kind="call", supabase=db)["cold"]


def test_assigned_types_are_only_read_with_the_process_on(_flags, monkeypatch):
    _flags.set_member_types(CO, ["cold"], user_id="u1")
    db = fake_db()
    assert assigned_for(db, CO, "u1") == ["cold"] and assigned_for(db, CO, None) is None
    monkeypatch.setattr(settings, "SALES_PROCESS_ENABLED", False)
    feature_flags.clear_cache()
    assert assigned_for(db, CO, "u1") is None
    assert not channel_types.enabled(db, CO)


def test_without_the_process_a_meeting_only_type_is_not_a_call_candidate(monkeypatch):
    monkeypatch.setattr(settings, "SALES_PROCESS_ENABLED", False)
    monkeypatch.setattr(settings, "TYPE_BY_CHANNEL_ENABLED", True)
    feature_flags.clear_cache()
    assert keys(fake_db(), "call") == ["cold"] and keys(fake_db(), "meeting") == ["cold", "demo"]


def test_a_member_only_sees_the_types_they_run_in_the_playbook_list(_flags):
    from app.api.playbooks import _playbooks_payload
    from app.services.company import Membership
    from app.services.playbooks.repository import InMemoryPlaybookRepository

    step = {"step_id": "a", "label": "A", "criterion": "x"}
    repository = InMemoryPlaybookRepository()
    for key in ("cold", "demo"):
        repository.add_type(CO, key, key, label=key.title())
        repository.save_draft(CO, key, [step], [])
        repository.publish(CO, key)
    db = fake_db()
    member = Membership(id="m", company_id=CO, user_id="u1", role="member", status="active", sales_role=None)
    manager = Membership(id="m2", company_id=CO, user_id="u9", role="owner", status="active", sales_role=None)
    assert set(_playbooks_payload(db, member, repository)["motions"]) >= {"cold", "demo"}  # nothing assigned: all
    _flags.set_member_types(CO, ["demo"], user_id="u1")
    shown = _playbooks_payload(db, member, repository)
    assert set(shown["motions"]) == {"demo"} and set(shown["details"]) == {"demo"}
    assert {"cold", "demo"} <= set(_playbooks_payload(db, manager, repository)["motions"])
