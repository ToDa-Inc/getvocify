"""F09 adherence: unknown is not a miss, and teams are pooled by counts."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-coaching-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-coaching-32")

from app.services.coaching.metrics import aggregate_adherence, compute_adherence


def test_unknown_is_not_a_failure():
    metrics = compute_adherence(["met", "missed", "unknown", "not_applicable"])
    assert metrics["met_steps"] == 1
    assert metrics["applicable_steps"] == 2
    assert metrics["unknown_steps"] == 1
    assert metrics["not_applicable_steps"] == 1
    assert metrics["adherence"] == 0.5
    assert metrics["coverage"] == 2 / 3
    assert "value" not in metrics


def test_all_unknown_or_nothing_applicable_leaves_adherence_empty():
    unknown = compute_adherence(["unknown", "unknown"])
    assert unknown["adherence"] is None
    assert unknown["coverage"] == 0
    assert unknown["applicable_steps"] == 0
    empty = compute_adherence(["not_applicable"])
    assert empty["adherence"] is None
    assert empty["coverage"] is None
    assert compute_adherence([])["adherence"] is None


def test_adherence_is_met_steps_over_applicable_steps():
    metrics = compute_adherence(["met", "missed", "unknown"])
    assert metrics["met_steps"] == 1
    assert metrics["applicable_steps"] == 2
    assert metrics["adherence"] == metrics["met_steps"] / metrics["applicable_steps"]


def test_teams_are_pooled_by_counts_not_by_averaging_percentages():
    strong = compute_adherence(["met"])
    uneven = compute_adherence(["met", "missed", "missed", "missed"])
    pooled = aggregate_adherence([strong, uneven])
    assert pooled["met_steps"] == 2
    assert pooled["applicable_steps"] == 5
    assert pooled["adherence"] == 2 / 5
    assert pooled["adherence"] != (strong["adherence"] + uneven["adherence"]) / 2
