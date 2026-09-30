"""The reserved `internal` type: a conversation with no customer in it (a team meeting, an
internal brief) is tagged `internal`, never scored and never proposed to the CRM. A manual
retag always wins over the detection."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.memo import MemoExtraction
from app.services import feature_flags
from app.services.coaching.score_assembly import build_score_from_extraction
from app.services.memo_extraction_hooks import refresh_meeting_proposal, run_post_extraction_hooks
from app.services.playbooks.catalog import INTERNAL_KEY
from app.services.playbooks.routing import apply_internal_detection

MEMO = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


class _Query:
    def __init__(self, tables: dict, name: str):
        self.tables, self.name = tables, name
        self.filters: list[tuple[str, str]] = []
        self.op, self.payload = "select", None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, str(value)))
        return self

    def limit(self, *_a):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    upsert = insert

    def delete(self):
        self.op = "delete"
        return self

    def execute(self):
        rows = self.tables.setdefault(self.name, [])
        hit = [row for row in rows if all(str(row.get(c)) == v for c, v in self.filters)]
        if self.op == "update":
            for row in hit:
                row.update(self.payload)
        elif self.op == "insert":
            rows.extend(dict(row) for row in (self.payload if isinstance(self.payload, list) else [self.payload]))
            hit = self.payload if isinstance(self.payload, list) else [self.payload]
        elif self.op == "delete":
            self.tables[self.name] = [row for row in rows if row not in hit]
        return SimpleNamespace(data=hit)


class _Db:
    def __init__(self, **tables):
        self.tables = {name: list(rows) for name, rows in tables.items()}

    def table(self, name):
        return _Query(self.tables, name)


def _memo(pin_source="role_default", **overrides):
    memo = {
        "id": MEMO,
        "company_id": "co-1",
        "user_id": "author",
        "sales_motion_key": "discovery",
        "playbook_version_id": "v-discovery",
        "pipeline_meta": {"stages": [{"name": "extract"}], "playbook_pin": {"source": pin_source}},
        "transcript": "You: ¿Nos vemos? Them: Vale, quedamos el jueves 1 a las 10.",
        "screening_outcome": "connected",
    }
    memo.update(overrides)
    return memo


def _scoreable(customer_present):
    return {
        "summary": "Repasamos el pipeline del equipo",
        "customerPresent": customer_present,
        "intelligence": {
            "version": 1,
            "input_revision": "rev-intel",
            "objections": [{"id": "obj-1", "category": "price", "evidence_refs": ["ev-1"]}],
            "playbook_observations": [{"step_id": "pain", "status": "met", "evidence_refs": ["ev-1"]}],
            "evidence": [{"id": "ev-1", "source_type": "transcript", "source_id": MEMO, "quote": "caro"}],
        },
    }


# -- extraction ------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("said, stored", [(False, False), (True, True), (None, None), ("no", None)])
async def test_extraction_reports_customer_present_and_keeps_it_out_of_the_crm_fields(said, stored):
    from app.services.extraction import ExtractionService, build_extraction_prompt

    prompt = build_extraction_prompt("You: Repasamos el pipeline. Them: Vale, yo llevo Acme.")
    assert '"customerPresent": boolean | null' in prompt
    assert "null for a note the rep dictates alone" in prompt

    llm = AsyncMock()
    llm.chat_json.return_value = {"summary": "# Equipo\n- Pipeline", "nextSteps": [], "customerPresent": said}
    llm.last_call_meta = {}
    jev = AsyncMock()
    jev.is_available = False
    extracted = await ExtractionService(llm_client=llm, jev_client=jev).extract(
        transcript="You: Repasamos el pipeline. Them: Vale, yo llevo Acme.",
    )
    assert extracted.customerPresent is stored
    assert "customerPresent" not in (extracted.raw_extraction or {})


# -- detection -------------------------------------------------------------------------------


def test_customer_absent_tags_internal():
    memo = _memo("role_default")
    update = apply_internal_detection(memo, {"customerPresent": False})
    assert update["sales_motion_key"] == INTERNAL_KEY == "internal"
    assert update["playbook_version_id"] is None
    assert update["pipeline_meta"]["playbook_pin"]["source"] == "internal"
    # The rest of pipeline_meta is kept.
    assert update["pipeline_meta"]["stages"] == [{"name": "extract"}]
    # A rule pin and a memo that was never pinned are tagged too; only manual is sacred.
    assert apply_internal_detection(_memo("rule"), {"customerPresent": False})["sales_motion_key"] == "internal"
    assert apply_internal_detection(_memo(pipeline_meta=None), {"customerPresent": False})["sales_motion_key"] == "internal"


def test_unknown_never_tags_internal():
    for extraction in ({"customerPresent": None}, {}, {"customerPresent": True}, {"customerPresent": "false"}):
        assert apply_internal_detection(_memo(), extraction) == {}
    # null / absent is unknown, never coerced to false by the model's normalizer.
    assert MemoExtraction(**{"summary": "x"}).customerPresent is None
    assert MemoExtraction(**{"summary": "x", "customerPresent": None}).customerPresent is None
    assert MemoExtraction(**{"summary": "x", "customerPresent": False}).customerPresent is False


def test_manual_pin_is_never_overwritten():
    assert apply_internal_detection(_memo("manual"), {"customerPresent": False}) == {}
    # Already internal: nothing to write again.
    already = _memo("internal", sales_motion_key="internal", playbook_version_id=None)
    assert apply_internal_detection(already, {"customerPresent": False}) == {}


def test_the_hooks_persist_the_tag_and_leave_a_manual_pin_alone():
    db = _Db(memos=[_memo("role_default")])
    run_post_extraction_hooks(db, memo_id=MEMO, extraction={"summary": "x", "customerPresent": False})
    row = db.tables["memos"][0]
    assert (row["sales_motion_key"], row["playbook_version_id"]) == ("internal", None)
    assert row["pipeline_meta"]["playbook_pin"]["source"] == "internal"

    manual = _Db(memos=[_memo("manual")])
    run_post_extraction_hooks(manual, memo_id=MEMO, extraction={"summary": "x", "customerPresent": False})
    assert manual.tables["memos"][0]["sales_motion_key"] == "discovery"


# -- skip rules ------------------------------------------------------------------------------


def test_internal_memo_is_not_scored():
    # The same extraction with a customer in it is scored, so the skip is the type's doing.
    scored = _Db(memos=[_memo()])
    run_post_extraction_hooks(scored, memo_id=MEMO, extraction=_scoreable(True))
    assert len(scored.tables.get("memo_scores") or []) == 1

    db = _Db(memos=[_memo()])
    run_post_extraction_hooks(db, memo_id=MEMO, extraction=_scoreable(False))
    assert db.tables.get("memo_scores") in (None, [])
    # The C04 worker path assembles through the same function.
    internal = _memo("internal", sales_motion_key="internal", playbook_version_id=None)
    assert build_score_from_extraction(extraction=_scoreable(False), memo=internal, input_revision="rev-1") is None


@pytest.mark.asyncio
async def test_internal_memo_makes_no_crm_proposals():
    # A meeting said out loud still makes no meeting proposal for an internal conversation.
    with_customer = _Db(memos=[_memo()])
    run_post_extraction_hooks(with_customer, memo_id=MEMO, extraction={"summary": "", "customerPresent": True})
    assert len(with_customer.tables.get("meeting_proposals") or []) == 1

    db = _Db(memos=[_memo()])
    run_post_extraction_hooks(db, memo_id=MEMO, extraction={"summary": "", "customerPresent": False})
    assert db.tables.get("meeting_proposals") in (None, [])
    internal = db.tables["memos"][0]
    refresh_meeting_proposal(db, {**internal, "extraction": {"summary": "", "customerPresent": False}})
    assert db.tables.get("meeting_proposals") in (None, [])

    # And the opt-in auto-approve never writes it to the CRM.
    from app.services.hubspot import auto_sync

    row = {
        "id": MEMO, "status": "pending_review", "source": "hubspot_call", "company_id": "co-1",
        "hubspot_contact_id": "c1", "hubspot_deal_id": "d1", "matched_deal_id": None,
        "screening_outcome": None, "sales_motion_key": "internal",
    }
    with patch(
        "app.services.crm_config.CRMConfigurationService.get_configuration",
        new_callable=AsyncMock, return_value=SimpleNamespace(auto_sync_hubspot_calls=True),
    ), patch("app.services.memo_approval.approve_memo_core", new_callable=AsyncMock) as approve:
        assert await auto_sync.maybe_auto_approve_hubspot_call(_Db(memos=[row]), MEMO, "author") is False
    approve.assert_not_awaited()


# -- manual retag ----------------------------------------------------------------------------


def test_manual_retag_accepts_internal(monkeypatch):
    from app.api.playbook_rules import memo_router
    from app.deps import get_membership, get_supabase
    from app.services.company import Membership

    requeued: list[dict] = []
    monkeypatch.setattr("app.api.playbook_rules._requeue", lambda _s, memo: requeued.append(dict(memo)))
    # No playbooks table at all: internal needs no live version.
    db = _Db(memos=[_memo("rule")])
    app = FastAPI()
    app.include_router(memo_router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="author", role="member", status="active",
    )
    response = TestClient(app).post(f"/api/v1/memos/{MEMO}/playbook", json={"sales_motion_key": "internal"})
    assert response.status_code == 200
    assert response.json() == {"sales_motion_key": "internal", "playbook_version_id": None, "status": "requeued"}
    row = db.tables["memos"][0]
    assert (row["sales_motion_key"], row["playbook_version_id"]) == ("internal", None)
    assert row["pipeline_meta"]["playbook_pin"] == {"source": "manual", "changed_from": "discovery", "changed_by": "author"}
    assert row["pipeline_meta"]["stages"] == [{"name": "extract"}]
    assert [memo["sales_motion_key"] for memo in requeued] == ["internal"]
