"""F15.04: Ask get_team_metrics and GET /team/adherence share one aggregate."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-channels-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-channels-32")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership
from app.services.company import Membership
from app.services.crm_copilot.tools import CopilotContext, execute_tool
from app.services.team_insights.aggregate import team_adherence

COMPANY = "co-channels-1"
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REP = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_WEEK_START = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)
_WEEK_END = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)

SHARED_INPUTS = {
    "parts": [
        {"met_steps": 2, "missed_steps": 0, "unknown_steps": 0, "not_applicable_steps": 8,
         "observed_at": "2026-09-22T10:00:00+00:00"},
    ],
    "playbook_present": True,
    "sample_size": 1,
    "activity_rows": [
        {"observed_at": "2026-09-22T10:00:00+00:00", "screening": "connected", "meeting_agreed": True},
        {"observed_at": "2026-09-22T11:00:00+00:00", "screening": "voicemail", "meeting_agreed": False},
    ],
    "activity_period_start": _WEEK_START,
    "activity_period_end": _WEEK_END,
    "pattern_rows": [
        {"category": "price", "kind": "objection", "resolution": "open", "superseded": False,
         "observed_at": "2026-09-22T10:00:00+00:00"},
        {"category": "timing", "kind": "objection", "resolution": "resolved", "superseded": False,
         "observed_at": "2026-09-22T10:05:00+00:00"},
    ],
    "reps": [{"userId": REP, "name": "Ana"}],
    "review": [],
    "outcome_observations": None,
    "outcome_user_id": None,
    "memo_rows": [],
}


def _panel_client(*, user_id: str | None = None, motion: str | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(team_api.router)

    def loader(_supabase, company_id, filter_user, filter_motion):
        assert company_id == COMPANY
        assert filter_user == user_id
        assert filter_motion == motion
        return {**SHARED_INPUTS, "outcome_user_id": user_id}

    team_api.set_team_adherence_loader(loader)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=ADMIN, role="admin", status="active",
    )
    params = []
    if user_id:
        params.append(f"user_id={user_id}")
    if motion:
        params.append(f"motion={motion}")
    qs = f"?{'&'.join(params)}" if params else ""
    return TestClient(app), qs


def _metric_keys(body: dict) -> dict:
    return {
        "attempts": body.get("attempts"),
        "connected": body.get("connected"),
        "meetings": body.get("meetings"),
        "met_steps": body.get("met_steps"),
        "applicable_steps": body.get("applicable_steps"),
        "adherence": body.get("adherence"),
        "objection_categories": body.get("objection_categories"),
    }


@pytest.mark.asyncio
async def test_ask_and_panel_share_the_same_team_aggregate(monkeypatch):
    from app.services.crm_copilot import viewer as viewer_mod

    members = [
        {"user_id": ADMIN, "role": "admin", "status": "active"},
        {"user_id": REP, "role": "member", "status": "active"},
    ]

    def scope(_supabase, actor_id):
        return Membership(id="m", company_id=COMPANY, user_id=ADMIN, role="admin", status="active"), members, {}

    monkeypatch.setattr(viewer_mod, "load_viewer_scope", scope)

    def loader(_supabase, company_id, *, user_id=None, motion=None):
        assert company_id == COMPANY
        assert user_id is None
        assert motion is None
        return SHARED_INPUTS

    from app.services.crm_copilot import vocify_reads

    monkeypatch.setattr(vocify_reads, "load_team_adherence_inputs", loader)

    ask = await execute_tool("get_team_metrics", {}, CopilotContext(supabase=object(), user_id=ADMIN, artifacts={}))
    assert ask["ok"] is True
    expected = team_adherence(role="admin", **SHARED_INPUTS)

    client, qs = _panel_client()
    panel = client.get(f"/api/v1/team/adherence{qs}").json()
    team_api.set_team_adherence_loader(None)

    assert _metric_keys(ask["metrics"]) == _metric_keys(expected) == _metric_keys(panel)


@pytest.mark.asyncio
async def test_ask_and_panel_match_with_rep_and_motion_filters(monkeypatch):
    from app.services.crm_copilot import viewer as viewer_mod

    members = [
        {"user_id": ADMIN, "role": "admin", "status": "active"},
        {"user_id": REP, "role": "member", "status": "active"},
    ]
    filtered = {**SHARED_INPUTS, "outcome_user_id": REP}

    def scope(_supabase, actor_id):
        return Membership(id="m", company_id=COMPANY, user_id=ADMIN, role="admin", status="active"), members, {}

    monkeypatch.setattr(viewer_mod, "load_viewer_scope", scope)

    def loader(_supabase, company_id, *, user_id=None, motion=None):
        assert user_id == REP
        assert motion == "discovery"
        return filtered

    from app.services.crm_copilot import vocify_reads

    monkeypatch.setattr(vocify_reads, "load_team_adherence_inputs", loader)

    ask = await execute_tool(
        "get_team_metrics",
        {"user_id": REP, "motion": "discovery"},
        CopilotContext(supabase=object(), user_id=ADMIN, artifacts={}),
    )
    expected = team_adherence(role="admin", **filtered)

    client, qs = _panel_client(user_id=REP, motion="discovery")
    panel = client.get(f"/api/v1/team/adherence{qs}").json()
    team_api.set_team_adherence_loader(None)

    assert _metric_keys(ask["metrics"]) == _metric_keys(expected) == _metric_keys(panel)
