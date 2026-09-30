"""The Python double of the SQL view `playbooks_live`, for the tests whose fake database has no views.

Seed the fake's `playbooks` table as always (a row with `active_version_id`, optionally `state` and `archived_at`) and
have its `table("playbooks_live")` return `live_view_rows(playbooks)`. test_live.py checks this double against the
real view on PostgreSQL, so the two cannot drift.
"""

from __future__ import annotations

from typing import Iterable


def live_view_rows(playbooks: Iterable[dict]) -> list[dict]:
    """[{playbook_id, company_id, sales_motion_key, version_id}] of the playbooks that apply to a call: a published
    version, switched on ('state' missing = on) and not deleted."""
    return [
        {
            "playbook_id": row.get("id"),
            "company_id": row.get("company_id"),
            "sales_motion_key": row.get("sales_motion_key"),
            "version_id": row.get("active_version_id"),
        }
        for row in playbooks
        if row.get("active_version_id") and (row.get("state") or "active") == "active" and not row.get("archived_at")
    ]


class TablesWithLiveView(dict):
    """A fake database's `tables` dict that also answers `playbooks_live`, derived from its `playbooks` rows at read
    time (so a test that changes `tables["playbooks"]` afterwards sees the change)."""

    def _derived(self) -> list[dict]:
        return live_view_rows(dict.get(self, "playbooks", []))

    def __getitem__(self, name):
        if name == "playbooks_live" and not dict.__contains__(self, name):
            return self._derived()
        return super().__getitem__(name)

    def get(self, name, default=None):
        if name == "playbooks_live" and not dict.__contains__(self, name):
            return self._derived()
        return super().get(name, default)

    def __contains__(self, name):
        return name == "playbooks_live" or super().__contains__(name)

    def setdefault(self, name, default=None):
        if name == "playbooks_live" and not dict.__contains__(self, name):
            return self._derived()
        return super().setdefault(name, default)
