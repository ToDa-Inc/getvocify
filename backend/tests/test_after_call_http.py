"""Lista 4 T4 (E10, E11) over HTTP: POST /memos/{id}/approve with the rep's outcome, POST
/memos/{id}/outcome for an already-approved memo, GET /memos/{id}/after-call, and the Head of
Sales' cadence on PATCH /company. Flag off = today's approve, untouched."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-after-call-32c")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-after-call-32c")

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import after_call as after_call_api
from app.api import memos as memos_api
from app.config import settings
from app.deps import get_membership, get_supabase, get_user_id
from app.services import feature_flags, memo_approval
from app.services.company import Membership
from app.services.hubspot.call_outcome import CallOutcomeWriteResult
from app.services.hubspot.types import SyncResult

COMPANY = "co-after-call"
MEMO = "88888888-8888-8888-8888-888888888888"
REP = "sdr-1"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._filters: list = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append(lambda row, c=column, v=value: row.get(c) == v)
        return self

    def in_(self, column, values):
        self._filters.append(lambda row, c=column, v=tuple(values): row.get(c) in v)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def single(self):
        return self

    def maybe_single(self):
        return self

    def insert(self, payload):
        self._mode, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def execute(self):
        if self._table in self._store.fail_tables:
            raise RuntimeError(f"relation {self._table} does not exist")
        rows = self._store.tables.setdefault(self._table, [])
        if self._mode == "insert":
            row = {"id": f"{self._table}-{len(rows) + 1}", **self._payload}
            rows.append(row)
            self._store.writes.append((self._table, "insert", dict(self._payload)))
            return _Result([row])
        matched = [row for row in rows if all(f(row) for f in self._filters)]
        if self._mode == "update":
            for row in matched:
                row.update(self._payload)
            self._store.writes.append((self._table, "update", dict(self._payload)))
            return _Result([dict(row) for row in matched])
        return _Result([dict(row) for row in matched])


class _Store:
    def __init__(self):
        self.tables: dict[str, list] = {}
        self.writes: list = []
        self.fail_tables: set[str] = set()

    def table(self, name):
        return _Query(self, name)


class _Provider:
    def __init__(self):
        self.calls: list[dict] = []
        self.outcome_calls: list[dict] = []
        self.outcome_result = CallOutcomeWriteResult()

    async def sync_memo(self, **kwargs):
        self.calls.append(kwargs)
        return SyncResult(memo_id=MEMO, success=True, contact_id="c-1", deal_id=kwargs.get("deal_id"))

    async def record_call_outcome(self, **kwargs):
        self.outcome_calls.append(kwargs)
        return self.outcome_result


def _config(**overrides):
    values = dict(
        allowed_deal_fields=["amount"],
        allowed_contact_fields=None,
        allowed_company_fields=None,
        allowed_line_item_fields=None,
        auto_create_companies=False,
        auto_create_contacts=False,
        default_stage_name=None,
        default_pipeline_id=None,
        default_stage_id=None,
        lost_reason_deal_property=None,
        lost_lead_status_value="UNQUALIFIED",
        on_hold_lead_status_value="IN_PROGRESS",
        lost_reasons=["No budget", "Not a fit"],
        deal_creation_rule="always",
        meeting_booked_pipeline_id=None,
        meeting_booked_stage_id=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _membership(*, sales_role="sdr", user_id=REP, role="member", handoff_ae_user_id="ae-1"):
    return Membership(
        id=f"member-{user_id}",
        company_id=COMPANY,
        user_id=user_id,
        role=role,
        status="active",
        sales_role=sales_role,
        handoff_ae_user_id=handoff_ae_user_id,
    )


class _Env:
    def __init__(self, monkeypatch, *, provider="hubspot", status="pending_review", memo=None, config=None, flags=True):
        self.store = _Store()
        self.provider = _Provider()
        self.config = config or _config()
        self.membership = _membership()
        self.user_id = REP
        self.connection = {"id": "conn-1", "provider": provider, "company_id": COMPANY}
        row = {
            "id": MEMO,
            "user_id": REP,
            "company_id": COMPANY,
            "status": status,
            "approved_at": "2026-09-28T09:10:00Z" if status == "approved" else None,
            "hubspot_contact_id": "c-1",
            "matched_deal_id": None,
            "extraction": {
                "companyName": "Acme",
                "contactName": "Ana",
                "intelligence": {
                    "input_revision": "rev-1",
                    "status": "ready",
                    "interest": "medium",
                    "objections": [{"category": "price", "state": "open", "quote": "caro"}],
                    "commitments": [{"kind": "email", "origin": "rep_promise", "text": "te mando la propuesta",
                                     "due_at": "2026-09-29T09:00:00Z"}],
                },
            },
            "audio_duration": 60,
            "created_at": "2026-09-28T09:00:00Z",
        }
        row.update(memo or {})
        self.store.tables = {
            "memos": [row],
            "company_members": [
                {"user_id": "ae-1", "company_id": COMPANY, "sales_role": "ae", "status": "active"},
            ],
            "action_signals": [],
            "company_feature_flags": [
                {"company_id": COMPANY, "flag": "AFTER_CALL_FLOW_ENABLED", "enabled": flags},
                {"company_id": COMPANY, "flag": "HANDOFF_ENABLED", "enabled": True},
            ],
        }
        env = self

        class _ConfigService:
            def __init__(self, _supabase):
                pass

            async def get_configuration(self, *_a, **_k):
                return env.config

        async def _fresh(_supabase, conn):
            return conn

        for module in (memo_approval, after_call_api):
            monkeypatch.setattr(module, "CRMConfigurationService", _ConfigService)
            monkeypatch.setattr(module, "resolve_sync_connection", lambda *_a: env.connection)
            monkeypatch.setattr(module, "build_crm_provider", lambda *_a: env.provider)
        monkeypatch.setattr(memo_approval, "load_viewer_scope", lambda *_a: (None, [], []))
        monkeypatch.setattr(memo_approval, "readable_memo_or_none", lambda row, **_k: row)
        monkeypatch.setattr(memo_approval, "ensure_hubspot_connection_tokens_fresh", _fresh)
        monkeypatch.setattr(memos_api, "load_viewer_scope", lambda *_a: (None, [], []))
        monkeypatch.setattr(memos_api, "readable_memo_or_none", lambda row, **_k: row)
        monkeypatch.setattr(after_call_api, "_membership_or_none", lambda *_a: env.membership)

    @property
    def memo(self) -> dict:
        return self.store.tables["memos"][0]

    def client(self) -> TestClient:
        app = FastAPI()
        app.include_router(memos_api.router)
        app.include_router(after_call_api.router)
        app.dependency_overrides[get_supabase] = lambda: self.store
        app.dependency_overrides[get_user_id] = lambda: self.user_id
        app.dependency_overrides[get_membership] = lambda: self.membership
        return TestClient(app)

    def approve(self, **body):
        return self.client().post(f"/api/v1/memos/{MEMO}/approve", json={"contact_id": "c-1", **body})


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()
    settings.AFTER_CALL_FLOW_ENABLED = False


# --- flag off: today's behaviour ------------------------------------------------------------


def test_flag_off_approve_ignores_the_outcome_and_creates_the_deal_as_today(monkeypatch):
    env = _Env(monkeypatch, flags=False, config=_config(deal_creation_rule="never"))
    response = env.approve(rep_outcome="follow_up", is_new_deal=True)
    assert response.status_code == 200
    [call] = env.provider.calls
    assert call["call_outcome"] is None
    assert call["is_new_deal"] is True and call["skip_deal"] is False
    assert response.json()["after_call"] is None
    assert "rep_outcome" not in env.memo


def test_flag_off_the_after_call_endpoints_are_404(monkeypatch):
    env = _Env(monkeypatch, flags=False, status="approved")
    client = env.client()
    assert client.get(f"/api/v1/memos/{MEMO}/after-call").status_code == 404
    assert client.post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "follow_up"}).status_code == 404


# --- approve with an outcome -------------------------------------------------------------------


def test_follow_up_without_a_date_stores_the_suggested_one(monkeypatch):
    env = _Env(monkeypatch)
    response = env.approve(rep_outcome="follow_up")
    assert response.status_code == 200
    [call] = env.provider.calls
    assert call["call_outcome"] == "on_hold"
    # price stopper: the call (28 Sep 09:00) + 7 days.
    assert env.memo["rep_outcome"] == "follow_up"
    assert env.memo["followup_at"] == "2026-10-05T09:00:00+00:00"
    assert response.json()["after_call"]["followup_at"] == "2026-10-05T09:00:00+00:00"


def test_follow_up_with_the_reps_date_stores_that_date(monkeypatch):
    env = _Env(monkeypatch)
    env.approve(rep_outcome="follow_up", followup_at="2026-10-20T08:00:00Z")
    assert env.memo["followup_at"] == "2026-10-20T08:00:00+00:00"


@pytest.mark.parametrize("rep_outcome", ["not_interested", "disqualified"])
def test_closing_out_without_a_reason_is_422(monkeypatch, rep_outcome):
    env = _Env(monkeypatch)
    assert env.approve(rep_outcome=rep_outcome).status_code == 422
    assert env.provider.calls == []


def test_disqualified_writes_lost_with_the_reason_and_resolves_the_contacts_cards(monkeypatch):
    env = _Env(monkeypatch)
    env.store.tables["action_signals"] = [
        {"id": "s1", "company_id": COMPANY, "user_id": REP, "contact_id": "c-1", "type": "followup_due",
         "status": "pending", "version": 1, "payload": {}},
        {"id": "s2", "company_id": COMPANY, "user_id": REP, "contact_id": "c-1", "type": "callback_no_answer",
         "status": "snoozed", "version": 3, "payload": {}},
        {"id": "s3", "company_id": COMPANY, "user_id": REP, "contact_id": "c-1", "type": "confirm_pending",
         "status": "pending", "version": 1, "payload": {}},
        {"id": "s4", "company_id": COMPANY, "user_id": REP, "contact_id": "c-2", "type": "followup_due",
         "status": "pending", "version": 1, "payload": {}},
    ]
    response = env.approve(rep_outcome="disqualified", disqualify_reason="Not a fit")
    assert response.status_code == 200
    [call] = env.provider.calls
    assert call["call_outcome"] == "lost" and call["lost_reason"] == "Not a fit"
    by_id = {row["id"]: row for row in env.store.tables["action_signals"]}
    assert by_id["s1"]["status"] == "resolved" and by_id["s1"]["payload"]["resolution_reason"] == "disqualified"
    assert by_id["s2"]["status"] == "resolved" and by_id["s2"]["version"] == 4
    assert by_id["s3"]["status"] == "pending"  # a CRM write waiting for its OK is not a call
    assert by_id["s4"]["status"] == "pending"  # another contact
    assert response.json()["after_call"]["signals_resolved"] == 2
    assert env.memo["rep_outcome"] == "disqualified" and env.memo["followup_at"] is None


def test_the_reps_lead_status_replaces_the_mapped_value_for_this_write(monkeypatch):
    env = _Env(monkeypatch)
    env.approve(rep_outcome="follow_up", lead_status="UNQUALIFIED")
    assert env.provider.calls[0]["on_hold_lead_status_value"] == "UNQUALIFIED"
    env2 = _Env(monkeypatch)
    env2.approve(rep_outcome="follow_up", lead_status="INVENTED")
    assert env2.provider.calls[0]["on_hold_lead_status_value"] == "IN_PROGRESS"


@pytest.mark.parametrize("provider", ["pipedrive", "salesforce"])
def test_other_crms_sync_without_a_call_outcome_and_still_store_it(monkeypatch, provider):
    env = _Env(monkeypatch, provider=provider)
    response = env.approve(rep_outcome="not_interested", disqualify_reason="No budget")
    assert response.status_code == 200
    assert env.provider.calls[0]["call_outcome"] is None
    assert env.memo["rep_outcome"] == "not_interested"


# --- deal rule on approve (E11), enforced by the backend -------------------------------------------


@pytest.mark.parametrize(
    "rule,rep_outcome,creates",
    [
        ("always", "follow_up", True),
        ("meeting_booked", "meeting_booked", True),
        ("meeting_booked", "follow_up", False),
        ("follow_up_or_meeting", "follow_up", True),
        ("follow_up_or_meeting", "not_interested", False),
        ("never", "meeting_booked", False),
    ],
)
def test_the_rule_decides_whether_a_contact_without_a_deal_gets_one(monkeypatch, rule, rep_outcome, creates):
    env = _Env(monkeypatch, config=_config(deal_creation_rule=rule))
    body = {"rep_outcome": rep_outcome, "is_new_deal": True}
    if rep_outcome in ("not_interested", "disqualified"):
        body["disqualify_reason"] = "No budget"
    assert env.approve(**body).status_code == 200
    [call] = env.provider.calls
    assert call["is_new_deal"] is creates
    assert call["skip_deal"] is (not creates)


def test_an_existing_deal_is_always_updated(monkeypatch):
    env = _Env(monkeypatch, config=_config(deal_creation_rule="never"))
    env.approve(rep_outcome="follow_up", deal_id="D-9")
    [call] = env.provider.calls
    assert call["deal_id"] == "D-9" and call["skip_deal"] is False


def test_the_rule_also_holds_for_an_approval_without_an_outcome(monkeypatch):
    env = _Env(monkeypatch, config=_config(deal_creation_rule="meeting_booked"))
    env.approve(is_new_deal=True)
    [call] = env.provider.calls
    assert call["skip_deal"] is True and call["is_new_deal"] is False
    assert call["call_outcome"] is None


def test_salesforce_keeps_its_opportunity_whatever_the_rule(monkeypatch):
    env = _Env(monkeypatch, provider="salesforce", config=_config(deal_creation_rule="never"))
    env.approve(rep_outcome="follow_up", is_new_deal=True)
    assert env.provider.calls[0]["skip_deal"] is False


# --- handoff on a booked meeting ------------------------------------------------------------------


def test_meeting_booked_hands_the_contact_to_the_ae(monkeypatch):
    env = _Env(monkeypatch)
    response = env.approve(rep_outcome="meeting_booked")
    assert response.status_code == 200
    handoff = response.json()["after_call"]["handoff"]
    assert handoff["status"] == "created" and handoff["ae_user_id"] == "ae-1"
    [row] = env.store.tables["deal_handoffs"]
    assert row["contact_id"] == "c-1" and row["sdr_user_id"] == REP and row["source_memo_id"] == MEMO
    # Idempotent: the same outcome again replays the active handoff.
    again = env.approve(rep_outcome="meeting_booked")
    assert again.json()["after_call"]["handoff"]["status"] == "exists"
    assert len(env.store.tables["deal_handoffs"]) == 1


def test_without_an_ae_the_approval_still_succeeds_with_a_needs_ae_hint(monkeypatch):
    env = _Env(monkeypatch)
    env.membership = _membership(handoff_ae_user_id=None)
    env.store.tables["company_members"] = []
    response = env.approve(rep_outcome="meeting_booked")
    assert response.status_code == 200
    assert response.json()["after_call"]["handoff"] == {"status": "needs_ae"}
    assert env.memo["rep_outcome"] == "meeting_booked"


def test_an_ae_or_handoff_off_creates_no_handoff(monkeypatch):
    env = _Env(monkeypatch)
    env.membership = _membership(sales_role="ae")
    assert env.approve(rep_outcome="meeting_booked").json()["after_call"]["handoff"] is None
    env2 = _Env(monkeypatch)
    env2.store.tables["company_feature_flags"][1]["enabled"] = False
    feature_flags.clear_cache()
    assert env2.approve(rep_outcome="meeting_booked").json()["after_call"]["handoff"] is None


def test_a_general_without_a_route_keeps_the_contact(monkeypatch):
    env = _Env(monkeypatch)
    env.membership = _membership(sales_role="general", handoff_ae_user_id=None)
    assert env.approve(rep_outcome="meeting_booked").json()["after_call"]["handoff"] == {"status": "self_owned"}


def test_a_manager_approving_a_teammates_memo_records_no_outcome(monkeypatch):
    env = _Env(monkeypatch)
    env.user_id = "admin-1"
    response = env.approve(rep_outcome="meeting_booked")
    assert response.status_code == 200
    assert response.json()["after_call"] is None
    assert "deal_handoffs" not in env.store.tables


# --- POST /outcome for an already-approved memo (auto-approve) -------------------------------------


def test_outcome_on_an_approved_memo_writes_the_crm_status_and_stores_it(monkeypatch):
    env = _Env(monkeypatch, status="approved")
    response = env.client().post(
        f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "not_interested", "disqualify_reason": "No budget"},
    )
    assert response.status_code == 200
    [call] = env.provider.outcome_calls
    assert call["call_outcome"] == "lost" and call["lost_reason"] == "No budget"
    assert call["lost_lead_status_value"] == "UNQUALIFIED" and call["contact_id"] == "c-1"
    body = response.json()["after_call"]
    assert body["crm"]["status"] == "written"
    assert env.memo["rep_outcome"] == "not_interested"
    assert env.provider.calls == []  # never a second full sync


def test_outcome_surfaces_a_failed_crm_write(monkeypatch):
    env = _Env(monkeypatch, status="approved")
    env.provider.outcome_result = CallOutcomeWriteResult(failed="No contact was resolved")
    response = env.client().post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "follow_up"})
    assert response.json()["after_call"]["crm"] == {"status": "failed", "failed": "No contact was resolved", "warning": None}


def test_outcome_on_other_crms_says_it_stays_in_vocify(monkeypatch):
    env = _Env(monkeypatch, status="approved", provider="pipedrive")
    response = env.client().post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "follow_up"})
    assert response.json()["after_call"]["crm"] == {"status": "unsupported", "provider": "pipedrive"}
    assert env.memo["rep_outcome"] == "follow_up"


def test_outcome_says_when_the_rule_would_have_created_a_deal(monkeypatch):
    env = _Env(monkeypatch, status="approved", config=_config(deal_creation_rule="meeting_booked"))
    response = env.client().post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "meeting_booked"})
    body = response.json()["after_call"]
    assert body["deal"] == {"status": "not_created_after_approval"}
    assert body["handoff"]["status"] == "created"


def test_outcome_needs_a_reason_to_close_out_and_an_approved_memo(monkeypatch):
    env = _Env(monkeypatch, status="approved")
    client = env.client()
    assert client.post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "disqualified"}).status_code == 422
    pending = _Env(monkeypatch)
    response = pending.client().post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "follow_up"})
    assert response.status_code == 409


def test_only_the_rep_who_made_the_call_records_its_outcome(monkeypatch):
    env = _Env(monkeypatch, status="approved")
    env.membership = _membership(user_id="admin-1", role="admin")
    client = env.client()
    assert client.post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "follow_up"}).status_code == 403
    assert client.get(f"/api/v1/memos/{MEMO}/after-call").status_code == 403
    env.store.tables["memos"][0]["company_id"] = "other-co"
    assert client.post(f"/api/v1/memos/{MEMO}/outcome", json={"rep_outcome": "follow_up"}).status_code == 404


def test_approve_after_auto_approve_still_records_the_outcome(monkeypatch):
    env = _Env(monkeypatch, status="approved")
    response = env.approve(rep_outcome="follow_up")
    assert response.status_code == 200
    assert env.provider.calls == []
    assert env.provider.outcome_calls[0]["call_outcome"] == "on_hold"
    assert response.json()["after_call"]["crm"]["status"] == "written"


# --- GET /after-call ---------------------------------------------------------------------------------


def test_after_call_prefills_the_panel(monkeypatch):
    env = _Env(monkeypatch, config=_config(deal_creation_rule="meeting_booked"))
    response = env.client().get(f"/api/v1/memos/{MEMO}/after-call")
    assert response.status_code == 200
    body = response.json()
    assert body["stopper"] == "price"
    assert body["suggested_followup_at"] == "2026-10-05T09:00:00+00:00"
    assert body["promised_email"] is True
    assert body["deal_creation_rule"] == "meeting_booked" and body["deal_rule_applies"] is True
    assert body["has_deal"] is False
    assert body["lead_status_options"] == {"on_hold": "IN_PROGRESS", "lost": "UNQUALIFIED"}
    assert body["proposed_lead_status"]["meeting_booked"] == "OPEN_DEAL"
    assert body["proposed_lead_status"]["follow_up"] == "IN_PROGRESS"
    assert body["lost_reasons"] == ["No budget", "Not a fit"]
    assert body["memo_status"] == "pending_review"


def test_after_call_without_hubspot_offers_no_lead_status(monkeypatch):
    env = _Env(monkeypatch, provider="salesforce")
    body = env.client().get(f"/api/v1/memos/{MEMO}/after-call").json()
    assert body["lead_status_options"] is None and body["proposed_lead_status"] is None
    assert body["deal_rule_applies"] is False


# --- Head of Sales' cadence (PATCH /company) -----------------------------------------------------------


def test_the_cadence_request_rejects_unknown_stoppers_and_out_of_range_days():
    from pydantic import ValidationError

    from app.api.company import UpdateCompanyRequest

    assert UpdateCompanyRequest(followup_cadence={"price": 3, "timing": 90}).followup_cadence == {"price": 3, "timing": 90}
    assert UpdateCompanyRequest(followup_cadence={}).followup_cadence == {}
    for bad in ({"price": 0}, {"price": 91}, {"price": "5"}, {"price": True}, {"price": 2.5}, {"weather": 3}, {"interest_none": 3}):
        with pytest.raises(ValidationError):
            UpdateCompanyRequest(followup_cadence=bad)


@pytest.mark.parametrize("flag_on,expected_calls", [(True, 1), (False, 0)])
def test_patch_company_saves_the_cadence_only_with_sdr_sections_on(flag_on, expected_calls):
    import asyncio
    from unittest.mock import MagicMock, patch

    from app.api import company as company_api

    svc = MagicMock()
    svc.require_manage_role.return_value = MagicMock(company_id="company-1")
    svc.sdr_sections_enabled.return_value = flag_on
    svc.lead_tiers_enabled.return_value = False
    svc.sales_strategy_enabled.return_value = False
    with (
        patch.object(company_api, "CompanyService", return_value=svc),
        patch.object(company_api, "get_company", new=MagicMock(return_value=asyncio.sleep(0, result={}))),
    ):
        asyncio.run(company_api.update_company(
            company_api.UpdateCompanyRequest(followup_cadence={"price": 4}), user_id="u1", supabase=MagicMock(),
        ))
    assert svc.update_followup_cadence.call_count == expected_calls
    if expected_calls:
        svc.update_followup_cadence.assert_called_with("company-1", {"price": 4})


def test_only_a_head_of_sales_can_patch_the_cadence():
    import asyncio
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    from app.api import company as company_api

    svc = MagicMock()
    svc.require_manage_role.side_effect = HTTPException(status_code=403, detail="Insufficient permissions")
    with patch.object(company_api, "CompanyService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(company_api.update_company(
                company_api.UpdateCompanyRequest(followup_cadence={"price": 4}), user_id="u1", supabase=MagicMock(),
            ))
    assert exc.value.status_code == 403
    svc.update_followup_cadence.assert_not_called()


def test_update_followup_cadence_writes_null_for_no_overrides_and_never_raises():
    from unittest.mock import MagicMock

    from app.services.company import CompanyService

    supabase = MagicMock()
    CompanyService(supabase).update_followup_cadence("company-1", {})
    assert supabase.table.return_value.update.call_args[0][0]["followup_cadence"] is None
    CompanyService(supabase).update_followup_cadence("company-1", {"price": 4})
    assert supabase.table.return_value.update.call_args[0][0]["followup_cadence"] == {"price": 4}
    supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("42703")
    CompanyService(supabase).update_followup_cadence("company-1", {"price": 4})


def test_get_company_sends_the_cadence_and_its_defaults_only_with_sdr_sections_on():
    from unittest.mock import MagicMock

    from app.api import company as company_api
    from app.services.hoy.cadence import DEFAULT_WAIT_DAYS

    svc = MagicMock()
    svc.sdr_sections_enabled.return_value = True
    svc.followup_cadence.return_value = {"price": 4}
    assert company_api._followup_cadence_fields(svc, "company-1") == {
        "followup_cadence": {"price": 4},
        "followup_cadence_defaults": DEFAULT_WAIT_DAYS,
    }
    svc.sdr_sections_enabled.return_value = False
    assert company_api._followup_cadence_fields(svc, "company-1") == {}
