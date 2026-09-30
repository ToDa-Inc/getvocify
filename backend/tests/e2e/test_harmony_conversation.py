"""E9 harmony: one conversation through the real pipeline; every output must show the same facts.

Each channel enters the way production does (dialer call webhook, WhatsApp voice note) and every
stage after that is production code. Only external IO is faked: the models (LLM), speech to text,
the CRM's HTTP API, WhatsApp delivery, and the database (tests/e2e/fake_db.py).
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-harmony-e2e-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-harmony-e2e-32")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import briefs as briefs_api
from app.api import memos as memos_api
from app.api import today as today_api
from app.deps import get_membership, get_supabase
from app.models.memo import MemoExtraction
from app.services import feature_flags, memo_approval
from app.services import followup as followup_svc
from app.services.company import Membership
from app.services.hoy import confirmations
from app.services.hoy.confirmations import CONFIRM_TYPE, DealSnapshot, run_confirm_write
from app.services.hubspot.types import SyncResult
from app.services.intelligence.extract import PROMPT_PATH, is_current
from app.services.meetings import accept as meetings_accept
from app.services.meetings.accept import accept_meeting_proposal
from app.services.meetings.proposals import latest_proposal
from app.services.reporting.periodic import ensure_self_weekly_report, ensure_team_weekly_report
from app.services.reporting.weekly import week_bounds
from app.services.team_insights.aggregate import load_team_adherence_inputs, team_adherence
from app.services.telephony import call_processor
from app.services.whatsapp import processor as whatsapp_processor

from tests.e2e.fake_db import FakeDB

COMPANY = "c0000000-0000-4000-8000-0000000000e9"
USER = "a0000000-0000-4000-8000-0000000000e9"
CONNECTION = "b0000000-0000-4000-8000-0000000000e9"
CONFIG_ID = "d0000000-0000-4000-8000-0000000000e9"
CONTACT = "42"
DEAL = "deal-1"
CALL_SID = "CA-harmony"
TZ = "Europe/Madrid"
MADRID = ZoneInfo(TZ)

CAPTURED = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)  # martes 10:00 Madrid
NOW = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)  # jueves 10:00 Madrid, día del compromiso
REPORT_NOW = datetime(2026, 9, 25, 17, 0, tzinfo=timezone.utc)  # viernes 19:00 Madrid, informe semanal

TRANSCRIPT = (
    "Rep: Hola Marina, ¿cómo lleváis el seguimiento?\n"
    "Them: Se nos quedan leads sin llamar los viernes, es un dolor.\n"
    "Them: Está caro para lo que ofrecéis.\n"
    "Rep: Te comparo con lo que os cuesta un comercial.\n"
    "Them: Vale, llámame el jueves para seguir.\n"
    "Rep: Perfecto, quedamos el jueves a las 11 para la demo.\n"
    "Them: De acuerdo."
)
PAIN_QUOTE = "Se nos quedan leads sin llamar los viernes"
OBJECTION_QUOTE = "Está caro para lo que ofrecéis"
COMMITMENT_TEXT = "llamar el jueves"
COMMITMENT_DAY = "2026-09-24"
MEETING_AT = datetime(2026, 9, 24, 11, 0, tzinfo=MADRID)
BOOKED_STAGE = "appointmentscheduled"

C04_ANSWER = {
    "interest": "high",
    "pain_confirmed": True,
    "pain_quote": PAIN_QUOTE,
    "objections": [{"category": "price", "resolution": "open", "quote": OBJECTION_QUOTE}],
    "commitments": [{
        "kind": "call",
        "origin": "prospect_request",
        "text": COMMITMENT_TEXT,
        "quote": "llámame el jueves para seguir",
        "due_at": COMMITMENT_DAY,
    }],
    "meeting": {
        "agreed": True,
        "starts_at": MEETING_AT.isoformat(),
        "quote": "quedamos el jueves a las 11 para la demo",
    },
}
EXTRACTION_ANSWER = {
    "summary": "Marina dudó por el precio y pidió que la llamaran el jueves.",
    "contactName": "Marina",
    "companyName": "Acme",
    "painPoints": ["Leads sin llamar los viernes"],
    "objections": [OBJECTION_QUOTE],
    "nextSteps": ["Llamar el jueves"],
}
FOLLOWUP_ANSWER = {"subject": "Seguimiento", "body": "Hola Marina, hablamos el jueves.", "language": "es"}

PLAYBOOK_ID = "e0000000-0000-4000-8000-0000000000e9"
PLAYBOOK_VERSION = {
    "id": "f0000000-0000-4000-8000-0000000000e9",
    "playbook_id": PLAYBOOK_ID,
    "status": "published",
    "steps": [{"step_id": "pitch", "label": "Pitch", "criterion": "Explicó el producto"}],
    "entries": [{"entry_id": "price-1", "category": "price", "guidance": "compáralo con un comercial más.",
                 "source_ref": "pb:1"}],
}

FLAGS = (
    "INTELLIGENCE_EXTRACT_ENABLED", "FOLLOWUP_ENABLED", "COMMITMENT_TASKS_ENABLED", "BRIEF_V2_ENABLED",
    "HOY_CONFIRMATIONS_ENABLED", "HOY_MEETINGS_ENABLED", "DEAL_STAGE_CONFIRM_ENABLED",
    "REPORTING_WEEKLY_ENABLED", "REPORTING_TEAM_ENABLED", "TEAM_COMPETITORS_ENABLED",
)


class FakeLLM:
    """The models. C04 and the follow-up draft answer as the real ones would for this call."""

    def __init__(self):
        self.calls: list[dict] = []

    async def chat_json(self, messages, **kwargs):
        kind = "c04" if messages[0]["content"] == PROMPT_PATH.read_text(encoding="utf-8") else "followup"
        self.calls.append({"kind": kind, "messages": copy.deepcopy(messages), **kwargs})
        return copy.deepcopy(C04_ANSWER if kind == "c04" else FOLLOWUP_ANSWER)

    def context(self, kind: str) -> dict:
        [call] = [c for c in self.calls if c["kind"] == kind]
        return json.loads(call["messages"][1]["content"])


class FakeExtraction:
    """The CRM-field extraction model."""

    def __init__(self, *_a, **_k):
        pass

    async def extract(self, *_a, **_k):
        return MemoExtraction(**copy.deepcopy(EXTRACTION_ANSWER))


class FakeHubSpot:
    """HubSpot's HTTP API as seen through the provider, the meeting writer and the task search."""

    def __init__(self):
        self.stage = "qualifiedtobuy"
        self.tasks: dict[str, dict] = {}
        self.syncs: list[dict] = []
        self.meetings: list[dict] = []

    async def sync_memo(self, **kwargs):
        self.syncs.append(kwargs)
        ids = {}
        for task in kwargs.get("commitment_tasks") or []:
            task_id = f"task-{len(self.tasks) + 1}"
            self.tasks[task_id] = {"subject": task.text, "due_date": task.due_date, "contact_id": CONTACT}
            ids[task.commitment_id] = task_id
        extraction = kwargs.get("extraction")
        if "dealstage" in (kwargs.get("allowed_fields") or []) and getattr(extraction, "dealStage", None):
            self.stage = extraction.dealStage
        return SyncResult(memo_id=kwargs["memo_id"], success=True, contact_id=CONTACT, deal_id=DEAL,
                          commitment_task_ids=ids)

    def task_page(self, request: dict) -> dict:
        assert request["path"] == "/crm/v3/objects/tasks/search"
        return {"results": [
            {"id": task_id, "properties": {"hs_task_subject": t["subject"], "hs_task_status": "NOT_STARTED",
                                           "contact_id": t["contact_id"]}}
            for task_id, t in self.tasks.items()
        ]}

    def writer(self, *_a, **_k):
        crm = self

        class _Writer:
            def create(self, operation_key: str, proposal: dict) -> str:
                crm.meetings.append({"operation_key": operation_key, **copy.deepcopy(proposal)})
                return f"meeting-{len(crm.meetings)}"

            def reconcile(self, _operation_key: str):
                return None

            def change_stage(self, mapping) -> bool:
                crm.stage = mapping.get("stage_id") if isinstance(mapping, dict) else mapping
                return True

        return _Writer()

    async def deal_snapshot(self, _supabase, *, memo: dict, company_id: str):
        del memo, company_id
        return DealSnapshot(provider="hubspot", pipeline_id="default", stage_id=self.stage,
                            stage_labels={BOOKED_STAGE: "Meeting booked", "qualifiedtobuy": "Qualified"})


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, _to, text, **_k):
        self.sent.append(text)


