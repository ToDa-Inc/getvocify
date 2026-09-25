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
from app.services.team_insights.aggregate import load_team_adherence_inputs, team_adherence

COMPANY = "co-filter-1"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_WEEK = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


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

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def or_(self, expression: str):
        self._or = expression
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def order(self, _column: str):
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._name, []))
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column)) in allowed]
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
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class _Supabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

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
