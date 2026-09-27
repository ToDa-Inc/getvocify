"""Playbook pinning on memo insert matches desktop capture reserve."""

from __future__ import annotations

from app.services.captures import playbook_fields_for_capture


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
    def __init__(self, playbooks: list[dict], versions: list[dict]):
        self._playbooks = playbooks
        self._versions = versions

    def table(self, name: str):
        if name == "playbooks":
            return _Query(self._playbooks)
        if name == "playbook_versions":
            return _Query(self._versions)
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