def _database() -> FakeDB:
    return FakeDB(
        clock=CAPTURED,
        emails={USER: "lucia@acme.test"},
        companies=[{"id": COMPANY, "name": "Acme", "product_context": "", "glossary": []}],
        company_members=[{"id": "m-1", "company_id": COMPANY, "user_id": USER, "role": "owner",
                          "status": "active", "created_at": "2026-01-01T00:00:00+00:00"}],
        user_profiles=[{"id": USER, "full_name": "Lucía Pérez", "company_name": "Vocify", "glossary": [],
                        "stt_languages": ["es"], "writing_samples": []}],
        company_feature_flags=[{"company_id": COMPANY, "flag": flag, "enabled": True} for flag in FLAGS],
        crm_connections=[{"id": CONNECTION, "company_id": COMPANY, "user_id": USER, "provider": "hubspot",
                          "status": "connected", "access_token": "token", "metadata": {"portal_id": "1"}}],
        crm_configurations=[{"id": CONFIG_ID, "connection_id": CONNECTION, "auto_sync_hubspot_calls": True,
                             "auto_create_contacts": False, "auto_create_companies": False,
                             "meeting_booked_pipeline_id": "default", "meeting_booked_stage_id": BOOKED_STAGE}],
        playbooks=[{"id": PLAYBOOK_ID, "company_id": COMPANY, "sales_motion_key": "outbound",
                    "active_version_id": PLAYBOOK_VERSION["id"]}],
        playbook_versions=[copy.deepcopy(PLAYBOOK_VERSION)],
        outbound_calls=[{"id": "oc-1", "user_id": USER, "carrier_call_id": CALL_SID, "to_number": "+34600000000",
                         "hubspot_contact_id": CONTACT, "hubspot_deal_id": DEAL, "recording_duration": 95,
                         "status": "completed"}],
    )


