"""T11: the week's best interactions per flow, ranked pure and DB-free."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-coaching-best-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-coaching-best-32")

from datetime import datetime, timezone

from app.services.coaching.best import best_by_flow

_WEEK_START = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)
_WEEK_END = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)
_IN_WEEK = "2026-09-22T10:00:00Z"
_OUT_WEEK = "2026-09-15T10:00:00Z"


def _row(
    *,
    memo_id: str,
    motion: str = "discovery",
    user_id: str = "u1",
    author: str = "Ana",
    observed_at: str | None = _IN_WEEK,
    value: float | None = 8,
    evidence: list[dict] | None = None,
) -> dict:
    row: dict = {
        "memo_id": memo_id,
        "sales_motion_key": motion,
        "user_id": user_id,
        "author": author,
    }
    if observed_at is not None:
        row["observed_at"] = observed_at
    if value is not None:
        row["value"] = value
    if evidence is not None:
        row["evidence"] = evidence
    return row


def test_empty_rows_yield_empty_flows():
    assert best_by_flow([], start=_WEEK_START, end=_WEEK_END) == {"sdr": [], "ae": []}


def test_discovery_and_closing_sort_into_sdr_and_ae():
    rows = [
        _row(memo_id="m-discovery", motion="discovery"),
        _row(memo_id="m-closing", motion="closing"),
        _row(memo_id="m-other", motion="qualification"),
    ]
    result = best_by_flow(rows, start=_WEEK_START, end=_WEEK_END)
    assert [item["memo_id"] for item in result["sdr"]] == ["m-discovery"]
    assert [item["memo_id"] for item in result["ae"]] == ["m-closing"]


def test_best_score_first_ties_broken_by_most_recent():
    rows = [
        _row(memo_id="m-low", value=5, observed_at="2026-09-22T09:00:00Z"),
        _row(memo_id="m-high", value=9, observed_at="2026-09-22T09:00:00Z"),
        _row(memo_id="m-tie-old", value=9, observed_at="2026-09-22T08:00:00Z"),
        _row(memo_id="m-tie-new", value=9, observed_at="2026-09-23T08:00:00Z"),
    ]
    result = best_by_flow(rows, start=_WEEK_START, end=_WEEK_END)
    assert [item["memo_id"] for item in result["sdr"]] == ["m-tie-new", "m-high", "m-tie-old"]


def test_limited_to_top_three_per_flow():
    rows = [_row(memo_id=f"m-{i}", value=float(i)) for i in range(5)]
    result = best_by_flow(rows, start=_WEEK_START, end=_WEEK_END)
    assert len(result["sdr"]) == 3
    assert [item["memo_id"] for item in result["sdr"]] == ["m-4", "m-3", "m-2"]


def test_rows_outside_the_week_do_not_count():
    rows = [_row(memo_id="m-out", observed_at=_OUT_WEEK)]
    result = best_by_flow(rows, start=_WEEK_START, end=_WEEK_END)
    assert result["sdr"] == []


def test_rows_without_a_numeric_value_do_not_count():
    rows = [_row(memo_id="m-none", value=None)]
    result = best_by_flow(rows, start=_WEEK_START, end=_WEEK_END)
    assert result["sdr"] == []


def test_author_and_highlights_are_carried_through():
    rows = [
        _row(
            memo_id="m1",
            author="Carlos",
            evidence=[{"start_ms": 1500, "label": "El precio es alto"}],
        ),
    ]
    result = best_by_flow(rows, start=_WEEK_START, end=_WEEK_END)
    item = result["sdr"][0]
    assert item["author"] == "Carlos"
    assert item["highlights"] == ["min 00:01 · El precio es alto"]
    assert item["value"] == 8
