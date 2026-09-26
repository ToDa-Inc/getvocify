"""F13.04 / F15.05: one weekly report per person, scope and week; team reports only for owner/admin."""

import json
import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")

import pytest

from app.services import feature_flags
from app.services.reporting.daily_snapshot import ensure_self_daily_reports_for_due_tick
from app.services.reporting.periodic import ensure_team_weekly_report, ensure_weekly_reports_for_tick
from app.services.reporting.weekly import week_bounds
from app.services.team_insights.aggregate import team_adherence
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
MADRID = "Europe/Madrid"
FRIDAY_1805 = datetime(2026, 9, 25, 16, 5, tzinfo=UTC)
FRIDAY_1759 = datetime(2026, 9, 25, 15, 59, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
COMPANY = "88888888-8888-8888-8888-888888888888"
OTHER_COMPANY = "77777777-7777-7777-7777-777777777777"
REP = "99999999-9999-9999-9999-999999999999"
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OWNER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
GONE = "cccccccc-cccc-cccc-cccc-cccccccccccc"


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _memo(memo_id: str, at: str, *, user_id: str = REP, screening: str = "connected", meeting: bool = False) -> dict:
    intel = {"meeting": {"agreed": True}} if meeting else {}
    return {
        "id": memo_id,
        "company_id": COMPANY,
        "user_id": user_id,
        "screening_outcome": screening,
        "capture_started_at": at,
        "created_at": at,
        "extraction": {"intelligence": intel},
    }


MONDAY_MEMO = _memo("m-mon", "2026-09-21T08:00:00+00:00", meeting=True)


def _flags(**flags) -> list[dict]:
    return [{"company_id": COMPANY, "flag": name, "enabled": value} for name, value in flags.items()]


def _db(*, flags=None, memos=None, prefs=None, members=None, extra=None) -> FakeDB:
    tables = {
        "memos": [MONDAY_MEMO] if memos is None else memos,
        "interaction_patterns": [],
        "reports": [],
        "report_notifications": [],
        "report_preferences": prefs or [],
        "brief_preferences": [],
        "team_outcome_observations": [],
        "company_feature_flags": flags if flags is not None else _flags(REPORTING_WEEKLY_ENABLED=True),
        "company_members": members or [
            {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
        ],
    }
    tables.update(extra or {})
    return FakeDB(tables)


def _reports(db: FakeDB, **match) -> list[dict]:
    return [row for row in db.tables["reports"] if all(row.get(k) == v for k, v in match.items())]


def test_friday_and_saturday_ticks_create_one_weekly_report_and_one_notification():
    db = _db()
    ensure_weekly_reports_for_tick(db, FRIDAY_1805)
    ensure_weekly_reports_for_tick(db, SATURDAY)
    weekly = _reports(db, report_type="weekly")
    assert len(weekly) == 1
    start, _ = week_bounds(FRIDAY_1805, MADRID)
    assert weekly[0]["scope"] == "self"
    assert weekly[0]["user_id"] == REP
    assert weekly[0]["period_start"] == start.isoformat()
    assert weekly[0]["snapshot"]["generated_at"] == FRIDAY_1805.isoformat()
    assert weekly[0]["snapshot"]["metrics"]["meetings_agreed"] == 1
    notes = [n for n in db.tables["report_notifications"] if n["report_id"] == weekly[0]["id"]]
    assert len(notes) == 1
    assert notes[0]["user_id"] == REP
    assert notes[0]["read_at"] is None


def test_before_friday_1800_local_nothing_is_generated():
    db = _db()
    ensure_weekly_reports_for_tick(db, FRIDAY_1759)
    assert _reports(db, report_type="weekly") == []


def test_flag_off_generates_nothing():
    db = _db(flags=[])
    ensure_weekly_reports_for_tick(db, FRIDAY_1805)
    assert db.tables["reports"] == []


def test_another_companys_flag_does_not_turn_it_on():
    db = _db(flags=[{"company_id": OTHER_COMPANY, "flag": "REPORTING_WEEKLY_ENABLED", "enabled": True}])
    ensure_weekly_reports_for_tick(db, FRIDAY_1805)
    assert db.tables["reports"] == []


def test_weekly_preference_off_generates_nothing():
    db = _db(prefs=[{"user_id": REP, "daily_enabled": True, "weekly_enabled": False, "team_enabled": True}])
    ensure_weekly_reports_for_tick(db, FRIDAY_1805)
    assert db.tables["reports"] == []


def test_a_week_without_activity_has_no_report():
    db = _db(memos=[_memo("m-last-week", "2026-09-19T08:00:00+00:00")])
    ensure_weekly_reports_for_tick(db, FRIDAY_1805)
    assert db.tables["reports"] == []


def test_monday_daily_and_weekly_are_two_different_reports():
    start, _ = week_bounds(FRIDAY_1805, MADRID)
    daily = {
        "id": "daily-monday",
        "company_id": COMPANY,
        "user_id": REP,
        "scope": "self",
        "period_start": start.isoformat(),
        "report_type": "daily",
        "revision": 1,
        "snapshot": {},
    }
    db = _db(extra={"reports": [daily]})
    ensure_weekly_reports_for_tick(db, FRIDAY_1805)
    assert len(_reports(db, period_start=start.isoformat())) == 2
    assert _reports(db, id="daily-monday")[0]["snapshot"] == {}


def test_daily_preference_off_skips_the_daily_report():
    db = _db(
        memos=[_memo("m-today", "2026-09-22T10:00:00+00:00")],
        prefs=[{"user_id": REP, "daily_enabled": False, "weekly_enabled": True, "team_enabled": True}],
    )
    ensure_self_daily_reports_for_due_tick(db, datetime(2026, 9, 22, 16, 0, tzinfo=UTC))
    assert db.tables["reports"] == []


def test_daily_preference_on_by_default_still_builds_the_daily_report():
    db = _db(memos=[_memo("m-today", "2026-09-22T10:00:00+00:00")])
    ensure_self_daily_reports_for_due_tick(db, datetime(2026, 9, 22, 16, 0, tzinfo=UTC))
    assert len(_reports(db, report_type="daily")) == 1


# ---------- team ----------

TEAM_INPUTS = {
    "parts": [
        {"met_steps": 2, "missed_steps": 8, "unknown_steps": 0, "not_applicable_steps": 0,
         "observed_at": "2026-09-21T08:10:00+00:00"},
        {"met_steps": 5, "missed_steps": 0, "unknown_steps": 0, "not_applicable_steps": 0,
         "observed_at": "2026-09-14T08:10:00+00:00"},
    ],
    "playbook_present": True,
    "sample_size": 2,
    "activity_rows": [
        {"observed_at": "2026-09-21T08:00:00+00:00", "screening": "connected", "meeting_agreed": True},
        {"observed_at": "2026-09-22T08:00:00+00:00", "screening": "voicemail", "meeting_agreed": False},
        {"observed_at": "2026-09-24T08:00:00+00:00", "screening": "connected", "meeting_agreed": False},
        {"observed_at": "2026-09-15T08:00:00+00:00", "screening": "connected", "meeting_agreed": True},
    ],
    "pattern_rows": [
        {"category": "price", "kind": "objection", "resolution": "open", "superseded": False,
         "created_at": "2026-09-21T08:05:00+00:00"},
        {"category": "trust", "kind": "objection", "resolution": "resolved", "superseded": False,
         "created_at": "2026-09-24T08:05:00+00:00"},
    ],
    "reps": [{"userId": REP, "name": "Ana Rep"}],
    "review": [{"memo_id": "m-mon", "line": "Ana habló con Acme"}],
    "outcome_observations": [
        {"connection_id": "c", "deal_id": "d", "status": "won", "owner_user_id": REP,
         "attribution": "assigned", "observed_at": "2026-09-22T08:00:00+00:00"},
    ],
    "outcome_user_id": None,
}

EMPTY_TEAM_INPUTS = {
    **TEAM_INPUTS,
    "parts": [],
    "activity_rows": [],
    "pattern_rows": [],
}


def _load(inputs):
    calls = []

    def loader(_supabase, company_id):
        calls.append(company_id)
        return {**inputs}

    loader.calls = calls
    return loader


TEAM_MEMBERS = [
    {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
    {"company_id": COMPANY, "user_id": ADMIN, "role": "admin", "status": "active"},
    {"company_id": COMPANY, "user_id": OWNER, "role": "owner", "status": "active"},
    {"company_id": COMPANY, "user_id": GONE, "role": "admin", "status": "removed"},
]


def test_team_report_numbers_equal_the_panel_for_the_same_week():
    start, end = week_bounds(FRIDAY_1805, MADRID)
    panel = team_adherence(role="admin", **TEAM_INPUTS, activity_period_start=start, activity_period_end=end)
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY_1805,
        load_inputs=_load(TEAM_INPUTS),
    )
    row = _reports(db, id=report_id)[0]
    snap = row["snapshot"]
    assert row["scope"] == "team"
    assert row["report_type"] == "weekly"
    assert row["user_id"] == ADMIN
    assert snap["scope"] == "team"
    assert snap["metrics"]["attempts"] == panel["attempts"] == 3
    assert snap["metrics"]["connected_calls"] == panel["connected"] == 2
    assert snap["metrics"]["meetings_agreed"] == panel["meetings"] == 1
    assert snap["metrics"]["adherence"] == panel["adherence"]
    assert snap["adherence_steps"] == {"met": panel["met_steps"], "applicable": panel["applicable_steps"]}
    assert snap["objections"] == panel["objection_categories"][:3]
    assert snap["metrics"]["deals_won"] is None
    assert snap["coverage"]["crm_outcomes"] == "unavailable"
    assert [day["connected_calls"] for day in snap["series"]] == [1, 0, 0, 1, 0]


def test_team_snapshot_carries_no_per_rep_data():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY_1805,
        load_inputs=_load(TEAM_INPUTS),
    )
    snap = _reports(db, id=report_id)[0]["snapshot"]
    dumped = json.dumps(snap)
    assert REP not in dumped
    assert "Ana Rep" not in dumped
    assert "reps" not in snap
    assert "review" not in snap


def _week(state: str, met: int = 0, applicable: int = 0, *, sample_limited: bool = False) -> dict:
    return {"week_start": "x", "state": state, "met_steps": met, "applicable_steps": applicable,
            "sample_limited": sample_limited, "interactions": 3, "adherence": None}


TREND = {
    "coverage": "complete",
    "weeks": [{"week_start": d} for d in ("2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21")],
    "team": {"weeks": [_week("gap"), _week("scored", 6, 10), _week("unscored"), _week("scored", 9, 12)]},
    "reps": [
        {"user_id": REP, "name": "Ana Rep", "weeks": [_week("gap"), _week("scored", 6, 10),
                                                       _week("unscored"), _week("scored", 4, 5, sample_limited=True)]},
        {"user_id": ADMIN, "name": "Bruno Admin", "weeks": [_week("gap"), _week("gap"), _week("gap"),
                                                             _week("scored", 5, 7, sample_limited=True)]},
    ],
}


def _trend(result):
    calls = []

    def loader(_supabase, company_id, **kwargs):
        calls.append((company_id, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    loader.calls = calls
    return loader


def test_team_report_carries_weekly_adherence_per_rep_when_the_trend_flag_is_on():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True, TEAM_ADHERENCE_TREND_ENABLED=True))
    loader = _trend(TREND)
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY_1805,
        load_inputs=_load(TEAM_INPUTS), load_trend=loader,
    )
    snap = _reports(db, id=report_id)[0]["snapshot"]
    trend = snap["adherence_trend"]
    assert trend["weeks"] == ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21"]
    assert trend["team"][1] == {"state": "scored", "met": 6, "applicable": 10, "sample_limited": False}
    assert [row["name"] for row in trend["reps"]] == ["Ana Rep", "Bruno Admin"]
    assert trend["reps"][0]["weeks"][3] == {"state": "scored", "met": 4, "applicable": 5, "sample_limited": True}
    assert trend["reps"][1]["weeks"][0]["state"] == "gap"
    assert REP not in json.dumps(snap)
    assert loader.calls == [(COMPANY, {"role": "admin", "now": FRIDAY_1805, "tz_name": MADRID, "weeks": 4})]


