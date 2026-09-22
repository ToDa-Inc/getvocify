"""F15 objection rollups: kind objection only, superseded rows excluded."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-obj-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-obj-32")

from app.services.team_insights.objections import objection_counts


def _row(*, category: str, kind: str = "objection", superseded: bool = False) -> dict:
    return {"category": category, "kind": kind, "superseded": superseded}


def test_empty_input_returns_no_categories():
    assert objection_counts([]) == []


def test_superseded_and_obstacle_rows_do_not_count():
    rows = [
        _row(category="price", superseded=True),
        _row(category="price", kind="obstacle"),
        _row(category="timing", kind="unknown"),
        _row(category="price"),
    ]
    assert objection_counts(rows) == [{"name": "price", "count": 1}]


def test_categories_sort_by_count_then_name():
    rows = [
        _row(category="timing"),
        _row(category="price"),
        _row(category="authority"),
        _row(category="authority"),
        _row(category="timing"),
        _row(category="timing"),
    ]
    assert objection_counts(rows) == [
        {"name": "timing", "count": 3},
        {"name": "authority", "count": 2},
        {"name": "price", "count": 1},
    ]
