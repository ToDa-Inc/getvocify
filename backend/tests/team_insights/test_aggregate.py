"""F15 adherence is pooled. A missing playbook does not invent a performance number."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-agg-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-agg-32")

from app.services.team_insights.aggregate import activity_counts, team_adherence


def _part(met: int, missed: int) -> dict:
    return {"met_steps": met, "missed_steps": missed, "unknown_steps": 0, "not_applicable_steps": 0}


def test_two_reps_pool_to_two_of_ten_not_the_average_of_their_rates():
    metrics = team_adherence(
        role="admin",
        parts=[_part(1, 0), _part(1, 8)],
        playbook_present=True,
        sample_size=10,
    )
    assert metrics["met_steps"] == 2
    assert metrics["applicable_steps"] == 10
    assert metrics["adherence"] == 0.2
    assert metrics["adherence"] != (1 + (1 / 9)) / 2


def test_without_a_playbook_there_is_no_invented_performance():
    metrics = team_adherence(role="owner", parts=[_part(1, 0)], playbook_present=False, sample_size=10)
    assert metrics["adherence"] is None
    assert metrics["coverage"] is None
    assert metrics["conclusion"] is None


def test_voicemail_and_connected_activity_reach_adherence_json():
    rows = [
        {"screening": "voicemail"},
        {"screening": "voicemail"},
        {"screening": "connected", "meeting_agreed": True},
    ]
    assert activity_counts(rows) == {"attempts": 3, "connected": 1, "meetings": 1}
    metrics = team_adherence(
        role="admin",
        parts=[],
        playbook_present=False,
        sample_size=0,
        activity_rows=rows,
    )
    assert metrics["attempts"] == 3
    assert metrics["connected"] == 1
    assert metrics["meetings"] == 1
    assert metrics["adherence"] is None