@dataclass
class World:
    channel: str
    db: FakeDB
    llm: FakeLLM
    crm: FakeHubSpot
    whatsapp: FakeWhatsApp
    memo_id: str = ""
    confirm_writes: list = field(default_factory=list)

    @property
    def memo(self) -> dict:
        [memo] = self.db.rows("memos", id=self.memo_id)
        return memo

    def client(self, *routers) -> TestClient:
        app = FastAPI()
        for router in routers:
            app.include_router(router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m-1", company_id=COMPANY, user_id=USER, role="owner", status="active",
        )
        app.dependency_overrides[get_supabase] = lambda: self.db
        return TestClient(app)


def _install_io_fakes(monkeypatch, crm: FakeHubSpot, llm: FakeLLM, confirm_writes: list) -> None:
    async def _fresh(_supabase, connection):
        return connection

    async def _stt(*_a, **_k):
        return SimpleNamespace(text=TRANSCRIPT, confidence=0.93, diarization={}, channels=1)

    async def _nothing(*_a, **_k):
        return {}

    async def _no_specs(*_a, **_k):
        return None

    monkeypatch.setattr("app.services.llm.LLMClient", lambda *_a, **_k: llm)
    monkeypatch.setattr(memos_api, "ExtractionService", FakeExtraction)
    monkeypatch.setattr(whatsapp_processor, "ExtractionService", FakeExtraction)
    monkeypatch.setattr(call_processor, "transcribe_audio", _stt)
    monkeypatch.setattr(call_processor, "log_call_engagement", _nothing)
    monkeypatch.setattr(memos_api, "_curated_field_specs_for_primary_crm", _no_specs)
    monkeypatch.setattr(whatsapp_processor, "get_field_specs", _no_specs)
    monkeypatch.setattr("app.services.extraction_context.load_existing_crm_values", _nothing)
    monkeypatch.setattr("app.services.transcript_sanitize.schedule_transcript_polish", lambda *_a, **_k: None)
    monkeypatch.setattr(memo_approval, "ensure_hubspot_connection_tokens_fresh", _fresh)
    monkeypatch.setattr(memo_approval, "build_crm_provider", lambda *_a, **_k: crm)
    monkeypatch.setattr(confirmations, "fetch_deal_snapshot", crm.deal_snapshot)
    monkeypatch.setattr(meetings_accept, "writer_from_connection", crm.writer)
    monkeypatch.setattr(today_api, "_FETCH", crm.task_page)
    monkeypatch.setattr(today_api, "schedule_confirm_write", lambda _s, sid, deadline: confirm_writes.append((sid, deadline)))
    monkeypatch.setattr(today_api, "_CLOCK", [NOW])
    monkeypatch.setattr(briefs_api, "_now", lambda: NOW)


