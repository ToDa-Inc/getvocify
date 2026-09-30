"""F15: shared commercial and motion filters scope team adherence counts."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-filt-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-filt-32")

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
import pytest

from app.services.team_insights import aggregate
from app.services.team_insights.aggregate import load_team_adherence_inputs, team_adherence

COMPANY = "co-filter-1"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_WEEK = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _frozen_week(monkeypatch):
    # Fixtures are dated in the week of _WEEK; pin the Madrid week to it.
    real = aggregate.madrid_week_bounds
    monkeypatch.setattr(aggregate, "madrid_week_bounds", lambda *, now=None: real(now=now or _WEEK))


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name: str):
        self._store = store
        self._name = name
        self._filters: list[tuple[str, object]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._limit: int | None = None
        self._gte: list[tuple[str, str]] = []
        self._range: tuple[int, int] | None = None
        self._orders: list[str] = []
        self.in_sizes: list[int] = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        self._store.in_calls.append((self._name, column, len(list(values))))
        return self

    def gte(self, column, value):
        self._gte.append((column, str(value)))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def or_(self, expression: str):
        self._or = expression
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def order(self, column: str, **_kwargs):
        self._orders.append(column)
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._name, []))
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column)) in allowed]
        for column, value in self._gte:
            rows = [row for row in rows if row.get(column) is not None and str(row.get(column)) >= value]
        expression = getattr(self, "_or", None)
        if expression:
            wanted = [part.split(".", 2) for part in expression.split(",")]

            def keep(row):
                for column, op, value in wanted:
                    if op == "eq" and str(row.get(column)) == value:
                        return True
                    if op == "is" and value == "null" and row.get(column) is None:
                        return True
                return False

            rows = [row for row in rows if keep(row)]
        if self._orders:
            rows = sorted(rows, key=lambda row: tuple(str(row.get(c) or "") for c in self._orders))
        if self._range is not None:
            rows = rows[self._range[0] : self._range[1] + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class _Supabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.in_calls: list[tuple[str, str, int]] = []

    def table(self, name: str):
        return _Query(self, name)


def _memo(memo_id: str, user_id: str, motion: str, screening: str = "connected") -> dict:
    return {
        "id": memo_id,
        "company_id": COMPANY,
        "user_id": user_id,
        "sales_motion_key": motion,
        "screening_outcome": screening,
        "extraction": {},
        "intelligence": {},
        "capture_started_at": _WEEK.isoformat(),
        "created_at": _WEEK.isoformat(),
    }


def _score(memo_id: str) -> dict:
    return {
        "memo_id": memo_id,
        "created_at": _WEEK.isoformat(),
        "score": {
            "status": "ready",
            "met_steps": 1,
            "missed_steps": 0,
            "unknown_steps": 0,
            "not_applicable_steps": 0,
        },
    }


def _store() -> _Supabase:
    return _Supabase(
        {
            "memos": [
                _memo("memo-a", USER_A, "discovery"),
                _memo("memo-b", USER_B, "discovery"),
            ],
            "memo_scores": [_score("memo-a"), _score("memo-b")],
            "interaction_patterns": [],
            "playbooks": [],
            "company_members": [
                {
                    "id": "m-a",
                    "company_id": COMPANY,
                    "user_id": USER_A,
                    "role": "member",
                    "status": "active",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "m-b",
                    "company_id": COMPANY,
                    "user_id": USER_B,
                    "role": "member",
                    "status": "active",
                    "created_at": "2026-01-02T00:00:00Z",
                },
            ],
            "user_profiles": [
                {"id": USER_A, "full_name": "Ana"},
                {"id": USER_B, "full_name": "Carlos"},
            ],
        }
    )


def test_without_filter_both_reps_count():
    inputs = load_team_adherence_inputs(_store(), COMPANY)
    body = team_adherence(role="admin", **inputs)
    assert body["attempts"] == 2


def test_a_member_memo_without_company_id_still_counts_and_an_outsider_does_not():
    store = _store()
    store.tables["memos"].append({**_memo("memo-old", USER_A, "discovery"), "company_id": None})
    store.tables["memos"].append({**_memo("memo-out", "cccccccc-cccc-cccc-cccc-cccccccccccc", "discovery"), "company_id": None})
    inputs = load_team_adherence_inputs(store, COMPANY)
    body = team_adherence(role="admin", **inputs)
    assert body["attempts"] == 3


def test_activity_counts_trace_to_company_memos():
    store = _store()
    store.tables["memos"] = [_memo("memo-a", USER_A, "discovery")]
    inputs = load_team_adherence_inputs(store, COMPANY)
    body = team_adherence(role="admin", **inputs)
    assert body["attempts"] == 1


def test_user_filter_excludes_the_other_rep():
    inputs = load_team_adherence_inputs(_store(), COMPANY, user_id=USER_A)
    body = team_adherence(role="admin", **inputs)
    assert body["attempts"] == 1


def test_load_team_adherence_inputs_collects_published_playbook_entries():
    store = _store()
    store.tables["playbooks"] = [
        {
            "id": "pb-1",
            "company_id": COMPANY,
            "active_version_id": "v-1",
            "playbook_versions.status": "published",
            "playbook_versions": [
                {"id": "v-1", "status": "published", "entries": [{"category": "price", "guidance": "Ancla en el ROI."}]},
            ],
        },
    ]
    inputs = load_team_adherence_inputs(store, COMPANY)
    assert inputs["playbook_entries"] == [{"category": "price", "guidance": "Ancla en el ROI."}]


def test_load_team_adherence_inputs_prefers_the_active_version_over_a_stray_published_one():
    store = _store()
    store.tables["playbooks"] = [
        {
            "id": "pb-1",
            "company_id": COMPANY,
            "active_version_id": "v-active",
            "playbook_versions.status": "published",
            "playbook_versions": [
                {"id": "v-stale", "status": "published", "entries": [{"category": "price", "guidance": "Guía vieja."}]},
                {"id": "v-active", "status": "published", "entries": [{"category": "price", "guidance": "Guía vigente."}]},
            ],
        },
    ]
    inputs = load_team_adherence_inputs(store, COMPANY)
    assert inputs["playbook_entries"] == [{"category": "price", "guidance": "Guía vigente."}]


def test_a_paused_or_deleted_playbook_contributes_no_entries():
    """Pausing moves the active version to paused_version_id: it is still a published row, but
    nothing points at it any more, so team adherence must not read its guidance."""
    store = _store()
    store.tables["playbooks"] = [
        {
            "id": "pb-paused",
            "company_id": COMPANY,
            "active_version_id": None,
            "paused_version_id": "v-paused",
            "playbook_versions.status": "published",
            "playbook_versions": [
                {"id": "v-paused", "status": "published", "entries": [{"category": "price", "guidance": "Pausada."}]},
            ],
        },
    ]
    inputs = load_team_adherence_inputs(store, COMPANY)
    assert inputs["playbook_entries"] == []


def test_http_passes_filters_to_loader():
    captured: dict = {}

    def loader(supabase, company_id, user_id, motion):
        captured["user_id"] = user_id
        captured["motion"] = motion
        inputs = load_team_adherence_inputs(supabase, company_id, user_id=user_id, motion=motion)
        return inputs

    team_api.set_team_adherence_loader(loader)
    app = FastAPI()
    app.include_router(team_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m",
        company_id=COMPANY,
        user_id=USER_A,
        role="admin",
        status="active",
    )
    app.dependency_overrides[get_supabase] = _store
    client = TestClient(app)
    response = client.get(f"/api/v1/team/adherence?user_id={USER_B}&motion=discovery")
    team_api.set_team_adherence_loader(None)
    assert response.status_code == 200
    assert captured == {"user_id": USER_B, "motion": "discovery"}
    assert response.json()["attempts"] == 1
