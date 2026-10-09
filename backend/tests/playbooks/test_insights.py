"""Fase 3: GET /playbooks/{key}/insights - per-step rates and objections from scored calls."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-pb-insights-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pb-insights-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import playbook_insights as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.playbooks.insights import (
    MIN_APPLICABLE,
    build_insights,
    memo_observations,
    scored_memo_ids,
    step_insights,
)
from app.services.team_insights import aggregate
from tests.team_insights.test_adherence_filters import COMPANY, USER_A, _store

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)  # Thursday
THIS_WEEK = "2026-09-23T09:00:00+00:00"
LAST_WEEK = "2026-09-16T09:00:00+00:00"
EARLIER_IN_MONTH = "2026-09-02T09:00:00+00:00"
STEPS = [
    {"step_id": "s-greet", "label": "Saludo"},
    {"step_id": "s-pain", "label": "Dolor"},
    {"step_id": "s-next", "label": "Siguiente paso"},
]
ENTRIES = [
    {"category": "price", "guidance": "Vuelve al valor antes de hablar de precio."},
    {"category": "timing", "guidance": "   "},
]


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(api, "_now", lambda: NOW)


def _obs(**statuses) -> list[dict]:
    return [{"step_id": step.replace("_", "-"), "status": status} for step, status in statuses.items()]


def _call(memo_id, *, at=THIS_WEEK, user=USER_A, motion="discovery", observations=None, flat=False, scored=True):
    """(memo, score) - the memo carries its observations where the extractor puts them."""
    if flat:
        extraction = {"playbook_observations": observations}
    else:
        extraction = {"intelligence": {"playbook_observations": observations or []}}
    memo = {
        "id": memo_id,
        "company_id": COMPANY,
        "user_id": user,
        "sales_motion_key": motion,
        "screening_outcome": "connected",
        "extraction": extraction,
        "capture_started_at": at,
        "created_at": at,
    }
    status = "ready" if scored else "unavailable"
    score = {"memo_id": memo_id, "revision_seq": 1, "created_at": at, "score": {"status": status}}
    return memo, score


def _supabase(calls, *, patterns=(), version="published", entries=None, steps=None):
    store = _store()
    store.tables["memos"] = [memo for memo, _ in calls]
    store.tables["memo_scores"] = [score for _, score in calls]
    store.tables["interaction_patterns"] = list(patterns)
    store.tables["playbooks"] = []
    store.tables["playbook_versions"] = []
    if version:
        store.tables["playbooks"] = [
            {"id": "pb-1", "company_id": COMPANY, "sales_motion_key": "discovery", "active_version_id": "v-2"}
        ]
        store.tables["playbook_versions"] = [
            {
                "id": "v-2",
                "status": version,
                "steps": STEPS if steps is None else steps,
                "entries": ENTRIES if entries is None else entries,
            }
        ]
    return store


def _pattern(memo_id, category, *, resolution="open", response=None, kind="objection", superseded=False, pattern_id=None):
    return {
        "memo_id": memo_id,
        "pattern_id": pattern_id or f"objection:{memo_id}:{category}",
        "input_revision": "r1",
        "category": category,
        "kind": kind,
        "resolution": resolution,
        "response": response,
        "superseded": superseded,
        "created_at": "2026-09-30T00:00:00+00:00",
    }


def _client(supabase, role="admin"):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_supabase] = lambda: supabase
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id="user-boss", role=role, status="active"
    )
    return TestClient(app)


def _get(supabase, period="week", role="admin", key="discovery"):
    return _client(supabase, role).get(f"/api/v1/playbooks/{key}/insights", params={"period": period})


def _many(prefix, n, observations, **kwargs):
    return [_call(f"{prefix}-{i}", observations=observations, **kwargs) for i in range(n)]


# --- steps ---------------------------------------------------------------------------


def test_rate_is_null_under_ten_applicable_calls_and_a_number_from_ten():
    nine = _many("a", 9, _obs(s_greet="met"))
    body = _get(_supabase(nine)).json()
    assert body["steps"][0] == {"step_id": "s-greet", "met": 9, "missed": 0, "rate": None}

    ten = nine + [_call("a-9", observations=_obs(s_greet="missed"))]
    body = _get(_supabase(ten)).json()
    assert body["calls"] == 10
    assert body["steps"][0] == {"step_id": "s-greet", "met": 9, "missed": 1, "rate": 0.9}
    assert MIN_APPLICABLE == 10


def test_not_applicable_and_unknown_do_not_count_toward_the_threshold():
    calls = _many("m", 6, _obs(s_greet="met")) + _many("n", 3, _obs(s_greet="not_applicable"))
    calls += _many("u", 5, _obs(s_greet="unknown"))
    step = _get(_supabase(calls)).json()["steps"][0]
    assert step == {"step_id": "s-greet", "met": 6, "missed": 0, "rate": None}


def test_steps_follow_the_active_versions_order_and_ignore_unknown_step_ids():
    calls = [
        _call("c-1", observations=[
            {"step_id": "s-next", "status": "missed"},
            {"step_id": "s-retired", "status": "met"},  # a step no longer in the active version
            {"step_id": "s-greet", "status": "met"},
        ]),
        _call("c-2", observations=[{"step_id": "s-next", "status": "met"}]),
    ]
    body = _get(_supabase(calls)).json()
    assert [s["step_id"] for s in body["steps"]] == ["s-greet", "s-pain", "s-next"]
    assert body["steps"][0]["met"] == 1
    assert body["steps"][1] == {"step_id": "s-pain", "met": 0, "missed": 0, "rate": None}
    assert body["steps"][2] == {"step_id": "s-next", "met": 1, "missed": 1, "rate": None}
    assert "s-retired" not in str(body)


def test_observations_fall_back_to_the_flat_extraction_key():
    memo, _ = _call("f-1", observations=_obs(s_greet="met"), flat=True)
    assert memo_observations(memo) == {"s-greet": "met"}
    both, _ = _call("f-2", observations=_obs(s_greet="met"))
    both["extraction"]["playbook_observations"] = _obs(s_greet="missed")
    assert memo_observations(both) == {"s-greet": "met"}  # intelligence wins
    assert memo_observations({"extraction": None}) == {}


def test_a_step_is_counted_once_per_call():
    memo, _ = _call("d-1", observations=[
        {"step_id": "s-greet", "status": "met"},
        {"step_id": "s-greet", "status": "missed"},
    ])
    first = step_insights([memo], STEPS)[0]
    assert (first["met"], first["missed"]) == (1, 0)


# --- which calls are considered -------------------------------------------------------


def test_only_scored_calls_of_the_motion_in_the_period_and_company_are_considered():
    calls = [
        _call("ok", observations=_obs(s_greet="met")),
        _call("unscored", observations=_obs(s_greet="met"), scored=False),
        _call("other-motion", motion="closing", observations=_obs(s_greet="met")),
        _call("last-week", at=LAST_WEEK, observations=_obs(s_greet="met")),
        _call("outsider", user="cccccccc-cccc-cccc-cccc-cccccccccccc", observations=_obs(s_greet="met")),
    ]
    week = _get(_supabase(calls)).json()
    assert week["calls"] == 1 and week["steps"][0]["met"] == 1

    month = _get(_supabase(calls), period="month").json()
    assert month["period"] == "month"
    assert month["calls"] == 2  # ok + last-week


def test_month_reaches_back_to_the_first_and_the_week_does_not():
    calls = [_call("early", at=EARLIER_IN_MONTH, observations=_obs(s_greet="met"))]
    assert _get(_supabase(calls), period="week").json()["calls"] == 0
    assert _get(_supabase(calls), period="month").json()["calls"] == 1


def test_the_latest_score_revision_decides_whether_a_call_is_scored():
    _, score = _call("rev", observations=_obs(s_greet="met"))
    later = {**score, "revision_seq": 2, "score": {"status": "unavailable"}}
    assert scored_memo_ids([score, later]) == set()
    assert scored_memo_ids([score]) == {"rev"}


def test_memos_and_scores_are_read_in_pages(monkeypatch):
    monkeypatch.setattr(aggregate, "_PAGE_SIZE", 2)
    monkeypatch.setattr(aggregate, "_IN_BATCH", 2)
    calls = _many("p", 5, _obs(s_greet="met"))
    body = _get(_supabase(calls)).json()
    assert body["calls"] == 5 and body["steps"][0]["met"] == 5


# --- objections -----------------------------------------------------------------------


def test_objections_have_share_answered_and_a_nameless_best_example():
    calls = [_call(f"o-{i}") for i in range(4)]
    patterns = [
        _pattern("o-0", "price", resolution="resolved", response="Lo comparamos con el coste de no hacerlo."),
        _pattern("o-1", "price", resolution="open"),
        _pattern("o-2", "timing", resolution="resolved", response="Empezamos con un piloto pequeño."),
        _pattern("o-3", "trust", resolution="unknown", superseded=True),  # superseded: not counted
        _pattern("o-3", "authority", kind="obstacle", pattern_id="obstacle:o-3"),  # not an objection
    ]
    response = _get(_supabase(calls, patterns=patterns))
    body = response.json()
    assert body["calls"] == 4
    assert body["objections"] == [
        {
            "category": "price",
            "count": 2,
            "share": 0.5,
            "answered": True,
            "best_example": "Lo comparamos con el coste de no hacerlo.",
        },
        # guidance is blank for timing: not answered, but the team has an example to offer
        {
            "category": "timing",
            "count": 1,
            "share": 0.25,
            "answered": False,
            "best_example": "Empezamos con un piloto pequeño.",
        },
    ]
    # No rep name anywhere in the body (the fixture reps are Ana and Carlos).
    assert "Ana" not in response.text and "Carlos" not in response.text
    assert set(body["objections"][0]) == {"category", "count", "share", "answered", "best_example"}


def test_best_example_is_the_most_recent_call_not_the_latest_extraction():
    older, _ = _call("b-old", at="2026-09-22T09:00:00+00:00")
    newer, _ = _call("b-new", at="2026-09-23T09:00:00+00:00")
    # Equally tight answers: the most recent call's wins (its time, not the extraction's).
    old_row = _pattern("b-old", "price", resolution="resolved", response="primera respuesta aqui")
    new_row = {
        **_pattern("b-new", "price", resolution="resolved", response="segunda respuesta aqui"),
        "created_at": "2026-09-24T00:00:00+00:00",  # extracted earlier than old_row
    }
    body = build_insights(
        period="week",
        memos=[older, newer],
        scored_ids={"b-old", "b-new"},
        pattern_rows=[old_row, new_row],
        steps=[],
        entries=[],
        start=datetime(2026, 9, 21, tzinfo=timezone.utc),
        end=datetime(2026, 9, 28, tzinfo=timezone.utc),
        motion="discovery",
    )
    assert body["objections"][0]["best_example"] == "segunda respuesta aqui"
    assert body["objections"][0]["answered"] is False


def test_objections_of_calls_outside_the_period_or_unscored_do_not_count():
    calls = [_call("in"), _call("out", at=LAST_WEEK), _call("unscored", scored=False)]
    patterns = [_pattern("in", "price"), _pattern("out", "price"), _pattern("unscored", "price")]
    body = _get(_supabase(calls, patterns=patterns)).json()
    assert body["calls"] == 1
    assert body["objections"][0]["count"] == 1 and body["objections"][0]["share"] == 1.0


def test_no_calls_gives_zeroed_steps_and_no_objections():
    body = _get(_supabase([])).json()
    assert body == {
        "period": "week",
        "calls": 0,
        "steps": [{"step_id": s["step_id"], "met": 0, "missed": 0, "rate": None} for s in STEPS],
        "objections": [],
    }


# --- access and missing playbook ---------------------------------------------------------


def test_a_member_is_rejected_before_any_read():
    class Boom:
        def table(self, name):
            raise AssertionError(f"read {name} for a member")

    response = _get(Boom(), role="member")
    assert response.status_code == 403
    assert "steps" not in response.text and "objections" not in response.text


def test_owner_and_admin_can_read():
    for role in ("owner", "admin"):
        assert _get(_supabase([]), role=role).status_code == 200


def test_an_unknown_period_is_rejected():
    assert _get(_supabase([]), period="year").status_code == 422


def test_no_active_version_returns_empty_steps_but_still_the_objections():
    calls = [_call("n-1", observations=_obs(s_greet="met")), _call("n-2")]
    patterns = [
        _pattern("n-1", "price", resolution="resolved", response="Volvemos al valor."),
        _pattern("n-2", "price"),
    ]
    for supabase in (
        _supabase(calls, patterns=patterns, version=None),  # no playbook at all
        _supabase(calls, patterns=patterns, version="draft"),  # the active pointer is not published
    ):
        response = _get(supabase)
        assert response.status_code == 200
        body = response.json()
        assert body["steps"] == []
        assert body["calls"] == 2
        assert body["objections"] == [
            {"category": "price", "count": 2, "share": 1.0, "answered": False, "best_example": "Volvemos al valor."}
        ]


def test_a_failed_read_is_a_503_not_a_page_of_zeros():
    class Down:
        def __init__(self, inner):
            self._inner = inner

        def table(self, name):
            if name == "memo_scores":
                raise RuntimeError("db down")
            return self._inner.table(name)

    assert _get(Down(_supabase([_call("x")]))).status_code == 503