async def _settle() -> None:
    """Wait for every background task the entry started (C04, hooks, follow-up, auto-approve)."""
    me = asyncio.current_task()
    for _ in range(100):
        pending = [t for t in asyncio.all_tasks() if t is not me and not t.done()]
        if not pending:
            return
        await asyncio.wait(pending, timeout=5)
    raise AssertionError("background work never settled")


async def _call(world: World) -> None:
    [call_row] = world.db.rows("outbound_calls", carrier_call_id=CALL_SID)
    memo_id, created = await call_processor.initiate_vocify_call_memo(world.db, call_row)
    assert created
    world.memo_id = memo_id
    await call_processor.process_vocify_call_background(memo_id, USER, CALL_SID, b"RIFF", 95.0, world.db)
    await _settle()


async def _whatsapp(world: World) -> None:
    memo_id, _ = await whatsapp_processor._extract_and_create_memo(world.db, USER, TRANSCRIPT, "wamid-harmony", None)
    assert memo_id
    world.memo_id = str(memo_id)
    await _settle()
    tap = SimpleNamespace(button_id=f"approve:{memo_id}", from_phone="+34600000001", chat_id=None, account_id=None)
    await whatsapp_processor._handle_button_reply(world.db, tap, world.whatsapp, USER)
    await _settle()


def _confirm_in_hoy(world: World) -> None:
    """The rep taps Confirmar on the Hoy card; the write runs once the undo window is over."""
    view = world.client(today_api.router).get("/api/v1/today").json()
    [card] = [item for item in view["items"] if item["type"] == CONFIRM_TYPE]
    assert card["reason"] == "Confirma: reunión jue 24 sep, 11:00 con Marina · etapa → Meeting booked"
    response = world.client(today_api.router).post(
        f"/api/v1/today/{card['id']}/resolve",
        json={"action": "confirm", "request_id": "tap-1", "expected_version": card["version"]},
    )
    assert response.status_code == 200, response.text
    [(scheduled, deadline)] = world.confirm_writes
    after = datetime.fromisoformat(str(deadline).replace("Z", "+00:00")) + timedelta(seconds=1)
    assert asyncio.run(run_confirm_write(world.db, scheduled, now=after)) == "applied"


def _accept_in_review(world: World) -> None:
    """WhatsApp memos have no Hoy confirmation: the rep accepts the meeting in the review."""
    proposal = latest_proposal(world.db.rows("meeting_proposals", memo_id=world.memo_id))
    accept_meeting_proposal(world.db, company_id=COMPANY, memo_id=world.memo_id, decision="accept",
                            proposal_id=proposal["proposal_id"])


