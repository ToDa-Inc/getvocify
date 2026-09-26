"""F15 addendum: weekly playbook adherence per rep. A gap is not a zero, and the team sums counts."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-trend-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-trend-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.team_insights.adherence_trend import adherence_trend
from app.services.team_insights.aggregate import TeamAccessError

COMPANY = "co-trend-1"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OUTSIDER = "cccccccc-cccc-cccc-cccc-cccccccccccc"
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
THIS_WEEK = "2026-09-22T10:00:00+00:00"
LAST_WEEK = "2026-09-15T10:00:00+00:00"
FLAG = "TEAM_ADHERENCE_TREND_ENABLED"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name: str):
        self._store = store
        self._name = name
        self._eq: list[tuple[str, object]] = []
        self._in: list[tuple[str, list]] = []
        self._gte: list[tuple[str, str]] = []
        self._or: str | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._eq.append((column, value))
        return self

    def in_(self, column, values):
        self._in.append((column, list(values)))
        return self

    def gte(self, column, value):
        self._gte.append((column, value))
        return self

    def or_(self, expression: str):
        self._or = expression
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def execute(self):
        if self._name in self._store.failing:
            raise RuntimeError(f"{self._name} read failed")
        self._store.calls.append((self._name, [list(v) for _, v in self._in]))
        rows = list(self._store.tables.get(self._name, []))
        for column, value in self._eq:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column)) in allowed]
        for column, value in self._gte:
            floor = datetime.fromisoformat(value)
            rows = [
                row for row in rows
                if row.get(column) and datetime.fromisoformat(str(row[column])) >= floor
            ]
        if self._or:
            wanted = [part.split(".", 2) for part in self._or.split(",")]

            def keep(row):
                for column, op, value in wanted:
                    if op == "eq" and str(row.get(column)) == value:
                        return True
                    if op == "is" and value == "null" and row.get(column) is None:
                        return True
                return False

            rows = [row for row in rows if keep(row)]
        if self._name == "memos":
            rows.sort(key=lambda row: str(row.get("id")))
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        return _Result(rows)


class _Supabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.failing: set[str] = set()
        self.calls: list = []

    def table(self, name: str):
        return _Query(self, name)


def _member(user_id: str, name: str, role: str = "member", status: str = "active") -> tuple[dict, dict]:
    return (
        {
            "id": f"m-{user_id[:4]}",
            "company_id": COMPANY,
            "user_id": user_id,
            "role": role,
            "status": status,
            "created_at": "2026-01-01T00:00:00Z",
        },
        {"id": user_id, "full_name": name},
    )


def _memo(memo_id: str, user_id: str, at: str, *, motion: str = "discovery", screening: str | None = "connected",
          status: str = "approved", company_id: str | None = COMPANY) -> dict:
    return {
        "id": memo_id,
        "company_id": company_id,
        "user_id": user_id,
        "sales_motion_key": motion,
        "screening_outcome": screening,
        "status": status,
        "capture_started_at": at,
        "created_at": at,
    }


def _score(memo_id: str, *, met: int = 1, missed: int = 0, unknown: int = 0, na: int = 0, status: str = "ready",
           reason: str | None = None, version: str | None = "pv-1", seq: int = 1, crm_outcome: str | None = None) -> dict:
    return {
        "memo_id": memo_id,
        "input_revision": f"rev-{seq}",
        "revision_seq": seq,
        "playbook_version_id": version,
        "created_at": THIS_WEEK,
        "score": {
            "status": status,
            "reason": reason,
            "crm_outcome": crm_outcome,
            "playbook_version_id": version,
            "met_steps": met,
            "missed_steps": missed,
            "unknown_steps": unknown,
            "not_applicable_steps": na,
        },
    }


def _store(memos: list[dict] | None = None, scores: list[dict] | None = None, members=None) -> _Supabase:
    members = members or [_member(USER_B, "Carlos"), _member(USER_A, "Ana", role="admin")]
    return _Supabase(
        {
            "memos": list(memos or []),
            "memo_scores": list(scores or []),
            "company_members": [m for m, _ in members],
            "user_profiles": [p for _, p in members],
        }
    )


def _trend(store: _Supabase, **kwargs) -> dict:
    kwargs.setdefault("role", "admin")
    kwargs.setdefault("now", NOW)
    return adherence_trend(store, COMPANY, **kwargs)


def _rep(body: dict, user_id: str) -> dict:
    return next(rep for rep in body["reps"] if rep["user_id"] == user_id)


def _week(series: dict, week_start: str) -> dict:
    return next(week for week in series["weeks"] if week["week_start"] == week_start)


# --- window and weeks ---------------------------------------------------------------


def test_default_window_is_eight_local_weeks_ending_with_the_current_one():
    body = _trend(_store())
    starts = [week["week_start"] for week in body["weeks"]]
    assert len(starts) == 8
    assert starts[0] == "2026-08-03"
    assert starts[-1] == "2026-09-21"
    assert body["weeks"][-1] == {"week_start": "2026-09-21", "week_end": "2026-09-27", "in_progress": True}
    assert all(week["in_progress"] is False for week in body["weeks"][:-1])
    assert body["timezone"] == "Europe/Madrid"
    assert body["coverage"] == "complete"


def test_weeks_is_clamped_between_one_and_twelve():
    assert len(_trend(_store(), weeks=0)["weeks"]) == 1
    assert len(_trend(_store(), weeks=40)["weeks"]) == 12


def test_week_boundary_follows_madrid_across_the_dst_change():
    now = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    # Sunday 25 Oct 23:30 local (CET, after the change) and Monday 26 Oct 00:30 local.
    memos = [
        _memo("memo-sun", USER_A, "2026-10-25T22:30:00+00:00"),
        _memo("memo-mon", USER_A, "2026-10-25T23:30:00+00:00"),
    ]
    scores = [_score("memo-sun"), _score("memo-mon")]
    body = _trend(_store(memos, scores), now=now)
    rep = _rep(body, USER_A)
    assert _week(rep, "2026-10-19")["interactions"] == 1
    assert _week(rep, "2026-10-26")["interactions"] == 1


# --- gaps, coverage and null ----------------------------------------------------------


def test_a_week_without_conversations_is_a_gap_not_a_zero():
    body = _trend(_store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a")]))
    empty = _week(_rep(body, USER_A), "2026-09-14")
    assert empty["state"] == "gap"
    assert empty["interactions"] == 0
    assert empty["adherence"] is None
    assert empty["coverage"] is None


def test_a_rep_without_conversations_in_the_window_has_only_gaps():
    body = _trend(_store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a")]))
    carlos = _rep(body, USER_B)
    assert len(carlos["weeks"]) == 8
    assert {week["state"] for week in carlos["weeks"]} == {"gap"}


def test_conversations_without_playbook_are_counted_apart_and_adherence_stays_null():
    memos = [_memo("memo-a", USER_A, THIS_WEEK), _memo("memo-b", USER_A, THIS_WEEK)]
    scores = [
        _score("memo-a", met=0, status="unavailable", reason="missing_playbook", version=None),
        _score("memo-b", met=0, status="unavailable", reason="missing_playbook", version=None),
    ]
    week = _week(_rep(_trend(_store(memos, scores)), USER_A), "2026-09-21")
    assert week["interactions"] == 2
    assert week["without_playbook"] == 2
    assert week["scored"] == 0
    assert week["adherence"] is None
    assert week["state"] == "unscored"


def test_pending_failed_or_missing_scores_are_without_score_not_a_miss():
    memos = [
        _memo("memo-pending", USER_A, THIS_WEEK),
        _memo("memo-failed", USER_A, THIS_WEEK),
        _memo("memo-none", USER_A, THIS_WEEK),
        _memo("memo-ok", USER_A, THIS_WEEK),
    ]
    scores = [
        _score("memo-pending", status="pending"),
        _score("memo-failed", status="failed", reason="uncited_evidence"),
        _score("memo-ok", met=3, missed=1),
    ]
    week = _week(_rep(_trend(_store(memos, scores)), USER_A), "2026-09-21")
    assert week["interactions"] == 4
    assert week["without_score"] == 3
    assert week["scored"] == 1
    assert week["met_steps"] == 3
    assert week["applicable_steps"] == 4
    assert week["adherence"] == 0.75


def test_only_unknown_steps_is_null_adherence_with_zero_coverage():
    week = _week(
        _rep(_trend(_store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a", met=0, unknown=3, status="partial")])), USER_A),
        "2026-09-21",
    )
    assert week["scored"] == 1
    assert week["adherence"] is None
    assert week["coverage"] == 0.0
    assert week["unknown_steps"] == 3
    assert week["state"] == "unscored"


def test_unknown_steps_go_to_coverage_not_to_missed():
    week = _week(
        _rep(_trend(_store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a", met=1, missed=1, unknown=1, na=1)])), USER_A),
        "2026-09-21",
    )
    assert week["adherence"] == 0.5
    assert week["coverage"] == pytest.approx(2 / 3)
    assert week["not_applicable_steps"] == 1


# --- sums, not averages ---------------------------------------------------------------


def test_team_sums_counts_instead_of_averaging_rep_percentages():
    memos = [_memo("memo-a", USER_A, THIS_WEEK), _memo("memo-b", USER_B, THIS_WEEK)]
    scores = [_score("memo-a", met=1, missed=0), _score("memo-b", met=1, missed=8)]
    body = _trend(_store(memos, scores))
    team = _week(body["team"], "2026-09-21")
    assert team["met_steps"] == 2
    assert team["applicable_steps"] == 10
    assert team["adherence"] == 0.2
    assert _week(_rep(body, USER_A), "2026-09-21")["adherence"] == 1.0
    assert _week(_rep(body, USER_B), "2026-09-21")["adherence"] == pytest.approx(1 / 9)


def test_a_rescored_conversation_counts_once_with_the_latest_revision():
    memos = [_memo("memo-a", USER_A, THIS_WEEK)]
    scores = [_score("memo-a", met=0, missed=4, seq=1), _score("memo-a", met=3, missed=1, seq=2)]
    week = _week(_rep(_trend(_store(memos, scores)), USER_A), "2026-09-21")
    assert week["interactions"] == 1
    assert week["scored"] == 1
    assert week["met_steps"] == 3
    assert week["applicable_steps"] == 4


def test_the_crm_outcome_does_not_change_adherence():
    won = _trend(_store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a", met=2, missed=2, crm_outcome="won")]))
    none = _trend(_store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a", met=2, missed=2)]))
    assert _rep(won, USER_A)["weeks"] == _rep(none, USER_A)["weeks"]


# --- what counts as a conversation ----------------------------------------------------


def test_voicemail_no_answer_and_failed_memos_are_not_conversations():
    memos = [
        _memo("memo-vm", USER_A, THIS_WEEK, screening="voicemail"),
        _memo("memo-na", USER_A, THIS_WEEK, screening="no_response"),
        _memo("memo-fail", USER_A, THIS_WEEK, status="failed"),
        _memo("memo-ok", USER_A, THIS_WEEK, screening=None),
    ]
    week = _week(_rep(_trend(_store(memos, [_score("memo-ok")])), USER_A), "2026-09-21")
    assert week["interactions"] == 1


def test_conversations_outside_the_window_are_ignored():
    memos = [_memo("memo-old", USER_A, "2026-07-01T10:00:00+00:00"), _memo("memo-a", USER_A, THIS_WEEK)]
    rep = _rep(_trend(_store(memos, [_score("memo-old"), _score("memo-a")])), USER_A)
    assert sum(week["interactions"] for week in rep["weeks"]) == 1


def test_capture_time_decides_the_week_not_the_row_creation():
    memo = _memo("memo-a", USER_A, LAST_WEEK)
    memo["created_at"] = THIS_WEEK
    rep = _rep(_trend(_store([memo], [_score("memo-a")])), USER_A)
    assert _week(rep, "2026-09-14")["interactions"] == 1
    assert _week(rep, "2026-09-21")["interactions"] == 0


def test_a_member_memo_without_company_id_counts_and_an_outsider_does_not():
    memos = [
        _memo("memo-old", USER_A, THIS_WEEK, company_id=None),
        _memo("memo-out", OUTSIDER, THIS_WEEK, company_id=None),
    ]
    body = _trend(_store(memos, [_score("memo-old"), _score("memo-out")]))
    assert _week(body["team"], "2026-09-21")["interactions"] == 1
    assert OUTSIDER not in {rep["user_id"] for rep in body["reps"]}


# --- playbook versions ----------------------------------------------------------------


def test_a_playbook_version_change_is_marked_and_each_conversation_keeps_its_version():
    memos = [_memo("memo-old", USER_A, LAST_WEEK), _memo("memo-new", USER_A, THIS_WEEK)]
    scores = [_score("memo-old", met=1, missed=1, version="pv-1"), _score("memo-new", met=2, missed=0, version="pv-2")]
    rep = _rep(_trend(_store(memos, scores)), USER_A)
    before = _week(rep, "2026-09-14")
    after = _week(rep, "2026-09-21")
    assert before["playbook_version_ids"] == ["pv-1"]
    assert before["new_playbook_version"] is False
    assert after["playbook_version_ids"] == ["pv-2"]
    assert after["new_playbook_version"] is True
    assert before["adherence"] == 0.5
    assert after["adherence"] == 1.0


def test_two_motions_with_their_own_playbooks_are_not_a_version_change():
    memos = [
        _memo("memo-d", USER_A, LAST_WEEK, motion="discovery"),
        _memo("memo-c", USER_A, THIS_WEEK, motion="closing"),
    ]
    scores = [_score("memo-d", version="pv-discovery"), _score("memo-c", version="pv-closing")]
    rep = _rep(_trend(_store(memos, scores)), USER_A)
    assert not any(week["new_playbook_version"] for week in rep["weeks"])


# --- small samples, order, filters -----------------------------------------------------


def test_one_to_four_scored_conversations_is_sample_limited():
    memos = [_memo(f"memo-{i}", USER_A, THIS_WEEK) for i in range(4)]
    few = _week(_rep(_trend(_store(memos, [_score(m["id"]) for m in memos])), USER_A), "2026-09-21")
    assert few["sample_limited"] is True
    memos5 = [_memo(f"memo-{i}", USER_A, THIS_WEEK) for i in range(5)]
    enough = _week(_rep(_trend(_store(memos5, [_score(m["id"]) for m in memos5])), USER_A), "2026-09-21")
    assert enough["sample_limited"] is False


def test_reps_are_alphabetical_never_by_adherence():
    memos = [_memo("memo-a", USER_A, THIS_WEEK), _memo("memo-b", USER_B, THIS_WEEK)]
    scores = [_score("memo-a", met=0, missed=5), _score("memo-b", met=5, missed=0)]
    body = _trend(_store(memos, scores))
    assert [rep["name"] for rep in body["reps"]] == ["Ana", "Carlos"]


def test_disabled_members_are_not_listed():
    members = [_member(USER_A, "Ana"), _member(USER_B, "Carlos", status="disabled")]
    body = _trend(_store(members=members))
    assert [rep["user_id"] for rep in body["reps"]] == [USER_A]


def test_user_filter_returns_only_that_rep_and_no_team_row():
    memos = [_memo("memo-a", USER_A, THIS_WEEK), _memo("memo-b", USER_B, THIS_WEEK)]
    body = _trend(_store(memos, [_score("memo-a"), _score("memo-b")]), user_id=USER_B)
    assert [rep["user_id"] for rep in body["reps"]] == [USER_B]
    assert body["team"] is None


def test_a_user_filter_outside_the_company_returns_no_rows():
    memos = [_memo("memo-out", OUTSIDER, THIS_WEEK)]
    body = _trend(_store(memos, [_score("memo-out")]), user_id=OUTSIDER)
    assert body["reps"] == []
    assert body["team"] is None


def test_motion_filter_keeps_only_that_typology():
    memos = [
        _memo("memo-d", USER_A, THIS_WEEK, motion="discovery"),
        _memo("memo-c", USER_A, THIS_WEEK, motion="closing"),
    ]
    body = _trend(_store(memos, [_score("memo-d"), _score("memo-c")]), motion="closing")
    assert _week(body["team"], "2026-09-21")["interactions"] == 1


# --- volume and failures --------------------------------------------------------------


def test_more_than_a_thousand_conversations_are_all_counted_and_scores_are_batched():
    memos = [_memo(f"memo-{i:05d}", USER_A, THIS_WEEK) for i in range(1200)]
    scores = [_score(m["id"]) for m in memos]
    store = _store(memos, scores)
    week = _week(_rep(_trend(store), USER_A), "2026-09-21")
    assert week["interactions"] == 1200
    assert week["scored"] == 1200
    score_batches = [ins[0] for name, ins in store.calls if name == "memo_scores"]
    assert score_batches and max(len(batch) for batch in score_batches) <= 200


@pytest.mark.parametrize("table", ["memos", "memo_scores", "company_members"])
def test_a_failed_read_is_unavailable_without_numbers(table):
    store = _store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a")])
    store.failing.add(table)
    body = _trend(store)
    assert body["coverage"] == "unavailable"
    assert body["reps"] == []
    assert body["team"] is None


def test_a_member_is_refused_by_the_service():
    with pytest.raises(TeamAccessError):
        _trend(_store(), role="member")


# --- HTTP: flag and permissions --------------------------------------------------------


def _client(store: _Supabase, role: str) -> TestClient:
    app = FastAPI()
    app.include_router(team_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER_A, role=role, status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


@pytest.fixture
def flag(monkeypatch):
    feature_flags.clear_cache()
    state = {"on": False}

    def is_enabled(_supabase, company_id, name):
        assert company_id == COMPANY
        return state["on"] if name == FLAG else False

    monkeypatch.setattr(team_api, "is_enabled", is_enabled)
    monkeypatch.setattr(team_api, "_trend_now", lambda: NOW)
    yield state
    feature_flags.clear_cache()


def test_flag_off_answers_like_a_missing_route(flag):
    store = _store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a")])
    response = _client(store, "admin").get("/api/v1/team/adherence/trend")
    missing = _client(store, "admin").get("/api/v1/team/does-not-exist")
    assert response.status_code == 404
    assert response.json() == missing.json()


def test_flag_on_member_gets_403_without_numbers(flag):
    flag["on"] = True
    store = _store([_memo("memo-a", USER_A, THIS_WEEK)], [_score("memo-a")])
    response = _client(store, "member").get("/api/v1/team/adherence/trend")
    assert response.status_code == 403
    assert "met_steps" not in response.text
    assert "weeks" not in response.text


def test_flag_on_admin_reads_the_trend_with_shared_filters(flag):
    flag["on"] = True
    memos = [_memo("memo-a", USER_A, THIS_WEEK, motion="closing"), _memo("memo-b", USER_B, THIS_WEEK)]
    store = _store(memos, [_score("memo-a"), _score("memo-b")])
    response = _client(store, "owner").get(
        f"/api/v1/team/adherence/trend?weeks=4&user_id={USER_A}&motion=closing"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["weeks"]) == 4
    assert [rep["user_id"] for rep in body["reps"]] == [USER_A]
    assert body["reps"][0]["weeks"][-1]["interactions"] == 1


def test_the_existing_adherence_route_is_unchanged_by_the_flag(flag):
    response = _client(_store(), "member").get("/api/v1/team/adherence")
    assert response.status_code == 403
