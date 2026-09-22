"""F15 objection rollups: kind objection only, superseded rows excluded."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-obj-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-obj-32")

from datetime import datetime, timezone

from app.services.team_insights.objections import objection_counts

_WEEK_START = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)
_WEEK_END = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)
_IN_WEEK = "2026-09-22T10:00:00Z"
_OUT_WEEK = "2026-09-15T10:00:00Z"


def _row(
    *,
    category: str,
    kind: str = "objection",
    superseded: bool = False,
    observed_at: str | None = _IN_WEEK,
    created_at: str | None = None,
) -> dict:
    row: dict = {"category": category, "kind": kind, "superseded": superseded}
    if observed_at is not None:
        row["observed_at"] = observed_at
    if created_at is not None:
        row["created_at"] = created_at
    return row


def test_empty_input_returns_no_categories():
    assert objection_counts([], start=_WEEK_START, end=_WEEK_END) == []


def test_superseded_and_obstacle_rows_do_not_count():
    rows = [
        _row(category="price", superseded=True),
        _row(category="price", kind="obstacle"),
        _row(category="timing", kind="unknown"),
        _row(category="price"),
    ]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == [{"name": "Precio", "count": 1}]


def test_categories_sort_by_count_then_name():
    rows = [
        _row(category="timing"),
        _row(category="price"),
        _row(category="authority"),
        _row(category="authority"),
        _row(category="timing"),
        _row(category="timing"),
    ]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == [
        {"name": "Plazo", "count": 3},
        {"name": "Autoridad", "count": 2},
        {"name": "Precio", "count": 1},
    ]


def test_objection_keys_map_to_spanish_labels():
    rows = [
        _row(category="status_quo"),
        _row(category="trust"),
        _row(category="competitor"),
        _row(category="other"),
        _row(category="not_a_real_key"),
    ]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END)
    assert {item["name"] for item in result} == {
        "Statu quo",
        "Confianza",
        "Competidor",
        "Otra",
    }
    assert result == [{"name": "Otra", "count": 2}, {"name": "Competidor", "count": 1}, {"name": "Confianza", "count": 1}, {"name": "Statu quo", "count": 1}]


def test_objection_outside_madrid_week_is_excluded():
    rows = [
        _row(category="price", observed_at=_OUT_WEEK),
        _row(category="timing"),
        _row(category="authority", observed_at=None, created_at=_OUT_WEEK),
    ]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == [{"name": "Plazo", "count": 1}]


def test_objection_without_date_is_ignored():
    rows = [_row(category="price", observed_at=None, created_at=None)]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == []
