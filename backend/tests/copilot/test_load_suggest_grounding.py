"""F12: suggest grounding from capture memo or a single company-published playbook."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from types import SimpleNamespace

from app.services.copilot.load_grounding import (
    load_company_suggest_grounding,
    load_suggest_grounding,
)

COMPANY = "co-1"
USER = "user-1"
CAPTURE = "memo-capture-1"


class _Chain:
    def __init__(self, table: "_FakeTable"):
        self._table = table
        self._filters: dict[str, str] = {}
        self._limit: int | None = None

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value: str):
        self._filters[column] = str(value)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self):
        rows = self._table.filter_rows(self._filters)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


class _FakeTable:
    def __init__(self, name: str, rows: list[dict]):
        self._name = name
        self._rows = rows

    def filter_rows(self, filters: dict[str, str]) -> list[dict]:
        out = []
        for row in self._rows:
            if all(str(row.get(k)) == v for k, v in filters.items()):
                out.append(dict(row))
        return out


class _FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, name: str):
        return _Chain(_FakeTable(name, self._tables.get(name, [])))


def _published_playbook(
    *,
    playbook_id: str,
    motion: str,
    version_id: str,
    company_id: str = COMPANY,
) -> tuple[dict, dict]:
    playbook = {
        "id": playbook_id,
        "company_id": company_id,
        "sales_motion_key": motion,
        "active_version_id": version_id,
    }
    version = {
        "id": version_id,
        "playbook_id": playbook_id,
        "status": "published",
        "steps": [{"step_id": "pain", "label": "Problema", "criterion": "Confirmado"}],
        "entries": [{"entry_id": "entry-1", "source_ref": "text:imp-1", "category": "price"}],
    }
    return playbook, version


def test_no_capture_and_one_published_playbook_returns_that_version_id():
    pb, ver = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-only")
    fake = _FakeSupabase(
        {
            "playbooks": [pb],
            "playbook_versions": [ver],
        }
    )
    grounding = load_company_suggest_grounding(
        fake,
        company_id=COMPANY,
        call_mode="meeting",
    )
    assert grounding is not None
    assert grounding.playbook_version_id == "pv-only"
    assert grounding.interaction_kind == "meeting"
    assert grounding.playbook_snapshot is not None
    assert grounding.playbook_snapshot["version_id"] == "pv-only"


def test_no_capture_and_two_published_playbooks_returns_none():
    pb1, ver1 = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-1")
    pb2, ver2 = _published_playbook(playbook_id="pb-2", motion="qualification", version_id="pv-2")
    fake = _FakeSupabase(
        {
            "playbooks": [pb1, pb2],
            "playbook_versions": [ver1, ver2],
        }
    )
    assert (
        load_company_suggest_grounding(
            fake,
            company_id=COMPANY,
            call_mode="speakerphone",
        )
        is None
    )


def test_capture_id_loads_memo_and_ignores_company_wide_shortcut():
    pb1, ver_active = _published_playbook(
        playbook_id="pb-1",
        motion="discovery",
        version_id="pv-company-1",
    )
    pb2, ver2 = _published_playbook(playbook_id="pb-2", motion="qualification", version_id="pv-company-2")
    ver_memo = {
        "id": "pv-memo",
        "playbook_id": "pb-1",
        "status": "published",
        "steps": ver_active["steps"],
        "entries": ver_active["entries"],
    }
    memo = {
        "id": CAPTURE,
        "user_id": USER,
        "company_id": COMPANY,
        "interaction_kind": "meeting",
        "playbook_version_id": "pv-memo",
        "sales_motion_key": "discovery",
        "extraction": {"intelligence": {"evidence": [{"id": "ev-memo"}]}},
    }
    fake = _FakeSupabase(
        {
            "memos": [memo],
            "playbooks": [pb1, pb2],
            "playbook_versions": [ver_active, ver_memo, ver2],
        }
    )
    grounding = load_suggest_grounding(
        fake,
        user_id=USER,
        company_id=COMPANY,
        capture_id=CAPTURE,
    )
    assert grounding is not None
    assert grounding.playbook_version_id == "pv-memo"
    assert grounding.evidence_ids == frozenset({"ev-memo"})
    assert grounding.playbook_snapshot is not None
    assert grounding.playbook_snapshot["version_id"] == "pv-memo"