def test_team_report_has_no_trend_when_the_trend_flag_is_off():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    loader = _trend(TREND)
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY_1805,
        load_inputs=_load(TEAM_INPUTS), load_trend=loader,
    )
    assert "adherence_trend" not in _reports(db, id=report_id)[0]["snapshot"]
    assert loader.calls == []


@pytest.mark.parametrize("result", [RuntimeError("read failed"), {**TREND, "coverage": "unavailable"}])
def test_a_failed_trend_read_still_sends_the_team_report_without_it(result):
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True, TEAM_ADHERENCE_TREND_ENABLED=True))
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY_1805,
        load_inputs=_load(TEAM_INPUTS), load_trend=_trend(result),
    )
    snap = _reports(db, id=report_id)[0]["snapshot"]
    assert "adherence_trend" not in snap
    assert snap["metrics"]["connected_calls"] == 2


def test_a_member_never_gets_a_team_report():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    loader = _load(TEAM_INPUTS)
    result = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=FRIDAY_1805, load_inputs=loader,
    )
    assert result is None
    assert db.tables["reports"] == []
    assert loader.calls == []


def test_tick_creates_team_reports_for_active_owner_and_admin_only():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    ensure_weekly_reports_for_tick(db, FRIDAY_1805, load_team_inputs=_load(TEAM_INPUTS))
    team = _reports(db, scope="team")
    assert sorted(row["user_id"] for row in team) == sorted([ADMIN, OWNER])
    assert _reports(db, scope="self") == []
    notified = sorted(n["user_id"] for n in db.tables["report_notifications"])
    assert notified == sorted([ADMIN, OWNER])


