"""DEAL_STAGE_CONFIRM_ENABLED: the rep confirms the deal stage; Vocify never moves it alone."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-stage-confirm-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-stage-confirm-32")

from types import SimpleNamespace

import pytest

from app.models.memo import ApproveMemoRequest, MemoExtraction
from app.services import deal_stage_confirm as sc
from app.services import feature_flags
from app.services import memo_approval
from app.services.hubspot.types import SyncResult

COMPANY = "co-stage"
MEMO = "77777777-7777-7777-7777-777777777777"
FLAG_ON = [{"company_id": COMPANY, "flag": "DEAL_STAGE_CONFIRM_ENABLED", "enabled": True}]
CONFIG = SimpleNamespace(
    meeting_booked_pipeline_id="default",
    meeting_booked_stage_id="appointmentscheduled",
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, tables, name):
        self._tables = tables
        self._name = name
        self._filters: list[tuple[str, object]] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def single(self):
        return self

    def update(self, _payload):
        return self

    def execute(self):
        rows = list(self._tables.get(self._name, []))
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        return _Result(rows)


class _DB:
    def __init__(self, **tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables, name)


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _proposal(**overrides):
    row = {
        "memo_id": MEMO,
        "proposal_id": "meet-1",
        "input_revision": "rev-1",
        "agreement": "agreed",
        "decision": "pending",
        "starts_at": "2026-09-29T15:00:00+00:00",
        "created_at": "2026-09-22T10:00:00Z",
    }
    row.update(overrides)
    return row


# --- Sugerencia preseleccionada ---------------------------------------------


def test_an_agreed_meeting_suggests_the_configured_stage():
    db = _DB(meeting_proposals=[_proposal()])
    assert sc.meeting_booked_stage(db, memo_id=MEMO, config=CONFIG) == {
        "pipeline_id": "default",
        "stage_id": "appointmentscheduled",
    }


def test_a_meeting_the_rep_omitted_suggests_nothing():
    db = _DB(meeting_proposals=[_proposal(decision="omitted")])
    assert sc.meeting_booked_stage(db, memo_id=MEMO, config=CONFIG) is None


def test_only_the_latest_proposal_counts():
    db = _DB(meeting_proposals=[
        _proposal(created_at="2026-09-22T10:00:00Z"),
        _proposal(created_at="2026-09-22T11:00:00Z", input_revision="rev-2", agreement="not_agreed"),
    ])
    assert sc.meeting_booked_stage(db, memo_id=MEMO, config=CONFIG) is None


def test_without_an_agreed_meeting_or_a_configured_stage_nothing_is_suggested():
    assert sc.meeting_booked_stage(_DB(meeting_proposals=[]), memo_id=MEMO, config=CONFIG) is None
    unconfigured = SimpleNamespace(meeting_booked_pipeline_id=None, meeting_booked_stage_id=None)
    assert sc.meeting_booked_stage(
        _DB(meeting_proposals=[_proposal()]), memo_id=MEMO, config=unconfigured
    ) is None


def test_suggestion_order_meeting_then_inferred_then_fallback():
    meeting = {"pipeline_id": "default", "stage_id": "appointmentscheduled"}
    stages = ["appointmentscheduled", "qualifiedtobuy", "closedwon"]
    assert sc.suggested_stage(
        pipeline_id="default", stage_ids=stages, meeting_booked=meeting,
        inferred="closedwon", fallback="qualifiedtobuy",
    ) == "appointmentscheduled"
    assert sc.suggested_stage(
        pipeline_id="partners", stage_ids=["p_new"], meeting_booked=meeting,
        inferred="p_new", fallback=None,
    ) == "p_new"
    assert sc.suggested_stage(
        pipeline_id="partners", stage_ids=["p_new"], meeting_booked=meeting,
        inferred=None, fallback="p_new",
    ) == "p_new"


# --- Preview kwargs (endpoint) ----------------------------------------------


def test_flag_off_preview_gets_no_stage_confirm_kwargs():
    db = _DB(meeting_proposals=[_proposal()], company_feature_flags=[])
    memo = {"id": MEMO, "company_id": COMPANY}
    assert sc.preview_stage_kwargs(db, memo=memo, connection={"provider": "hubspot"}, config=CONFIG) == {}


def test_flag_on_preview_gets_stage_confirm_and_the_meeting_suggestion():
    db = _DB(meeting_proposals=[_proposal()], company_feature_flags=FLAG_ON)
    memo = {"id": MEMO, "company_id": COMPANY}
    for provider in ("hubspot", "pipedrive"):
        assert sc.preview_stage_kwargs(db, memo=memo, connection={"provider": provider}, config=CONFIG) == {
            "stage_confirm": True,
            "meeting_booked_stage": {"pipeline_id": "default", "stage_id": "appointmentscheduled"},
        }


def test_flag_on_is_not_applied_to_salesforce():
    db = _DB(meeting_proposals=[_proposal()], company_feature_flags=FLAG_ON)
    memo = {"id": MEMO, "company_id": COMPANY}
    assert sc.preview_stage_kwargs(db, memo=memo, connection={"provider": "salesforce"}, config=CONFIG) == {}


# --- Aprobación (approve_memo_core) -----------------------------------------


class _Provider:
    def __init__(self):
        self.calls: list[dict] = []

    async def sync_memo(self, **kwargs):
        self.calls.append(kwargs)
        return SyncResult(memo_id=MEMO, success=True, deal_id="D1")


def _approve_env(monkeypatch, *, provider_name: str, flags, allowed_deal_fields):
    memo = {
        "id": MEMO,
        "user_id": "u-1",
        "company_id": COMPANY,
        "status": "pending_review",
        "matched_deal_id": "D1",
        "extraction": {"companyName": "Acme", "dealStage": "closedwon"},
        "audio_duration": 1,
        "created_at": "2026-09-22T10:00:00Z",
    }
    db = _DB(memos=[memo], company_feature_flags=list(flags))
    provider = _Provider()
    connection = {"id": "conn-1", "provider": provider_name, "company_id": COMPANY}
    config = SimpleNamespace(
        allowed_deal_fields=allowed_deal_fields,
        allowed_contact_fields=None,
        allowed_company_fields=None,
        allowed_line_item_fields=None,
        auto_create_companies=False,
        auto_create_contacts=False,
        default_stage_name=None,
        default_pipeline_id=None,
        default_stage_id=None,
        lost_reason_deal_property=None,
        lost_lead_status_value=None,
        on_hold_lead_status_value=None,
    )

    class _Config:
        def __init__(self, _supabase):
            pass

        async def get_configuration(self, *_a, **_k):
            return config

    async def _fresh(_supabase, conn):
        return conn

    monkeypatch.setattr(memo_approval, "load_viewer_scope", lambda *_a: (None, [], []))
    monkeypatch.setattr(memo_approval, "readable_memo_or_none", lambda row, **_k: row)
    monkeypatch.setattr(memo_approval, "resolve_sync_connection", lambda *_a: connection)
    monkeypatch.setattr(memo_approval, "ensure_hubspot_connection_tokens_fresh", _fresh)
    monkeypatch.setattr(memo_approval, "CRMConfigurationService", _Config)
    monkeypatch.setattr(memo_approval, "build_crm_provider", lambda *_a: provider)
    return db, provider


def _reviewed(**extraction):
    return ApproveMemoRequest(extraction=MemoExtraction(companyName="Acme", **extraction), deal_id="D1")


@pytest.mark.asyncio
async def test_flag_off_approval_keeps_the_allowlist_and_sends_no_stage_confirm(monkeypatch):
    db, provider = _approve_env(monkeypatch, provider_name="hubspot", flags=[], allowed_deal_fields=["amount"])
    await memo_approval.approve_memo_core(db, MEMO, "u-1", _reviewed(dealStage="closedwon"))
    call = provider.calls[0]
    assert call["allowed_fields"] == ["amount"]
    assert "stage_confirm" not in call


@pytest.mark.asyncio
async def test_flag_on_reviewed_approval_lets_the_confirmed_stage_through(monkeypatch):
    db, provider = _approve_env(monkeypatch, provider_name="hubspot", flags=FLAG_ON, allowed_deal_fields=["amount"])
    await memo_approval.approve_memo_core(db, MEMO, "u-1", _reviewed(dealStage="closedwon"))
    call = provider.calls[0]
    assert call["allowed_fields"] == ["amount", "dealstage"]
    assert call["stage_confirm"] is True


@pytest.mark.asyncio
async def test_flag_on_reviewed_pipedrive_approval_lets_stage_id_through(monkeypatch):
    db, provider = _approve_env(monkeypatch, provider_name="pipedrive", flags=FLAG_ON, allowed_deal_fields=["value"])
    await memo_approval.approve_memo_core(db, MEMO, "u-1", _reviewed())
    call = provider.calls[0]
    assert call["allowed_fields"] == ["value", "stage_id"]
    assert call["stage_confirm"] is True


@pytest.mark.asyncio
async def test_flag_on_unattended_approval_never_moves_the_stage(monkeypatch):
    db, provider = _approve_env(
        monkeypatch, provider_name="hubspot", flags=FLAG_ON, allowed_deal_fields=["amount", "dealstage"],
    )
    await memo_approval.approve_memo_core(db, MEMO, "u-1", None)
    call = provider.calls[0]
    assert call["allowed_fields"] == ["amount"]
    assert "stage_confirm" not in call
