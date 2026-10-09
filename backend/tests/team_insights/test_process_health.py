"""Head of Sales phase 2: is it the rep or the playbook? (plan §0 / §5)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-health-32")

from app.services.team_insights.process_health import (
    FOLLOWS_THRESHOLD,
    MIN_GROUP,
    follows_playbook,
    process_health,
)


def _row(met, missed, goal, motion="discovery", unknown=0):
    return {
        "motion": motion,
        "met_steps": met,
        "missed_steps": missed,
        "unknown_steps": unknown,
        "goal_met": goal,
    }


def _rows(n, *, follows, goal_hits, motion="discovery"):
    met, missed = (9, 1) if follows else (3, 7)
    return [_row(met, missed, i < goal_hits, motion) for i in range(n)]


def _flow(body, key="discovery"):
    return next(f for f in body if f["motion"] == key)


def test_follows_uses_met_over_applicable_and_ignores_unknown():
    assert follows_playbook({"met_steps": 7, "missed_steps": 3, "unknown_steps": 5}) is True
    assert follows_playbook({"met_steps": 6, "missed_steps": 4, "unknown_steps": 0}) is False
    assert follows_playbook({"met_steps": 0, "missed_steps": 0, "unknown_steps": 4}) is None
    assert FOLLOWS_THRESHOLD == 0.7


def test_following_and_failing_while_deviators_succeed_points_at_the_playbook():
    rows = _rows(MIN_GROUP, follows=True, goal_hits=1) + _rows(MIN_GROUP, follows=False, goal_hits=4)
    flow = _flow(process_health(rows))
    assert flow["verdict"] == "playbook_underperforms"
    assert flow["matrix"] == {
        "follows_goal": 1,
        "follows_no_goal": MIN_GROUP - 1,
        "deviates_goal": 4,
        "deviates_no_goal": MIN_GROUP - 4,
    }
    assert flow["follows_goal_rate"] == 0.1
    assert flow["deviates_goal_rate"] == 0.4


def test_playbook_helps_but_few_follow_it_points_at_coaching():
    rows = _rows(MIN_GROUP, follows=True, goal_hits=5) + _rows(MIN_GROUP * 2, follows=False, goal_hits=2)
    flow = _flow(process_health(rows))
    assert flow["verdict"] == "coach_reps"
    assert flow["follow_share"] == 1 / 3


def test_playbook_helps_and_most_follow_it_is_working():
    rows = _rows(MIN_GROUP * 2, follows=True, goal_hits=8) + _rows(MIN_GROUP, follows=False, goal_hits=1)
    assert _flow(process_health(rows))["verdict"] == "playbook_works"


def test_no_difference_between_groups_means_the_playbook_does_not_move_the_result():
    rows = _rows(MIN_GROUP, follows=True, goal_hits=3) + _rows(MIN_GROUP, follows=False, goal_hits=3)
    assert _flow(process_health(rows))["verdict"] == "no_difference"


def test_everyone_follows_so_there_is_nothing_to_compare_with():
    rows = _rows(MIN_GROUP, follows=True, goal_hits=2) + _rows(2, follows=False, goal_hits=0)
    flow = _flow(process_health(rows))
    assert flow["verdict"] == "no_comparison"
    assert flow["follows_goal_rate"] == 0.2
    assert flow["deviates_goal_rate"] is None  # below the minimum group: no rate, not zero


def test_small_sample_gives_no_verdict():
    flow = _flow(process_health(_rows(3, follows=True, goal_hits=1)))
    assert flow["verdict"] == "insufficient_data"
    assert flow["needed"] == MIN_GROUP - 3


def test_closing_goal_is_not_measurable_per_interaction_so_no_verdict_is_invented():
    flow = _flow(process_health(_rows(MIN_GROUP * 3, follows=True, goal_hits=5, motion="closing")), "closing")
    assert flow["verdict"] == "goal_not_measurable"
    assert flow["matrix"] is None


def test_unscored_and_motionless_rows_are_ignored():
    rows = [_row(0, 0, True, unknown=3), {**_row(9, 1, True), "motion": None}]
    assert process_health(rows) == []


def test_no_conclusion_when_almost_no_call_reached_the_goal():
    # 0 % against 0 % compares nothing: the reps marked no meeting in either group.
    rows = _rows(MIN_GROUP, follows=True, goal_hits=0) + _rows(MIN_GROUP, follows=False, goal_hits=1)
    assert _flow(process_health(rows))["verdict"] == "few_outcomes"
