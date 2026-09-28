"""Head of Sales phase 2 on /team/adherence: period + comparison, SDR/AE filter, per-rep
activity and process health. Everything is additive: no period = the pre-phase-2 body."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-phase-2-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.team_insights import aggregate
from app.services.team_insights.aggregate import load_team_adherence_inputs, team_adherence
from app.services.team_insights.period import Window
from tests.team_insights.test_adherence_filters import COMPANY, USER_A, USER_B, _Supabase, _memo, _score, _store

CURRENT = Window(datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 28, tzinfo=timezone.utc))
PREVIOUS = Window(datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 28, tzinfo=timezone.utc))


def _row(user, screening, when, meeting=False):
    return {"user_id": user, "screening": screening, "meeting_agreed": meeting, "observed_at": when}


ROWS = [
    _row("u1", "connected", "2026-09-02T10:00:00Z", meeting=True),
    _row("u1", "voicemail", "2026-09-03T10:00:00Z"),
    _row("u2", "no_response", "2026-09-04T10:00:00Z"),
    _row("u1", "connected", "2026-08-05T10:00:00Z"),
]
REPS = [{"userId": "u1", "name": "Ana", "salesRole": "sdr"}, {"userId": "u2", "name": "Carlos", "salesRole": "sdr"}]


def _body(**extra):
    return team_adherence(
        role="owner",
        parts=[],
        playbook_present=False,
        sample_size=0,
        activity_rows=ROWS,
        activity_period_start=CURRENT.start,
        activity_period_end=CURRENT.end,
        reps=REPS,
        **extra,
    )


def test_per_rep_activity_splits_the_same_counts_as_the_team():
    body = _body()
    by_rep = {rep["userId"]: rep["activity"] for rep in body["reps"]}
    assert by_rep["u1"] == {"attempts": 2, "connected": 1, "meetings": 1}
    assert by_rep["u2"] == {"attempts": 1, "connected": 0, "meetings": 0}
    assert body["attempts"] == sum(a["attempts"] for a in by_rep.values())


def test_without_a_previous_window_there_is_no_comparison_key():
    body = _body()
    assert "previous" not in body and "period" not in body
    assert body["process_health"] == []


def test_previous_window_reuses_activity_counts():
    body = _body(previous_period_start=PREVIOUS.start, previous_period_end=PREVIOUS.end)
    assert body["previous"]["attempts"] == 1
    assert body["previous"]["connected"] == 1
    assert body["previous"]["adherence"] is None  # no playbook: no invented number
    assert body["period"]["start"] == CURRENT.start.isoformat()


def test_process_health_reads_scored_rows_in_the_period_only():
    inside = {"met_steps": 9, "missed_steps": 1, "unknown_steps": 0, "not_applicable_steps": 0,
              "motion": "discovery", "goal_met": True, "observed_at": "2026-09-10T10:00:00Z"}
    outside = {**inside, "observed_at": "2026-08-10T10:00:00Z"}
    body = _body(health_rows=[inside, inside, outside])
    [flow] = body["process_health"]
    assert flow["motion"] == "discovery"
    assert flow["scored"] == 2
    assert flow["verdict"] == "insufficient_data"


def _roles(monkeypatch, roles):
    real = aggregate.load_team_reps

    def with_roles(supabase, company_id):
        return [{**rep, "salesRole": roles[rep["userId"]]} for rep in real(supabase, company_id)]

    monkeypatch.setattr(aggregate, "load_team_reps", with_roles)


def test_loader_sales_role_filter_keeps_only_that_role(monkeypatch):
    _roles(monkeypatch, {USER_A: "sdr", USER_B: "ae"})
    inputs = load_team_adherence_inputs(_store(), COMPANY, sales_role="ae")
    assert [rep["userId"] for rep in inputs["reps"]] == [USER_B]
    assert {row["user_id"] for row in inputs["activity_rows"]} == {USER_B}


def test_loader_sales_role_with_nobody_in_it_reads_nothing(monkeypatch):
    _roles(monkeypatch, {USER_A: "sdr", USER_B: "sdr"})
    inputs = load_team_adherence_inputs(_store(), COMPANY, sales_role="ae")
    assert inputs["reps"] == []
    assert inputs["activity_rows"] == []


def test_loader_with_period_passes_both_windows_and_health_rows():
    inputs = load_team_adherence_inputs(_store(), COMPANY, period=(CURRENT, PREVIOUS))
    assert inputs["activity_period_start"] == CURRENT.start
    assert inputs["previous_period_end"] == PREVIOUS.end
    assert len(inputs["health_rows"]) == 2
    assert all(row["motion"] == "discovery" for row in inputs["health_rows"])


def test_loader_without_period_adds_no_previous_window():
    inputs = load_team_adherence_inputs(_store(), COMPANY)
    assert "previous_period_start" not in inputs


def _client(role: str, loader=None):
    app = FastAPI()
    app.include_router(team_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER_A, role=role, status="active"
    )
    app.dependency_overrides[get_supabase] = lambda: _store()
    return TestClient(app)


@pytest.fixture
def _flags_off(monkeypatch):
    monkeypatch.setattr(team_api, "is_enabled", lambda *_a, **_k: False)


def test_endpoint_with_period_returns_the_comparison(_flags_off):
    res = _client("owner").get("/api/v1/team/adherence?period=month")
    assert res.status_code == 200
    body = res.json()
    assert "previous" in body and "period" in body
    assert "process_health" in body
    assert all("activity" in rep for rep in body["reps"])


def test_endpoint_without_period_has_no_comparison(_flags_off):
    body = _client("owner").get("/api/v1/team/adherence").json()
    assert "previous" not in body


def test_endpoint_rejects_unknown_period_and_role(_flags_off):
    client = _client("owner")
    assert client.get("/api/v1/team/adherence?period=year").status_code == 422
    assert client.get("/api/v1/team/adherence?sales_role=manager").status_code == 422


def test_member_still_gets_403_with_the_new_params(_flags_off, monkeypatch):
    monkeypatch.setattr(team_api, "effective_visibility", lambda *_a, **_k: "own")
    assert _client("member").get("/api/v1/team/adherence?period=month").status_code == 403
