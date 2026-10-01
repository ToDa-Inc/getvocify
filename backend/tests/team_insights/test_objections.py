"""F15 objection rollups: kind objection only, superseded rows excluded."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-obj-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-obj-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.team_insights.objections import objection_counts
from tests.reporting.fake_db import FakeDB

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
    resolution: str | None = None,
    response: str | None = None,
) -> dict:
    row: dict = {"category": category, "kind": kind, "superseded": superseded}
    if observed_at is not None:
        row["observed_at"] = observed_at
    if created_at is not None:
        row["created_at"] = created_at
    if resolution is not None:
        row["resolution"] = resolution
    if response is not None:
        row["response"] = response
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
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == [
        {"name": "price", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
    ]


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
        {"name": "timing", "count": 3, "resolved": 0, "open": 0, "unknown": 3},
        {"name": "authority", "count": 2, "resolved": 0, "open": 0, "unknown": 2},
        {"name": "price", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
    ]


def test_objection_keys_stay_stable():
    rows = [
        _row(category="status_quo"),
        _row(category="trust"),
        _row(category="competitor"),
        _row(category="other"),
        _row(category="not_a_real_key"),
    ]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END)
    assert {item["name"] for item in result} == {
        "status_quo",
        "trust",
        "competitor",
        "other",
        "not_a_real_key",
    }
    assert result == [
        {"name": "competitor", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
        {"name": "not_a_real_key", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
        {"name": "other", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
        {"name": "status_quo", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
        {"name": "trust", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
    ]


def test_objection_outside_madrid_week_is_excluded():
    rows = [
        _row(category="price", observed_at=_OUT_WEEK),
        _row(category="timing"),
        _row(category="authority", observed_at=None, created_at=_OUT_WEEK),
    ]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == [
        {"name": "timing", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
    ]


def test_objection_without_date_is_ignored():
    rows = [_row(category="price", observed_at=None, created_at=None)]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == []


def test_objection_counts_resolution_per_category_without_inferring():
    rows = [
        _row(category="price", resolution="resolved"),
        _row(category="price", resolution="open"),
        _row(category="price"),
        _row(category="timing", resolution="unknown"),
        _row(category="timing", resolution="not_a_resolution"),
    ]
    assert objection_counts(rows, start=_WEEK_START, end=_WEEK_END) == [
        {"name": "price", "count": 3, "resolved": 1, "open": 1, "unknown": 1},
        {"name": "timing", "count": 2, "resolved": 0, "open": 0, "unknown": 2},
    ]


def test_how_to_comes_from_the_published_playbook_entry_for_that_category():
    rows = [_row(category="price")]
    entries = [
        {"category": "price", "guidance": "Ancla en el ROI, no en el descuento."},
        {"category": "timing", "guidance": "Pregunta qué cambiaría en 3 meses."},
    ]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END, playbook_entries=entries, include_guidance=True)
    assert result == [
        {
            "name": "price", "count": 1, "resolved": 0, "open": 0, "unknown": 1,
            "how_to": "Ancla en el ROI, no en el descuento.", "best_example": None,
        },
    ]


def test_how_to_is_none_without_a_matching_playbook_entry():
    rows = [_row(category="price")]
    entries = [{"category": "timing", "guidance": "Pregunta qué cambiaría en 3 meses."}]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END, playbook_entries=entries, include_guidance=True)
    assert result[0]["how_to"] is None


def test_best_example_is_the_most_recent_resolved_response():
    rows = [
        _row(category="price", resolution="resolved", observed_at="2026-09-22T10:00:00Z", response="Le mostré el ROI a 6 meses."),
        _row(category="price", resolution="resolved", observed_at="2026-09-23T10:00:00Z", response="Comparamos el coste total, no solo la licencia."),
        _row(category="price", resolution="open", observed_at="2026-09-24T10:00:00Z", response="Sin respuesta clara todavía."),
    ]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END, include_guidance=True)
    assert result[0]["best_example"] == "Comparamos el coste total, no solo la licencia."


def test_best_example_ignores_unresolved_and_empty_responses():
    rows = [
        _row(category="price", resolution="resolved", response=""),
        _row(category="price", resolution="open", response="No cuenta, sigue abierta."),
    ]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END, include_guidance=True)
    assert result[0]["best_example"] is None


def test_include_guidance_false_omits_how_to_and_best_example_keys():
    rows = [_row(category="price", resolution="resolved", response="Le mostré el ROI.")]
    result = objection_counts(rows, start=_WEEK_START, end=_WEEK_END)
    assert result == [{"name": "price", "count": 1, "resolved": 1, "open": 0, "unknown": 0}]
    assert "how_to" not in result[0]
    assert "best_example" not in result[0]


_COMPANY = "44444444-4444-4444-4444-444444444444"
_ADMIN = "55555555-5555-5555-5555-555555555555"


@pytest.fixture(autouse=True)
def _reset_team_loader_and_flags():
    from app.services import feature_flags

    feature_flags.clear_cache()
    yield
    team_api.set_team_adherence_loader(None)
    feature_flags.clear_cache()


def _adherence_client(inputs: dict, *, flags: list[dict] | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(team_api.router)
    store = FakeDB({"company_feature_flags": flags or []})
    team_api.set_team_adherence_loader(lambda *_args: inputs)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=_COMPANY, user_id=_ADMIN, role="admin", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def _guidance_inputs() -> dict:
    return {
        "parts": [],
        "playbook_present": True,
        "sample_size": 0,
        "activity_rows": [],
        "activity_period_start": _WEEK_START,
        "activity_period_end": _WEEK_END,
        "pattern_rows": [_row(category="price", resolution="resolved", response="Le mostré el ROI.")],
        "playbook_entries": [{"category": "price", "guidance": "Ancla en el ROI."}],
        "reps": [],
        "review": [],
        "outcome_observations": None,
        "outcome_user_id": None,
        "memo_rows": [],
    }


def test_playbook_tab_flag_off_keeps_objection_categories_in_the_old_shape():
    client = _adherence_client(_guidance_inputs())
    body = client.get("/api/v1/team/adherence").json()
    category = body["objection_categories"][0]
    assert "how_to" not in category
    assert "best_example" not in category


def test_playbook_tab_flag_on_adds_how_to_and_best_example():
    flags = [{"company_id": _COMPANY, "flag": "PLAYBOOK_TAB_ENABLED", "enabled": True}]
    client = _adherence_client(_guidance_inputs(), flags=flags)
    body = client.get("/api/v1/team/adherence").json()
    category = body["objection_categories"][0]
    assert category["how_to"] == "Ancla en el ROI."
    assert category["best_example"] == "Le mostré el ROI."


def test_the_best_example_is_the_text_people_read_not_its_storage():
    from app.services.team_insights.objections import response_text
    assert response_text('{"text": "Te lo enseño en 20 minutos."}') == "Te lo enseño en 20 minutos."
    assert response_text({"text": "Vale,  sin problema."}) == "Vale, sin problema."
    long = "Mira, lo entiendo. " * 30
    assert len(response_text(long)) <= 245 and response_text(long).endswith("…")