@pytest.fixture(params=["call", "whatsapp"])
def world(request, monkeypatch) -> World:
    feature_flags.clear_cache()
    followup_svc._live.clear()
    db = _database()
    crm, llm, confirm_writes = FakeHubSpot(), FakeLLM(), []
    _install_io_fakes(monkeypatch, crm, llm, confirm_writes)
    # The team loader reads memos from the current Madrid week (minus a margin): pin "now"
    # to the story's week so the test does not depend on the wall clock.
    from app.services.team_insights import aggregate as team_aggregate

    real_week_bounds = team_aggregate.madrid_week_bounds
    monkeypatch.setattr(
        team_aggregate, "madrid_week_bounds", lambda *, now=None: real_week_bounds(now=now or REPORT_NOW)
    )
    world = World(channel=request.param, db=db, llm=llm, crm=crm, whatsapp=FakeWhatsApp(),
                  confirm_writes=confirm_writes)
    asyncio.run(_call(world) if world.channel == "call" else _whatsapp(world))
    db.clock = NOW
    if world.channel == "call":
        _confirm_in_hoy(world)
    else:
        _accept_in_review(world)
    yield world
    feature_flags.clear_cache()
    followup_svc._live.clear()


def _local(value) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(MADRID)


def _hoy(world: World) -> dict:
    return world.client(today_api.router).get("/api/v1/today").json()


