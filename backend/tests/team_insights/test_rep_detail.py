"""T13: manager home + per-rep detail. A member with visibility=team reads the team page
read-only (T1/D3); GET /team/rep/{user_id} needs MANAGER_HOME_ENABLED and returns the rep's
sales_role plus its handoffs (SDR past / AE received); get_team_metrics (Ask) matches the
endpoint for the same viewer and filters; the reps table carries per-flow adherence."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-rep-detail-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-rep-detail-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.team_insights.aggregate import (
    TeamAccessError,
    assert_team_reader,
    reps_with_flow_adherence,
    team_adherence,
)
from tests.reporting.fake_db import FakeDB

COMPANY = "co-rep-detail"
OWNER = "user-owner"
SDR = "user-sdr"
AE = "user-ae"
_WEEK_START = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)
_WEEK_END = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _app(db: FakeDB, *, role: str, visibility: str | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(team_api.router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=OWNER, role=role, status="active", visibility=visibility or "own",
    )
    return TestClient(app)


def _db(**flags) -> FakeDB:
    return FakeDB({
        "company_feature_flags": [
            {"company_id": COMPANY, "flag": name, "enabled": value} for name, value in flags.items()
        ],
        "company_members": [
            {"company_id": COMPANY, "user_id": SDR, "sales_role": "sdr", "status": "active"},
            {"company_id": COMPANY, "user_id": AE, "sales_role": "ae", "status": "active"},
        ],
        "deal_handoffs": [
            {
                "id": "h1", "company_id": COMPANY, "sdr_user_id": SDR, "ae_user_id": AE,
                "contact_id": "c1", "status": "active", "created_at": "2026-09-20T10:00:00Z",
            },
            {
                "id": "h2", "company_id": COMPANY, "sdr_user_id": SDR, "ae_user_id": AE,
                "contact_id": "c2", "status": "closed", "created_at": "2026-09-10T10:00:00Z",
            },
        ],
    })


def test_a_plain_member_is_denied_but_visibility_team_is_allowed():
    with pytest.raises(TeamAccessError):
        assert_team_reader("member", None)
    with pytest.raises(TeamAccessError):
        assert_team_reader("member", "own")
    assert_team_reader("member", "team")  # T1/D3: does not raise
    with pytest.raises(TeamAccessError):
        team_adherence(role="member", visibility="own", parts=[], playbook_present=True, sample_size=0)
    team_adherence(role="member", visibility="team", parts=[], playbook_present=True, sample_size=0)


def test_rep_detail_flag_gates_a_member_with_visibility_team():
    db = _db(SALES_ROLES_ENABLED=True)
    response = _app(db, role="member", visibility="team").get(f"/api/v1/team/rep/{SDR}")
    assert response.status_code == 404


def test_rep_detail_owner_and_admin_do_not_need_the_manager_home_flag():
    for role in ("owner", "admin"):
        response = _app(_db(), role=role).get(f"/api/v1/team/rep/{SDR}")
        assert response.status_code == 200


def test_rep_detail_is_denied_to_a_plain_member():
    db = _db(MANAGER_HOME_ENABLED=True)
    response = _app(db, role="member").get(f"/api/v1/team/rep/{SDR}")
    assert response.status_code == 403


def test_rep_detail_allows_a_member_with_visibility_team():
    db = _db(MANAGER_HOME_ENABLED=True, HANDOFF_ENABLED=True, SALES_ROLES_ENABLED=True)
    response = _app(db, role="member", visibility="team").get(f"/api/v1/team/rep/{SDR}")
    assert response.status_code == 200


def test_rep_detail_denies_visibility_team_when_sales_roles_flag_is_off():
    # effective_visibility (T1) only honours the stored visibility once SALES_ROLES_ENABLED
    # is on - off means today's owner/admin-only behaviour, whatever the column holds.
    db = _db(MANAGER_HOME_ENABLED=True)
    response = _app(db, role="member", visibility="team").get(f"/api/v1/team/rep/{SDR}")
    assert response.status_code == 403


def test_rep_detail_returns_sales_role_and_split_handoffs():
    db = _db(MANAGER_HOME_ENABLED=True, HANDOFF_ENABLED=True)
    sdr_body = _app(db, role="owner").get(f"/api/v1/team/rep/{SDR}").json()
    assert sdr_body["sales_role"] == "sdr"
    assert [row["id"] for row in sdr_body["handoffs"]["as_sdr"]] == ["h1", "h2"]
    assert sdr_body["handoffs"]["as_ae"] == []

    ae_body = _app(db, role="owner").get(f"/api/v1/team/rep/{AE}").json()
    assert ae_body["sales_role"] == "ae"
    assert [row["id"] for row in ae_body["handoffs"]["as_ae"]] == ["h1", "h2"]
    assert ae_body["handoffs"]["as_sdr"] == []


def test_rep_detail_handoffs_are_none_when_handoff_flag_is_off():
    db = _db(MANAGER_HOME_ENABLED=True)
    body = _app(db, role="owner").get(f"/api/v1/team/rep/{SDR}").json()
    assert body["handoffs"] is None


def test_rep_detail_404s_for_a_user_with_no_company_members_row():
    db = _db(MANAGER_HOME_ENABLED=True, HANDOFF_ENABLED=True)
    response = _app(db, role="owner").get("/api/v1/team/rep/not-a-member")
    assert response.status_code == 404


def _flow_part(user_id: str, motion: str, met: int, missed: int) -> dict:
    return {
        "user_id": user_id,
        "motion": motion,
        "met_steps": met,
        "missed_steps": missed,
        "unknown_steps": 0,
        "not_applicable_steps": 0,
        "observed_at": "2026-09-22T10:00:00Z",
    }


def test_reps_with_flow_adherence_splits_by_sdr_and_ae_motion():
    reps = [{"userId": SDR, "name": "S"}, {"userId": AE, "name": "A"}]
    parts = [
        _flow_part(SDR, "discovery", 4, 1),
        _flow_part(AE, "closing", 2, 2),
        _flow_part(AE, "qualification", 9, 0),  # neither column
    ]
    out = reps_with_flow_adherence(reps, parts, start=_WEEK_START, end=_WEEK_END)
    by_id = {row["userId"]: row for row in out}
    assert by_id[SDR]["flows"]["sdr"] == 0.8
    assert by_id[SDR]["flows"]["ae"] is None
    assert by_id[AE]["flows"]["ae"] == 0.5
    assert by_id[AE]["flows"]["sdr"] is None


def test_team_adherence_reps_carry_flow_columns_when_rep_motion_parts_is_given():
    body = team_adherence(
        role="admin",
        parts=[_flow_part(SDR, "discovery", 1, 0)],
        rep_motion_parts=[_flow_part(SDR, "discovery", 1, 0)],
        playbook_present=True,
        sample_size=1,
        activity_period_start=_WEEK_START,
        activity_period_end=_WEEK_END,
        reps=[{"userId": SDR, "name": "S"}],
    )
    assert body["reps"][0]["flows"]["sdr"] == 1.0
    assert body["reps"][0]["flows"]["ae"] is None


async def test_ask_get_team_metrics_matches_the_endpoint_for_the_same_viewer(monkeypatch):
    from app.services.crm_copilot import viewer as viewer_mod
    from app.services.crm_copilot.tools import CopilotContext, execute_tool
    from app.services.team_insights.aggregate import load_team_adherence_inputs

    members = [
        {"user_id": OWNER, "role": "owner", "status": "active", "full_name": "Owner"},
        {"user_id": SDR, "role": "member", "status": "active", "full_name": "Sdr"},
    ]

    def scope(_supabase, user_id):
        role = {OWNER: "owner", SDR: "member"}[user_id]
        return (
            Membership(id="m", company_id=COMPANY, user_id=user_id, role=role, status="active"),
            members,
            {},
        )

    monkeypatch.setattr(viewer_mod, "load_viewer_scope", scope)
    db = _db()

    endpoint_body = team_adherence(
        role="owner",
        visibility=None,
        **load_team_adherence_inputs(db, COMPANY, user_id=None, motion=None),
    )
    endpoint_body.pop("competitor_mentions", None)  # off by default, same as the tool
    tool_result = await execute_tool(
        "get_team_metrics",
        {"instruction": "", "user_id": None},
        CopilotContext(supabase=db, user_id=OWNER, artifacts={}),
    )
    assert tool_result["ok"] is True
    assert tool_result["metrics"] == endpoint_body


async def test_ask_get_team_metrics_matches_the_endpoint_for_a_visibility_team_member(monkeypatch):
    # T1/D3 + T13: a plain member with visibility=team is also a manager for both paths.
    from app.services.crm_copilot import viewer as viewer_mod
    from app.services.crm_copilot.tools import CopilotContext, execute_tool
    from app.services.team_insights.aggregate import load_team_adherence_inputs

    members = [
        {"user_id": OWNER, "role": "owner", "status": "active", "full_name": "Owner"},
        {"user_id": SDR, "role": "member", "status": "active", "full_name": "Sdr"},
    ]

    def scope(_supabase, user_id):
        return (
            Membership(
                id="m", company_id=COMPANY, user_id=user_id, role="member", status="active",
                visibility="team",
            ),
            members,
            {},
        )

    monkeypatch.setattr(viewer_mod, "load_viewer_scope", scope)
    db = _db(SALES_ROLES_ENABLED=True)

    endpoint_body = team_adherence(
        role="member",
        visibility="team",
        **load_team_adherence_inputs(db, COMPANY, user_id=None, motion=None),
    )
    endpoint_body.pop("competitor_mentions", None)
    tool_result = await execute_tool(
        "get_team_metrics",
        {"instruction": "", "user_id": None},
        CopilotContext(supabase=db, user_id=SDR, artifacts={}),
    )
    assert tool_result["ok"] is True
    assert tool_result["metrics"] == endpoint_body


def test_company_summary_exposes_the_viewers_own_visibility_when_sales_roles_are_on():
    from unittest.mock import MagicMock

    from app.services.company import CompanyService, Membership

    svc = CompanyService(MagicMock())
    svc.get_membership = MagicMock(
        return_value=Membership(
            id="m", company_id=COMPANY, user_id=OWNER, role="member", status="active",
            visibility="team",
        )
    )
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.seat_usage = MagicMock(return_value={"seat_limit": 5, "seats_used": 1, "seats_pending": 0, "seats_active": 1})
    svc.billing_for = MagicMock(return_value={})
    svc.rep_workspace_enabled = MagicMock(return_value=False)
    svc.brief_v2_enabled = MagicMock(return_value=False)
    svc.sales_roles_enabled = MagicMock(return_value=True)
    svc.needs_onboarding = MagicMock(return_value=False)

    summary = svc.company_summary_for_user(OWNER)
    assert summary["visibility"] == "team"

    svc.sales_roles_enabled = MagicMock(return_value=False)
    summary = svc.company_summary_for_user(OWNER)
    assert summary["visibility"] is None


def test_rep_detail_names_the_handoff_contacts_from_memos():
    db = _db(MANAGER_HOME_ENABLED=True, HANDOFF_ENABLED=True)
    db.tables["memos"] = [
        {"id": "m1", "company_id": COMPANY, "hubspot_contact_id": "c1",
         "extraction": {"contactName": "Marina Ortiz", "companyName": "Acme"}},
    ]
    body = _app(db, role="owner").get(f"/api/v1/team/rep/{SDR}").json()
    rows = {row["id"]: row for row in body["handoffs"]["as_sdr"]}
    assert rows["h1"]["contact_name"] == "Marina Ortiz"
    assert rows["h1"]["company_name"] == "Acme"
    assert "contact_name" not in rows["h2"]  # no memo: the page falls back to the id