def test_team_tick_twice_keeps_one_report_per_admin():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    ensure_weekly_reports_for_tick(db, FRIDAY_1805, load_team_inputs=_load(TEAM_INPUTS))
    ensure_weekly_reports_for_tick(db, SATURDAY, load_team_inputs=_load(TEAM_INPUTS))
    assert len(_reports(db, scope="team")) == 2
    assert len(db.tables["report_notifications"]) == 2


def test_team_flag_off_generates_no_team_report():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_WEEKLY_ENABLED=True))
    loader = _load(TEAM_INPUTS)
    ensure_weekly_reports_for_tick(db, FRIDAY_1805, load_team_inputs=loader)
    assert _reports(db, scope="team") == []
    assert loader.calls == []


def test_team_preference_off_skips_that_admin():
    db = _db(
        members=TEAM_MEMBERS,
        flags=_flags(REPORTING_TEAM_ENABLED=True),
        prefs=[{"user_id": ADMIN, "daily_enabled": True, "weekly_enabled": True, "team_enabled": False}],
    )
    ensure_weekly_reports_for_tick(db, FRIDAY_1805, load_team_inputs=_load(TEAM_INPUTS))
    assert [row["user_id"] for row in _reports(db, scope="team")] == [OWNER]


def test_a_team_week_without_activity_has_no_report():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    ensure_weekly_reports_for_tick(db, FRIDAY_1805, load_team_inputs=_load(EMPTY_TEAM_INPUTS))
    assert _reports(db, scope="team") == []


def test_team_without_playbook_has_null_adherence():
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True))
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=FRIDAY_1805,
        load_inputs=_load({**TEAM_INPUTS, "playbook_present": False}),
    )
    snap = _reports(db, id=report_id)[0]["snapshot"]
    assert snap["metrics"]["adherence"] is None
    assert snap["adherence_steps"] is None
    assert snap["metrics"]["connected_calls"] == 2