def _brief(world: World) -> dict:
    response = world.client(briefs_api.router).get(
        "/api/v1/briefs", params={"connection_id": CONNECTION, "contact_id": CONTACT, "deal_id": DEAL},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _reports(world: World) -> tuple[dict, dict]:
    ensure_self_weekly_report(world.db, company_id=COMPANY, user_id=USER, timezone=TZ, now=REPORT_NOW)
    ensure_team_weekly_report(world.db, company_id=COMPANY, user_id=USER, timezone=TZ, now=REPORT_NOW)
    [mine] = world.db.rows("reports", scope="self")
    [team] = world.db.rows("reports", scope="team")
    return mine["snapshot"], team["snapshot"]


def _team_panel(world: World) -> dict:
    start, end = week_bounds(REPORT_NOW, TZ)
    inputs = {**load_team_adherence_inputs(world.db, COMPANY), "activity_period_start": start,
              "activity_period_end": end}
    return team_adherence(role="owner", **inputs)


def _c04(world: World) -> dict:
    memo = world.memo
    assert is_current(memo)
    return memo["extraction"]["intelligence"]


def test_one_c04_run_is_current_for_the_stored_conversation(world):
    intel = _c04(world)
    assert [c["kind"] for c in world.llm.calls].count("c04") == 1
    assert intel["commitments"][0]["text"] == COMMITMENT_TEXT
    assert intel["objections"][0]["category"] == "price"
    assert intel["meeting"]["agreed"] is True


def test_commitment_date_is_the_same_in_c04_crm_task_hoy_brief_and_followup(world):
    [commitment] = _c04(world)["commitments"]
    assert _local(commitment["due_at"]).date().isoformat() == COMMITMENT_DAY

    [task] = world.crm.tasks.values()
    assert task["subject"].lower() == COMMITMENT_TEXT
    assert task["due_date"] == COMMITMENT_DAY
    assert commitment["crm_task_id"] in world.crm.tasks

    view = _hoy(world)
    [row] = world.db.rows("action_signals", type="commitment_due")
    assert row["payload"]["text"] == COMMITMENT_TEXT
    assert _local(row["payload"]["due_at"]).date().isoformat() == COMMITMENT_DAY
    [shown] = [item for item in view["items"] if str(item.get("contact_id")) == CONTACT]
    assert shown["dedupe_key"] == row["dedupe_key"]
    assert shown["crm_task_id"] == commitment["crm_task_id"]

    why = next(line for line in _brief(world)["lines"] if line["type"] == "why")
    assert why["text"] == "Pidió que le llamaras hoy."
    assert _local(why["observed_at"]).date().isoformat() == COMMITMENT_DAY

    draft = world.llm.context("followup")
    assert draft["commitments"] == [{"text": COMMITMENT_TEXT, "origin": "prospect_request",
                                     "day": "Thursday 2026-09-24"}]
    assert world.memo["followup"]["status"] == "ready"


def test_meeting_is_the_same_in_c04_proposal_crm_hoy_and_followup(world):
    meeting = _c04(world)["meeting"]
    assert _local(meeting["starts_at"]) == MEETING_AT

    [proposal] = world.db.rows("meeting_proposals", memo_id=world.memo_id)
    assert proposal["evidence_refs"] == meeting["evidence_refs"]
    assert _local(proposal["starts_at"]) == MEETING_AT
    assert proposal["decision"] == "accepted"

    [written] = world.crm.meetings
    assert written["proposal_id"] == proposal["proposal_id"]
    assert _local(written["starts_at"]) == MEETING_AT

    _hoy(world)
    [today] = world.db.rows("action_signals", type="meeting_today")
    assert today["payload"]["proposal_id"] == proposal["proposal_id"]
    assert _local(today["payload"]["starts_at"]) == MEETING_AT

    assert world.llm.context("followup")["meeting"] == {"day": "Thursday 2026-09-24", "time": "11:00"}


def test_only_the_auto_approved_call_confirms_meeting_and_stage_from_hoy(world):
    if world.channel == "whatsapp":
        assert world.db.rows("action_signals", type=CONFIRM_TYPE) == []
        return
    [row] = world.db.rows("action_signals", type=CONFIRM_TYPE)
    proposal = latest_proposal(world.db.rows("meeting_proposals", memo_id=world.memo_id))
    assert row["payload"]["meeting"]["proposal_id"] == proposal["proposal_id"]
    assert _local(row["payload"]["meeting"]["starts_at"]) == MEETING_AT
    assert row["payload"]["write_applied"] is True
    assert world.crm.stage == BOOKED_STAGE


def test_meeting_counted_in_report_and_team(world):
    mine, team = _reports(world)
    assert mine["metrics"]["meetings_agreed"] == 1
    assert team["metrics"]["meetings_agreed"] == 1
    assert _team_panel(world)["meetings"] == 1


def test_pain_quote_is_the_same_in_c04_brief_hook_and_followup(world):
    assert _c04(world)["pain_confirmed"] is True
    [hook] = [line for line in _brief(world)["lines"] if line["type"] == "hook"]
    assert hook["text"] == f"22 sep: «{PAIN_QUOTE}»"
    assert world.llm.context("followup")["pain_quote"] == PAIN_QUOTE


def test_price_objection_is_the_same_in_c04_and_hoy(world):
    [objection] = _c04(world)["objections"]
    _hoy(world)
    [row] = world.db.rows("action_signals", type="objection_open")
    assert row["payload"]["category"] == objection["category"] == "price"
    assert OBJECTION_QUOTE.lower() in row["payload"]["quote"].lower()


def test_price_objection_reaches_team_and_report(world):
    mine, team = _reports(world)
    assert [o["name"] for o in mine["objections"]] == ["price"]
    assert [o["name"] for o in team["objections"]] == ["price"]
    assert [o["name"] for o in _team_panel(world)["objection_categories"]] == ["price"]


def test_price_objection_reaches_the_post_call_brief(world):
    [brief] = world.db.rows("post_interaction_briefs", memo_id=world.memo_id)
    assert brief["status"] == "ready"
    categories = [s.get("category") for s in brief["body"].get("sections") or []]
    assert "price" in categories


def test_brief_says_the_playbook_line_for_the_price_objection(world):
    says = [line["text"] for line in _brief(world)["lines"] if line["type"] == "say"]
    assert says == ["Precio: compáralo con un comercial más."]


def test_adherence_is_the_same_in_score_report_and_team(world):
    [score] = world.db.rows("memo_scores", memo_id=world.memo_id)
    mine, team = _reports(world)
    panel = _team_panel(world)
    assert score["score"]["adherence"] == mine["metrics"]["adherence"] == team["metrics"]["adherence"] \
        == panel["adherence"]
