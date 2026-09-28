"""load_team_adherence_inputs: bounded, paged, batched reads and one current score per memo."""

import logging
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-reads-32-chars")

from datetime import datetime, timedelta, timezone

import pytest

from app.services.team_insights import aggregate
from app.services.team_insights.aggregate import load_team_adherence_inputs, team_adherence
from app.services.team_insights.period import Window
from tests.team_insights.test_adherence_filters import COMPANY, USER_A, USER_B, _memo, _score, _store

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _frozen_week(monkeypatch):
    real = aggregate.madrid_week_bounds
    monkeypatch.setattr(aggregate, "madrid_week_bounds", lambda *, now=None: real(now=now or NOW))


def _at(memo: dict, when: datetime) -> dict:
    return {**memo, "capture_started_at": when.isoformat(), "created_at": when.isoformat()}


def _ids(inputs: dict) -> set[str]:
    return {str(m["id"]) for m in inputs["memo_rows"]}


def test_no_period_reads_from_the_week_start_minus_eight_days():
    week_start = aggregate.madrid_week_bounds()[0]
    store = _store()
    store.tables["memos"] = [
        _at(_memo("recent", USER_A, "discovery"), week_start - timedelta(days=7)),
        _at(_memo("old", USER_A, "discovery"), week_start - timedelta(days=9)),
    ]
    assert _ids(load_team_adherence_inputs(store, COMPANY)) == {"recent"}


def test_period_reads_from_the_oldest_window_start_minus_a_day():
    current = Window(datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 28, tzinfo=timezone.utc))
    previous = Window(datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 28, tzinfo=timezone.utc))
    store = _store()
    store.tables["memos"] = [
        _at(_memo("margin", USER_A, "discovery"), previous.start - timedelta(hours=12)),
        _at(_memo("before", USER_A, "discovery"), previous.start - timedelta(days=2)),
        _at(_memo("inside", USER_A, "discovery"), current.start),
    ]
    assert _ids(load_team_adherence_inputs(store, COMPANY, period=(current, previous))) == {"margin", "inside"}


def test_memos_are_paged_until_a_short_page(monkeypatch):
    monkeypatch.setattr(aggregate, "_PAGE_SIZE", 2)
    store = _store()
    store.tables["memos"] = [_at(_memo(f"m{i}", USER_A, "discovery"), NOW) for i in range(5)]
    assert len(_ids(load_team_adherence_inputs(store, COMPANY))) == 5


def test_memo_id_lists_are_chunked_and_responses_paged(monkeypatch):
    monkeypatch.setattr(aggregate, "_IN_BATCH", 2)
    monkeypatch.setattr(aggregate, "_PAGE_SIZE", 2)
    store = _store()
    store.tables["memos"] = [_at(_memo(f"m{i}", USER_A, "discovery"), NOW) for i in range(5)]
    store.tables["memo_scores"] = [_score(f"m{i}") for i in range(5)]
    store.tables["interaction_patterns"] = [
        {"memo_id": "m0", "category": "price", "kind": "objection", "resolution": "open", "created_at": NOW.isoformat()},
    ]
    inputs = load_team_adherence_inputs(store, COMPANY)
    sizes = [n for table, column, n in store.in_calls if column == "memo_id"]
    assert sizes and max(sizes) <= 2
    assert {t for t, c, _ in store.in_calls if c == "memo_id"} == {"memo_scores", "interaction_patterns"}
    assert inputs["sample_size"] == 5
    assert len(inputs["pattern_rows"]) == 1


def test_only_the_latest_score_revision_counts():
    store = _store()
    store.tables["memos"] = [_at(_memo("m1", USER_A, "discovery"), NOW)]
    old = {**_score("m1"), "revision_seq": 1, "created_at": "2026-09-25T10:00:00+00:00"}
    new = {**_score("m1"), "revision_seq": 2, "created_at": "2026-09-23T10:00:00+00:00"}
    new["score"] = {**new["score"], "met_steps": 4}
    store.tables["memo_scores"] = [new, old]
    inputs = load_team_adherence_inputs(store, COMPANY)
    assert inputs["sample_size"] == 1
    assert inputs["parts"][0]["met_steps"] == 4


def test_score_observed_at_is_the_memos_time_not_the_score_row():
    captured = NOW - timedelta(days=2)
    store = _store()
    store.tables["memos"] = [_at(_memo("m1", USER_A, "discovery"), captured)]
    store.tables["memo_scores"] = [{**_score("m1"), "created_at": (NOW + timedelta(days=30)).isoformat()}]
    inputs = load_team_adherence_inputs(store, COMPANY)
    assert inputs["parts"][0]["observed_at"] == captured.isoformat()
    assert inputs["health_rows"][0]["observed_at"] == captured.isoformat()
    assert inputs["rep_motion_parts"][0]["observed_at"] == captured.isoformat()


def test_read_failure_is_logged_and_stays_tolerant(caplog):
    class Failing(type(_store())):
        def table(self, name):
            if name == "memo_scores":
                raise RuntimeError("boom")
            return super().table(name)

    healthy = _store()
    store = Failing(healthy.tables)
    with caplog.at_level(logging.WARNING, logger=aggregate.logger.name):
        inputs = load_team_adherence_inputs(store, COMPANY)
    assert inputs["parts"] == []
    assert any(r.exc_info and "boom" in str(r.exc_info[1]) for r in caplog.records)
    assert team_adherence(role="admin", **inputs)["attempts"] == 2
