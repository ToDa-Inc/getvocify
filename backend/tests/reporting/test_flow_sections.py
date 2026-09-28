"""T12: daily/weekly reports pick sections by sales_role (REPORTING_BY_FLOW_ENABLED)."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-flow-sections-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-flow-sections-32")

import pytest

from app.services import feature_flags
from app.services.reporting.aggregate import build_snapshot, flow_sections
from app.services.reporting.daily_snapshot import ensure_self_daily_report
from app.services.reporting.periodic import ensure_self_weekly_report
from app.services.reporting.weekly import week_bounds
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
MADRID = "Europe/Madrid"
COMPANY = "88888888-8888-8888-8888-888888888888"
USER = "99999999-9999-9999-9999-999999999999"
AE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NOW = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)
FRIDAY_1805 = datetime(2026, 9, 25, 16, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def test_flow_sections_pure_mapping():
    assert flow_sections("sdr") == ["attempts", "connected_calls", "meetings_agreed", "handoffs"]
    assert flow_sections("ae") == ["meetings_held", "deals_in_progress", "proposals_sent", "deals_won"]
    both = flow_sections("general")
    assert set(both) == {
        "attempts", "connected_calls", "meetings_agreed", "handoffs",
        "meetings_held", "deals_in_progress", "proposals_sent", "deals_won",
    }
    # D1: null/unknown behaves exactly like general.
    assert flow_sections(None) == both
    assert flow_sections("nonsense") == both


def _base_kwargs(**overrides):
    base = dict(
        scope="self",
        period_start="2026-09-21T22:00:00Z",
        period_end="2026-09-22T22:00:00Z",
        timezone=MADRID,
        interactions=[],
        outcomes={"coverage": "unavailable"},
    )
    base.update(overrides)
    return base


def test_build_snapshot_without_sales_role_is_unchanged():
    snapshot = build_snapshot(**_base_kwargs())
    assert "sections" not in snapshot
    for key in ("handoffs", "meetings_held", "deals_in_progress", "proposals_sent"):
        assert key not in snapshot["metrics"]


def test_build_snapshot_with_sales_role_adds_sections_and_flow_metrics():
    snapshot = build_snapshot(**_base_kwargs(
        sales_role="sdr",
        flow_facts={"handoffs": 2, "meetings_held": 0, "deals_in_progress": 0, "proposals_sent": 0},
    ))
    assert snapshot["sections"] == ["attempts", "connected_calls", "meetings_agreed", "handoffs"]
    assert snapshot["metrics"]["handoffs"] == 2


def _memo(memo_id, *, motion=None, followup_status=None, interaction_kind="call"):
    at = "2026-09-22T10:00:00+00:00"
    memo = {
        "id": memo_id,
        "company_id": COMPANY,
        "user_id": AE,
        "screening_outcome": "connected",
        "interaction_kind": interaction_kind,
        "capture_started_at": at,
        "created_at": at,
        "extraction": {},
        "sales_motion_key": motion,
    }
    if followup_status is not None:
        memo["followup"] = {"status": followup_status, "channel": "vocify_email"}
    return memo


def _db(**tables):
    base = {
        "memos": [],
        "reports": [],
        "report_notifications": [],
        "team_outcome_observations": [],
        "deal_handoffs": [],
        "company_members": [],
        "company_feature_flags": [],
    }
    base.update(tables)
    return FakeDB(base)


def test_daily_report_off_flag_has_no_flow_fields():
    db = _db(memos=[_memo("m-1", motion="closing", followup_status="sent", interaction_kind="meeting")])
    ensure_self_daily_report(db, company_id=COMPANY, user_id=AE, timezone=MADRID, now=NOW)
    snap = db.tables["reports"][0]["snapshot"]
    assert "sections" not in snap
    assert "proposals_sent" not in snap["metrics"]


def test_daily_report_ae_sees_meetings_held_and_proposals_sent():
    db = _db(
        memos=[
            _memo("m-1", motion="closing", followup_status="sent", interaction_kind="meeting"),
            _memo("m-2", motion="discovery", interaction_kind="call"),
        ],
        company_members=[{"id": "mem-ae", "company_id": COMPANY, "user_id": AE, "role": "member", "status": "active",
                           "sales_role": "ae", "handoff_ae_user_id": None, "visibility": "own"}],
        deal_handoffs=[{"id": "h-1", "company_id": COMPANY, "ae_user_id": AE, "sdr_user_id": USER,
                        "status": "active", "connection_id": "c-1", "contact_id": "ct-1", "created_at": "2026-09-20T00:00:00+00:00"}],
        company_feature_flags=[{"company_id": COMPANY, "flag": "REPORTING_BY_FLOW_ENABLED", "enabled": True}],
    )
    ensure_self_daily_report(db, company_id=COMPANY, user_id=AE, timezone=MADRID, now=NOW)
    snap = db.tables["reports"][0]["snapshot"]
    assert snap["sections"] == ["meetings_held", "deals_in_progress", "proposals_sent", "deals_won"]
    assert snap["metrics"]["meetings_held"] == 1
    assert snap["metrics"]["proposals_sent"] == 1
    assert snap["metrics"]["deals_in_progress"] == 1


def test_daily_report_sdr_sees_handoffs_created_in_period():
    db = _db(
        memos=[_memo("m-1", interaction_kind="call")],
        company_members=[{"id": "mem-sdr", "company_id": COMPANY, "user_id": AE, "role": "member", "status": "active",
                           "sales_role": "sdr", "handoff_ae_user_id": USER, "visibility": "own"}],
        deal_handoffs=[
            {"id": "h-1", "company_id": COMPANY, "sdr_user_id": AE, "ae_user_id": USER, "status": "active",
             "connection_id": "c-1", "contact_id": "ct-1", "created_at": "2026-09-22T09:00:00+00:00"},
            {"id": "h-2", "company_id": COMPANY, "sdr_user_id": AE, "ae_user_id": USER, "status": "closed",
             "connection_id": "c-2", "contact_id": "ct-2", "created_at": "2026-09-19T09:00:00+00:00"},
        ],
        company_feature_flags=[{"company_id": COMPANY, "flag": "REPORTING_BY_FLOW_ENABLED", "enabled": True}],
    )
    ensure_self_daily_report(db, company_id=COMPANY, user_id=AE, timezone=MADRID, now=NOW)
    snap = db.tables["reports"][0]["snapshot"]
    assert snap["sections"] == ["attempts", "connected_calls", "meetings_agreed", "handoffs"]
    assert snap["metrics"]["handoffs"] == 1


def test_daily_report_handoffs_unavailable_when_table_missing_not_zero():
    db = FakeDB(
        {
            "memos": [_memo("m-1", interaction_kind="call")],
            "reports": [],
            "report_notifications": [],
            "team_outcome_observations": [],
            "company_members": [{"id": "mem-sdr2", "company_id": COMPANY, "user_id": AE, "role": "member", "status": "active",
                                  "sales_role": "sdr", "handoff_ae_user_id": None, "visibility": "own"}],
            "company_feature_flags": [{"company_id": COMPANY, "flag": "REPORTING_BY_FLOW_ENABLED", "enabled": True}],
        },
        fail_tables=("deal_handoffs",),
    )
    ensure_self_daily_report(db, company_id=COMPANY, user_id=AE, timezone=MADRID, now=NOW)
    snap = db.tables["reports"][0]["snapshot"]
    assert snap["metrics"]["handoffs"] is None


def test_weekly_report_by_flow_uses_the_same_facts():
    db = _db(
        memos=[_memo("m-1", motion="closing", followup_status="sent", interaction_kind="meeting")],
        company_members=[{"id": "mem-ae", "company_id": COMPANY, "user_id": AE, "role": "member", "status": "active",
                           "sales_role": "ae", "handoff_ae_user_id": None, "visibility": "own"}],
        deal_handoffs=[],
        interaction_patterns=[],
        report_preferences=[],
        company_feature_flags=[
            {"company_id": COMPANY, "flag": "REPORTING_WEEKLY_ENABLED", "enabled": True},
            {"company_id": COMPANY, "flag": "REPORTING_BY_FLOW_ENABLED", "enabled": True},
        ],
    )
    ensure_self_weekly_report(db, company_id=COMPANY, user_id=AE, timezone=MADRID, now=FRIDAY_1805)
    weekly = [row for row in db.tables["reports"] if row["report_type"] == "weekly"]
    assert len(weekly) == 1
    snap = weekly[0]["snapshot"]
    assert snap["sections"] == ["meetings_held", "deals_in_progress", "proposals_sent", "deals_won"]
    assert snap["metrics"]["meetings_held"] == 1
    assert snap["metrics"]["proposals_sent"] == 1
