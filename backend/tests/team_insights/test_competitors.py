"""F15 E8: named competitors from current C04 intelligence, gated by TEAM_COMPETITORS_ENABLED."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-competitors-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-competitors-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.reporting.periodic import ensure_team_weekly_report
from app.services.reporting.presentation import email_html_for_snapshot
from app.services.reporting.weekly import week_bounds
from app.services.intelligence.extract import PROMPT_VERSION
from app.services.team_insights.aggregate import load_team_adherence_inputs
from app.services.team_insights.competitors import competitor_counts, normalize_competitor_name
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
MADRID = "Europe/Madrid"
FRIDAY = datetime(2026, 9, 25, 16, 5, tzinfo=UTC)
COMPANY = "88888888-8888-8888-8888-888888888888"
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REP = "99999999-9999-9999-9999-999999999999"
_WEEK_START = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)
_WEEK_END = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)
_IN_WEEK = "2026-09-22T10:00:00+00:00"
_OUT_WEEK = "2026-09-15T10:00:00+00:00"
_REVISION = "rev-current"


@pytest.fixture(autouse=True)
def fresh_flags():
    from app.services import feature_flags

    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


@pytest.fixture(autouse=True)
def reset_team_loader():
    yield
    team_api.set_team_adherence_loader(None)


def _memo(
    memo_id: str,
    *,
    mentions: list | None = None,
    revision: str = _REVISION,
    at: str = _IN_WEEK,
    stale: bool = False,
) -> dict:
    intelligence = {
        "version": 1,
        "prompt_version": PROMPT_VERSION,
        "input_revision": "rev-stale" if stale else revision,
        "status": "ready",
        "competitor_mentions": mentions or [],
    }
    extraction = {"summary": "call", "intelligence": intelligence}
    return {
        "id": memo_id,
        "company_id": COMPANY,
        "user_id": REP,
        "capture_started_at": at,
        "created_at": at,
        "extraction": extraction,
        "notes_revision": None,
        "playbook_version_id": None,
    }


def _revision_inputs(memos: list[dict]) -> dict:
    from app.services.intelligence.worker import revision_for_memo

    for memo in memos:
        block = memo["extraction"]["intelligence"]
        block["input_revision"] = revision_for_memo(memo)
    return {
        "parts": [{"met_steps": 1, "missed_steps": 0, "unknown_steps": 0, "not_applicable_steps": 9,
                   "observed_at": _IN_WEEK}],
        "playbook_present": True,
        "sample_size": 1,
        "activity_rows": [{"observed_at": _IN_WEEK, "screening": "connected", "meeting_agreed": False}],
        "activity_period_start": _WEEK_START,
        "activity_period_end": _WEEK_END,
        "pattern_rows": [],
        "reps": [{"userId": REP, "name": "Ana"}],
        "review": [],
        "outcome_observations": None,
        "outcome_user_id": None,
        "memo_rows": memos,
    }


def test_competitors_aggregate_and_sort_by_count():
    memos = [
        _memo("m1", mentions=[{"name": "Acme"}, {"name": "  acme  "}]),
        _memo("m2", mentions=[{"name": "HubSpot"}]),
        _memo("m3", mentions=[{"name": "Acme"}]),
    ]
    _revision_inputs(memos)
    assert competitor_counts(memos, start=_WEEK_START, end=_WEEK_END) == [
        {"name": "ACME", "count": 2},
        {"name": "HUBSPOT", "count": 1},
    ]
    assert normalize_competitor_name("  acme  ") == "ACME"


def test_stale_intelligence_does_not_count():
    memos = [_memo("m1", mentions=[{"name": "Acme"}], stale=True)]
    assert competitor_counts(memos, start=_WEEK_START, end=_WEEK_END) == []


def test_empty_competitor_names_yield_no_rows():
    memos = [_memo("m1", mentions=[{"name": ""}, {"name": "   "}, {}])]
    _revision_inputs(memos)
    assert competitor_counts(memos, start=_WEEK_START, end=_WEEK_END) == []


def test_plain_string_competitor_mentions_are_counted():
    memos = [_memo("m1", mentions=["Acme", {"name": "HubSpot"}])]
    _revision_inputs(memos)
    assert competitor_counts(memos, start=_WEEK_START, end=_WEEK_END) == [
        {"name": "ACME", "count": 1},
        {"name": "HUBSPOT", "count": 1},
    ]


def test_competitors_outside_the_period_are_excluded():
    memos = [_memo("m1", mentions=[{"name": "Acme"}], at=_OUT_WEEK)]
    _revision_inputs(memos)
    assert competitor_counts(memos, start=_WEEK_START, end=_WEEK_END) == []


def test_competitors_respect_sample_limited():
    from app.services.team_insights.aggregate import team_adherence

    memos = [_memo("m1", mentions=[{"name": "Acme"}])]
    inputs = _revision_inputs(memos)
    body = team_adherence(role="admin", **inputs)
    assert body["sample_limited"] is True
    assert body["competitor_mentions"] == [{"name": "ACME", "count": 1}]


def _panel_client(inputs: dict, *, flags: list[dict] | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(team_api.router)
    store = FakeDB({
        "company_feature_flags": flags or [],
        "memos": [],
        "memo_scores": [],
        "interaction_patterns": [],
        "playbooks": [],
        "team_outcome_observations": [],
        "company_members": [{"company_id": COMPANY, "user_id": ADMIN, "role": "admin", "status": "active"}],
    })

    def loader(_supabase, company_id, user_id, motion):
        return inputs

    team_api.set_team_adherence_loader(loader)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=ADMIN, role="admin", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def test_flag_off_omits_competitors_from_api():
    memos = [_memo("m1", mentions=[{"name": "Acme"}])]
    inputs = _revision_inputs(memos)
    client = _panel_client(inputs)
    body = client.get("/api/v1/team/adherence").json()
    assert "competitor_mentions" not in body


def test_flag_on_includes_competitors_in_api():
    memos = [_memo("m1", mentions=[{"name": "Acme"}])]
    inputs = _revision_inputs(memos)
    flags = [{"company_id": COMPANY, "flag": "TEAM_COMPETITORS_ENABLED", "enabled": True}]
    client = _panel_client(inputs, flags=flags)
    body = client.get("/api/v1/team/adherence").json()
    assert body["competitor_mentions"] == [{"name": "ACME", "count": 1}]


class _LoaderResult:
    def __init__(self, data):
        self.data = data


class _LoaderQuery:
    def __init__(self, store, name: str):
        self._store = store
        self._name = name
        self._columns: list[str] | None = None
        self._filters: list[tuple[str, object]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._limit: int | None = None

    def select(self, columns: str, **_kwargs):
        self._columns = [column.strip() for column in columns.split(",")]
        known = self._store.schema.get(self._name)
        unknown = [c for c in self._columns if known is not None and c != "*" and c not in known]
        if unknown:
            raise RuntimeError(f"42703 column {self._name}.{unknown[0]} does not exist")
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def or_(self, expression: str):
        self._or = expression
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._name, []))
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column)) in allowed]
        expression = getattr(self, "_or", None)
        if expression:
            wanted = [part.split(".", 2) for part in expression.split(",")]

            def keep(row):
                for column, op, value in wanted:
                    if op == "eq" and str(row.get(column)) == value:
                        return True
                    if op == "is" and value == "null" and row.get(column) is None:
                        return True
                return False

            rows = [row for row in rows if keep(row)]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._columns:
            rows = [{column: row.get(column) for column in self._columns} for row in rows]
        return _LoaderResult(rows)


# Real memos columns: notes_revision is read by revision_for_memo but is not a column.
_MEMOS_SCHEMA = frozenset({
    "id", "user_id", "company_id", "source", "source_type", "interaction_kind",
    "screening_outcome", "capture_started_at", "created_at", "approved_at",
    "hubspot_contact_id", "hubspot_deal_id", "matched_deal_id", "extraction",
    "followup", "playbook_version_id", "sales_motion_key",
})


class _LoaderSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.schema = {"memos": _MEMOS_SCHEMA}

    def table(self, name: str):
        return _LoaderQuery(self, name)


def test_loader_revision_columns_keep_competitors_current():
    from app.services.intelligence.worker import revision_for_memo

    memo = _memo("m-loader", mentions=[{"name": "Acme"}])
    memo["extraction"]["intelligence"]["input_revision"] = revision_for_memo(memo)
    store = _LoaderSupabase(
        {
            "memos": [memo],
            "memo_scores": [],
            "interaction_patterns": [],
            "playbooks": [],
            "company_members": [
                {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
            ],
            "user_profiles": [{"id": REP, "full_name": "Ana"}],
            "team_outcome_observations": [],
        }
    )
    inputs = load_team_adherence_inputs(store, COMPANY)
    assert competitor_counts(
        inputs["memo_rows"],
        start=_WEEK_START,
        end=_WEEK_END,
    ) == [{"name": "ACME", "count": 1}]


def _team_db(*, flags: dict) -> FakeDB:
    flag_rows = [{"company_id": COMPANY, "flag": name, "enabled": value} for name, value in flags.items()]
    return FakeDB({
        "memos": [MONDAY_MEMO],
        "interaction_patterns": [],
        "reports": [],
        "report_notifications": [],
        "report_preferences": [],
        "brief_preferences": [],
        "team_outcome_observations": [],
        "company_feature_flags": flag_rows,
        "company_members": [
            {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
            {"company_id": COMPANY, "user_id": ADMIN, "role": "admin", "status": "active"},
        ],
    })


MONDAY_MEMO = {
    "id": "m-mon",
    "company_id": COMPANY,
    "user_id": REP,
    "screening_outcome": "connected",
    "capture_started_at": "2026-09-21T08:00:00+00:00",
    "created_at": "2026-09-21T08:00:00+00:00",
    "extraction": {"intelligence": {"meeting": {"agreed": True}}},
}


def _load(inputs):
    def loader(_supabase, company_id):
        return {**inputs, "activity_period_start": week_bounds(FRIDAY, MADRID)[0],
                "activity_period_end": week_bounds(FRIDAY, MADRID)[1]}

    return loader


def test_team_report_email_includes_competitors_when_flag_on():
    memos = [_memo("m1", mentions=[{"name": "Acme"}, {"name": "HubSpot"}])]
    inputs = _revision_inputs(memos)
    db = _team_db(flags={"REPORTING_TEAM_ENABLED": True, "TEAM_COMPETITORS_ENABLED": True})
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY, load_inputs=_load(inputs),
    )
    snap = [row for row in db.tables["reports"] if row["id"] == report_id][0]["snapshot"]
    html = email_html_for_snapshot(snap, report_id=report_id)
    assert "Competidores mencionados" in html
    assert "ACME" in html
    assert "HUBSPOT" in html


def test_team_report_email_omits_competitors_when_flag_off():
    memos = [_memo("m1", mentions=[{"name": "Acme"}])]
    inputs = _revision_inputs(memos)
    db = _team_db(flags={"REPORTING_TEAM_ENABLED": True})
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY, load_inputs=_load(inputs),
    )
    snap = [row for row in db.tables["reports"] if row["id"] == report_id][0]["snapshot"]
    html = email_html_for_snapshot(snap, report_id=report_id)
    assert "Competidores mencionados" not in html
    assert "competitors" not in snap
