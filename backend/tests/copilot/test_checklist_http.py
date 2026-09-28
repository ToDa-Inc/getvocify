"""F12: POST /copilot/checklist marks steps only from stored playbook observations."""

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.copilot.checklist import checklist_from_grounding
from app.services.copilot.grounding import SuggestGrounding

COMPANY = "co-1"
USER = "user-1"
OTHER_USER = "user-2"
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
    steps: list[dict] | None = None,
) -> tuple[dict, dict]:
    playbook = {
        "id": playbook_id,
        "company_id": COMPANY,
        "sales_motion_key": motion,
        "active_version_id": version_id,
    }
    version = {
        "id": version_id,
        "playbook_id": playbook_id,
        "status": "published",
        "steps": steps
        or [
            {"step_id": "pain", "label": "Problema", "criterion": "Confirmado"},
            {"step_id": "budget", "label": "Presupuesto", "criterion": "Explorado"},
        ],
        "entries": [{"entry_id": "entry-1", "source_ref": "text:imp-1", "category": "price"}],
    }
    return playbook, version


def _client(fake: _FakeSupabase) -> TestClient:
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_supabase] = lambda: fake
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m",
        company_id=COMPANY,
        user_id=USER,
        role="member",
        status="active",
    )
    return TestClient(app)


def test_speakerphone_returns_empty_checklist():
    pb, ver = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-1")
    client = _client(_FakeSupabase({"playbooks": [pb], "playbook_versions": [ver]}))
    got = client.post("/api/v1/copilot/checklist", json={"call_mode": "speakerphone"})
    assert got.status_code == 200
    assert got.json() == {
        "playbook_version_id": None,
        "observed": 0,
        "applicable": 0,
        "steps": [],
    }


def test_one_published_playbook_without_capture_lists_pending_steps():
    pb, ver = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-only")
    client = _client(_FakeSupabase({"playbooks": [pb], "playbook_versions": [ver]}))
    got = client.post("/api/v1/copilot/checklist", json={"call_mode": "meeting"})
    body = got.json()
    assert body["playbook_version_id"] == "pv-only"
    assert body["applicable"] == 2
    assert body["observed"] == 0
    assert len(body["steps"]) == 2
    assert all(step["status"] == "pending" and step["evidence_refs"] == [] for step in body["steps"])


def test_two_playbooks_without_capture_is_not_a_finished_checklist():
    pb1, ver1 = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-1")
    pb2, ver2 = _published_playbook(playbook_id="pb-2", motion="qualification", version_id="pv-2")
    client = _client(_FakeSupabase({"playbooks": [pb1, pb2], "playbook_versions": [ver1, ver2]}))
    got = client.post("/api/v1/copilot/checklist", json={"call_mode": "meeting"})
    assert got.json()["steps"] == []
    assert got.json()["observed"] == 0
    assert got.json()["applicable"] == 0


def test_capture_marks_met_only_with_stored_observations_and_evidence():
    pb, ver = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-memo")
    memo = {
        "id": CAPTURE,
        "user_id": USER,
        "company_id": COMPANY,
        "interaction_kind": "meeting",
        "playbook_version_id": "pv-memo",
        "sales_motion_key": "discovery",
        "extraction": {
            "intelligence": {
                "playbook_observations": [
                    {
                        "step_id": "pain",
                        "status": "met",
                        "evidence_refs": ["ev-pain"],
                        "origin": "live",
                    },
                    {
                        "step_id": "budget",
                        "status": "missed",
                        "evidence_refs": ["ev-budget"],
                        "origin": "live",
                    },
                ]
            }
        },
    }
    client = _client(
        _FakeSupabase(
            {
                "memos": [memo],
                "playbooks": [pb],
                "playbook_versions": [ver],
            }
        )
    )
    got = client.post(
        "/api/v1/copilot/checklist",
        json={
            "call_mode": "meeting",
            "capture_id": CAPTURE,
            "elapsed_seconds": 600,
            "finalized_turns": [{"text": "fake keyword budget", "speaker": "prospect"}],
        },
    )
    body = got.json()
    assert body["observed"] == 1
    assert body["applicable"] == 2
    pain = next(s for s in body["steps"] if s["step_id"] == "pain")
    budget = next(s for s in body["steps"] if s["step_id"] == "budget")
    assert pain == {
        "step_id": "pain",
        "label": "Problema",
        "status": "met",
        "evidence_refs": ["ev-pain"],
    }
    assert budget["status"] == "pending"
    assert budget["evidence_refs"] == []


def test_foreign_capture_returns_404():
    pb, ver = _published_playbook(playbook_id="pb-1", motion="discovery", version_id="pv-memo")
    memo = {
        "id": CAPTURE,
        "user_id": OTHER_USER,
        "company_id": COMPANY,
        "interaction_kind": "meeting",
        "playbook_version_id": "pv-memo",
        "sales_motion_key": "discovery",
        "extraction": {},
    }
    client = _client(
        _FakeSupabase({"memos": [memo], "playbooks": [pb], "playbook_versions": [ver]})
    )
    got = client.post(
        "/api/v1/copilot/checklist",
        json={"call_mode": "meeting", "capture_id": CAPTURE},
    )
    assert got.status_code == 404


def test_met_without_evidence_refs_stays_pending():
    snapshot = {
        "playbook_id": "pb-1",
        "version_id": "pv-1",
        "steps": [{"step_id": "pain", "label": "Problema"}],
        "entries": [],
    }
    grounding = SuggestGrounding(
        interaction_kind="meeting",
        playbook_version_id="pv-1",
        evidence_ids=frozenset(),
        playbook_snapshot=snapshot,
    )
    body = checklist_from_grounding(
        grounding,
        extraction={
            "intelligence": {
                "playbook_observations": [{"step_id": "pain", "status": "met", "evidence_refs": []}]
            }
        },
    )
    assert body["observed"] == 0
    assert body["steps"][0]["status"] == "pending"


def test_playbook_observations_at_extraction_root():
    snapshot = {
        "playbook_id": "pb-1",
        "version_id": "pv-1",
        "steps": [{"step_id": "pain", "label": "Problema"}],
        "entries": [],
    }
    grounding = SuggestGrounding(
        interaction_kind="meeting",
        playbook_version_id="pv-1",
        evidence_ids=frozenset(),
        playbook_snapshot=snapshot,
    )
    body = checklist_from_grounding(
        grounding,
        extraction={
            "playbook_observations": [
                {"step_id": "pain", "status": "met", "evidence_refs": ["ev-1"]},
            ]
        },
    )
    assert body["observed"] == 1
    assert body["steps"][0]["status"] == "met"
