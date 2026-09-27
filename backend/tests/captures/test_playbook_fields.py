"""Playbook pinning on memo insert matches desktop capture reserve."""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.captures import playbook_fields_for_capture


@pytest.fixture(autouse=True)
def _clear_flag_cache():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


class _Query:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: list[tuple[str, str]] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        rows = self._rows
        for column, value in self._filters:
            rows = [row for row in rows if str(row.get(column)) == str(value)]
        return type("R", (), {"data": rows})()


class _Supabase:
    def __init__(self, playbooks: list[dict], versions: list[dict], flags: list[dict] | None = None):
        self._playbooks = playbooks
        self._versions = versions
        self._flags = flags or []

    def table(self, name: str):
        if name == "playbooks":
            return _Query(self._playbooks)
        if name == "playbook_versions":
            return _Query(self._versions)
        if name == "company_feature_flags":
            return _Query(self._flags)
        raise AssertionError(name)


def test_single_published_playbook_pins_motion_and_version():
    supabase = _Supabase(
        playbooks=[{
            "id": "pb-1",
            "company_id": "co-1",
            "sales_motion_key": "outbound",
            "active_version_id": "pv-1",
        }],
        versions=[{"id": "pv-1", "playbook_id": "pb-1", "status": "published", "steps": [], "entries": []}],
    )
    fields = playbook_fields_for_capture(supabase, "co-1", default_when_unspecified=True)
    assert fields == {"sales_motion_key": "outbound", "playbook_version_id": "pv-1"}


def test_without_motion_or_default_flag_nothing_is_pinned():
    supabase = _Supabase(
        playbooks=[{
            "id": "pb-1",
            "company_id": "co-1",
            "sales_motion_key": "outbound",
            "active_version_id": "pv-1",
        }],
        versions=[{"id": "pv-1", "playbook_id": "pb-1", "status": "published", "steps": [], "entries": []}],
    )
    assert playbook_fields_for_capture(supabase, "co-1") == {}


def test_explicit_motion_uses_active_version():
    supabase = _Supabase(
        playbooks=[{
            "id": "pb-1",
            "company_id": "co-1",
            "sales_motion_key": "outbound",
            "active_version_id": "pv-2",
        }],
        versions=[{"id": "pv-2", "playbook_id": "pb-1", "status": "published", "steps": [], "entries": []}],
    )
    fields = playbook_fields_for_capture(supabase, "co-1", sales_motion_key="outbound")
    assert fields == {"sales_motion_key": "outbound", "playbook_version_id": "pv-2"}


def _sdr_ae_supabase(**flag_kwargs) -> _Supabase:
    """A company with both flows published: discovery pv-d, closing pv-c."""
    return _Supabase(
        playbooks=[
            {"id": "pb-d", "company_id": "co-1", "sales_motion_key": "discovery", "active_version_id": "pv-d"},
            {"id": "pb-c", "company_id": "co-1", "sales_motion_key": "closing", "active_version_id": "pv-c"},
        ],
        versions=[
            {"id": "pv-d", "playbook_id": "pb-d", "status": "published", "steps": [], "entries": []},
            {"id": "pv-c", "playbook_id": "pb-c", "status": "published", "steps": [], "entries": []},
        ],
        **flag_kwargs,
    )


def test_sdr_capture_is_pinned_to_discovery_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _sdr_ae_supabase()
    fields = playbook_fields_for_capture(supabase, "co-1", sales_role="sdr", interaction_kind="meeting")
    assert fields == {"sales_motion_key": "discovery", "playbook_version_id": "pv-d"}


def test_ae_capture_is_pinned_to_closing_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _sdr_ae_supabase()
    fields = playbook_fields_for_capture(supabase, "co-1", sales_role="ae", interaction_kind="call")
    assert fields == {"sales_motion_key": "closing", "playbook_version_id": "pv-c"}


def test_general_capture_follows_the_channel_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _sdr_ae_supabase()
    call = playbook_fields_for_capture(supabase, "co-1", sales_role="general", interaction_kind="call")
    meeting = playbook_fields_for_capture(supabase, "co-1", sales_role="general", interaction_kind="meeting")
    assert call == {"sales_motion_key": "discovery", "playbook_version_id": "pv-d"}
    assert meeting == {"sales_motion_key": "closing", "playbook_version_id": "pv-c"}


def test_explicit_motion_still_wins_over_the_role_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _sdr_ae_supabase()
    fields = playbook_fields_for_capture(
        supabase, "co-1", sales_motion_key="closing", sales_role="sdr", interaction_kind="call"
    )
    assert fields == {"sales_motion_key": "closing", "playbook_version_id": "pv-c"}


def test_role_based_motion_falls_back_to_the_single_published_rule_when_unpublished(monkeypatch):
    """The SDR's role points at discovery, but only closing is published: fall back (D2/D5)."""
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    supabase = _Supabase(
        playbooks=[{"id": "pb-c", "company_id": "co-1", "sales_motion_key": "closing", "active_version_id": "pv-c"}],
        versions=[{"id": "pv-c", "playbook_id": "pb-c", "status": "published", "steps": [], "entries": []}],
    )
    fields = playbook_fields_for_capture(
        supabase, "co-1", sales_role="sdr", interaction_kind="call", default_when_unspecified=True
    )
    assert fields == {"sales_motion_key": "closing", "playbook_version_id": "pv-c"}


def test_flag_off_ignores_the_role_and_behaves_as_before(monkeypatch):
    """SALES_ROLES_ENABLED off: an AE on a call still gets nothing pinned without an
    explicit motion, exactly like before this task."""
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    supabase = _sdr_ae_supabase()
    fields = playbook_fields_for_capture(supabase, "co-1", sales_role="ae", interaction_kind="call")
    assert fields == {}


def test_per_company_override_can_turn_the_role_selection_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    supabase = _sdr_ae_supabase(flags=[{"company_id": "co-1", "flag": "SALES_ROLES_ENABLED", "enabled": True}])
    fields = playbook_fields_for_capture(supabase, "co-1", sales_role="sdr", interaction_kind="call")
    assert fields == {"sales_motion_key": "discovery", "playbook_version_id": "pv-d"}
