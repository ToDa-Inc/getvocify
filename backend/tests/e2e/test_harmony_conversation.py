"""E9 harmony: one conversation, all outputs show the same facts (call and WhatsApp)."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-harmony-e2e-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-harmony-e2e-32")

import pytest

from app.config import settings
from app.models.memo import MemoExtraction
from app.services import feature_flags
from app.services import followup as followup_svc
from app.services.briefs.v2 import prepare_brief_v2
from app.services.coaching.briefs import aggregate_brief
from app.services.commitment_tasks import commitment_tasks, sync_plan
from app.services.followup_logic import c04_facts
from app.services.hoy.confirmations import build_confirm_signal, pending_confirm_parts
from app.services.hoy.materialize import day_end, fresh_signals
from app.services.hoy.reasons import reason
from app.services.intelligence.extract import PROMPT_VERSION, shape_intelligence
from app.services.intelligence.worker import revision_for_memo
from app.services.meetings.today import (
    MEETINGS_FLAG,
    meeting_today_signal,
    refresh_meeting_today,
)
from app.services.memo_extraction_hooks import refresh_meeting_proposal, run_post_extraction_hooks
from app.services.reporting.aggregate import build_snapshot
from app.services.team_insights.objections import objection_counts
from app.services.whatsapp import processor as whatsapp_processor

COMPANY = "co-harmony"
USER = "user-harmony"
MEMO_ID = "e9999999-9999-9999-9999-999999999999"
CONTACT = "42"
DEAL = "deal-1"
CONNECTION = "conn-harmony"
TZ = "Europe/Madrid"
NOW = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)  # 10:00 Madrid, meeting day
CAPTURE = "2026-09-22T10:00:00+02:00"

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
COMMITMENT_DUE = "2026-09-24T09:00:00+02:00"
MEETING_START = "2026-09-24T11:00:00+02:00"

PLAYBOOK_ENTRIES = [
    {"entry_id": "price-1", "category": "price", "guidance": "compáralo con un comercial más.", "source_ref": "pb:1"},
]
PLAYBOOK_STEPS = [
    {"step_id": "pitch", "label": "Pitch", "criterion": "Explicó el producto"},
    {"step_id": "qualify", "label": "Cualificar", "criterion": "Confirmó decisor y presupuesto"},
]
BOOKED_LABELS = {"appointmentscheduled": "Meeting booked", "qualifiedtobuy": "Qualified"}
CRM_CONFIG = SimpleNamespace(
    meeting_booked_pipeline_id="default",
    meeting_booked_stage_id="appointmentscheduled",
)

LISTA2_FLAGS = (
    ("COMMITMENT_TASKS_ENABLED", True),
    ("BRIEF_V2_ENABLED", True),
    ("HOY_CONFIRMATIONS_ENABLED", True),
    ("HOY_MEETINGS_ENABLED", True),
    ("DEAL_STAGE_CONFIRM_ENABLED", True),
    ("TEAM_COMPETITORS_ENABLED", True),
    ("INTELLIGENCE_EXTRACT_ENABLED", True),
    ("FOLLOWUP_ENABLED", True),
)


class _Result:
    def __init__(self, data):
        self.data = data


def _matches(row: dict, column: str, value) -> bool:
    if "->>" in column:
        base, key = column.split("->>", 1)
        stored = (row.get(base) or {}).get(key)
        return str(stored).lower() == str(value).lower() if stored is not None else False
    return row.get(column) == value


class _Query:
    def __init__(self, store: "_Store", name: str):
        self._store = store
        self._name = name
        self._filters: list = []
        self._in_filters: list = []
        self._op: str | None = None
        self._payload = None
        self._limit = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def order(self, *_a, **_k):
        return self

    def or_(self, _expr):
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, **_k):
        self._op, self._payload = "upsert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        table = self._store.tables.setdefault(self._name, [])
        rows = list(table)
        for column, value in self._filters:
            rows = [row for row in rows if _matches(row, column, value)]
        for column, values in self._in_filters:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column) or "") in allowed]
        if self._op == "upsert":
            key_cols = ("company_id", "user_id", "connection_id", "dedupe_key")
            match = next(
                (row for row in table if all(row.get(c) == self._payload.get(c) for c in key_cols)),
                None,
            )
            if match:
                match.update(copy.deepcopy(self._payload))
            else:
                row = copy.deepcopy(self._payload)
                row.setdefault("id", f"sig-{len(table) + 1}")
                row.setdefault("version", 1)
                row.setdefault("status", "pending")
                table.append(row)
            return _Result([self._payload])
        if self._op == "update":
            updated = []
            for row in table:
                if all(_matches(row, c, v) for c, v in self._filters):
                    row.update(copy.deepcopy(self._payload))
                    updated.append(row)
            return _Result(updated)
        if self._op == "insert":
            payload = self._payload
            if isinstance(payload, list):
                table.extend(copy.deepcopy(payload))
            else:
                table.append(copy.deepcopy(payload))
            return _Result([payload] if not isinstance(payload, list) else payload)
        if self._op == "delete":
            gone = [row for row in table if row in rows]
            self._store.tables[self._name] = [row for row in table if row not in gone]
            return _Result(gone)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(copy.deepcopy(rows))


class _Store:
    def __init__(self):
        self.tables: dict[str, list] = {
            "company_feature_flags": [
                {"company_id": COMPANY, "flag": flag, "enabled": enabled}
                for flag, enabled in LISTA2_FLAGS
            ],
            "memos": [],
            "memo_scores": [],
            "meeting_proposals": [],
            "interaction_patterns": [],
            "post_interaction_briefs": [],
            "action_signals": [],
            "user_profiles": [{"id": USER, "full_name": "Lucía Pérez", "writing_samples": []}],
        }

    def table(self, name: str):
        return _Query(self, name)


class FakeLLM:
    def __init__(self):
        self.messages = None

    async def chat_json(self, messages, **_kwargs):
        self.messages = messages
        return {"subject": "Seguimiento comercial", "body": "Hola Marina, quedamos el jueves a las 11.", "language": "es"}


def _raw_c04():
    return {
        "interest": "high",
        "pain_confirmed": True,
        "pain_quote": PAIN_QUOTE,
        "objections": [{"category": "price", "resolution": "open", "quote": OBJECTION_QUOTE}],
        "commitments": [{
            "kind": "call",
            "origin": "prospect_request",
            "text": COMMITMENT_TEXT,
            "quote": "llámame el jueves para seguir",
            "due_at": COMMITMENT_DUE,
        }],
        "meeting": {
            "agreed": True,
            "starts_at": MEETING_START,
            "quote": "quedamos el jueves a las 11 para la demo",
        },
    }


def _base_memo(*, channel: str) -> dict:
    kind = "visit" if channel == "whatsapp" else "call"
    source = "whatsapp" if channel == "whatsapp" else "vocify_call"
    return {
        "id": MEMO_ID,
        "user_id": USER,
        "company_id": COMPANY,
        "hubspot_contact_id": CONTACT,
        "hubspot_deal_id": DEAL,
        "matched_deal_id": DEAL,
        "connection_id": CONNECTION,
        "playbook_version_id": "pv-1",
        "timezone": TZ,
        "transcript": TRANSCRIPT,
        "capture_started_at": CAPTURE,
        "created_at": CAPTURE,
        "interaction_kind": kind,
        "source": source,
        "status": "pending_review",
        "screening_outcome": None,
        "extraction": {
            "summary": "Marina dudó por el precio y pidió seguimiento.",
            "contactName": "Marina",
            "dealStage": "qualifiedtobuy",
            "nextSteps": [],
        },
    }


def _with_intelligence(memo: dict) -> dict:
    shaped = shape_intelligence(memo, _raw_c04())
    obj_ev = shaped["objections"][0]["evidence_refs"][0]
    shaped["playbook_observations"] = [
        {"step_id": "pitch", "status": "met", "evidence_refs": [obj_ev]},
        {"step_id": "qualify", "status": "missed", "evidence_refs": []},
    ]
    out = copy.deepcopy(memo)
    out["extraction"] = {**out["extraction"], "intelligence": shaped}
    return out


def _scoreable_extraction(memo: dict) -> dict:
    extraction = copy.deepcopy(memo["extraction"])
    extraction["objections"] = [{"text": OBJECTION_QUOTE, "category": "price"}]
    return extraction


async def _whatsapp_capture(store: _Store) -> dict:
    inserted: list[dict] = []

    class _Memos:
        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, row):
            inserted.append(dict(row))
            store.tables["memos"] = [{"id": MEMO_ID, **row}]
            return self

        def execute(self):
            if inserted:
                return SimpleNamespace(data=[{"id": MEMO_ID, **inserted[-1]}])
            return SimpleNamespace(data=list(store.tables.get("memos") or []))

    class _DB:
        def table(self, name):
            if name == "memos":
                return _Memos()
            return store.table(name)

    class _Extraction:
        async def extract(self, *_a, **_k):
            return MemoExtraction(summary="Visita a Marina: duda por precio.")

    class _Glossary:
        def __init__(self, *_a, **_k):
            pass

        async def get_user_glossary(self, _user_id):
            return []

    with patch.object(whatsapp_processor, "get_field_specs", return_value=None), patch.object(
        whatsapp_processor, "GlossaryService", _Glossary
    ), patch.object(whatsapp_processor, "ExtractionService", _Extraction), patch.object(
        whatsapp_processor, "with_author_company", lambda _s, row: row
    ), patch(
        "app.services.extraction_context.load_product_context", return_value=""
    ), patch(
        "app.services.session_entities.load_stt_profile", return_value={}
    ), patch(
        "app.services.transcript_sanitize.prepare_transcript_for_extraction",
        lambda transcript, *_a, **_k: (transcript, ""),
    ), patch(
        "app.services.transcript_sanitize.schedule_transcript_polish", lambda *_a, **_k: None
    ), patch(
        "app.services.followup.schedule_followup", lambda *_a, **_k: False
    ), patch(
        "app.services.pipeline_lease.update_memo_row", lambda *_a, **_k: None
    ), patch(
        "app.services.intelligence.worker.record_enqueue", lambda *_a, **_k: None
    ), patch(
        "app.services.memo_extraction_hooks.run_post_extraction_hooks", lambda *_a, **_k: None
    ), patch(
        "app.services.hubspot.auto_sync.maybe_auto_approve_hubspot_call",
        new=AsyncMockFalse(),
    ):
        memo_id, _ = await whatsapp_processor._extract_and_create_memo(
            _DB(), USER, TRANSCRIPT, "wamid-harmony", None, None
        )
        await asyncio.gather(*list(whatsapp_processor._POST_EXTRACTION_TASKS), return_exceptions=True)

    assert memo_id == MEMO_ID
    row = store.tables["memos"][0]
    assert row["interaction_kind"] == "visit"
    assert row["source"] == "whatsapp"
    row.update({
        "id": MEMO_ID,
        "company_id": COMPANY,
        "hubspot_contact_id": CONTACT,
        "hubspot_deal_id": DEAL,
        "connection_id": CONNECTION,
        "playbook_version_id": "pv-1",
        "timezone": TZ,
        "transcript": TRANSCRIPT,
        "capture_started_at": CAPTURE,
    })
    return row


class AsyncMockFalse:
    async def __call__(self, *_a, **_k):
        return False


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    followup_svc._live.clear()
    settings.FOLLOWUP_ENABLED = True
    settings.INTELLIGENCE_EXTRACT_ENABLED = True
    yield
    feature_flags.clear_cache()


def _accept_meeting(store: _Store, memo: dict) -> dict:
    revision = revision_for_memo(memo)
    rows = store.tables["meeting_proposals"]
    assert rows, "meeting proposal expected from hooks"
    latest = max(rows, key=lambda row: row.get("created_at") or "")
    latest["decision"] = "accepted"
    latest["crm_status"] = "succeeded"
    return latest


async def _run_pipeline(store: _Store, memo: dict) -> tuple[dict, FakeLLM]:
    memo = _with_intelligence(memo)
    store.tables["memos"] = [memo]

    extraction = _scoreable_extraction(memo)
    run_post_extraction_hooks(store, memo_id=MEMO_ID, memo=memo, extraction=extraction)

    memo = _with_intelligence(store.tables["memos"][0])
    store.tables["memos"] = [memo]
    refresh_meeting_proposal(store, memo)

    connection = {"provider": "hubspot", "company_id": COMPANY}
    plan = sync_plan(store, memo=memo, connection=connection, extraction=MemoExtraction(**memo["extraction"]), reviewed=False)
    assert plan is not None
    tasks, _ = plan
    assert len(tasks) == 1
    assert tasks[0].text == "Llamar el jueves"
    assert tasks[0].due_date == "2026-09-24"

    llm = FakeLLM()
    await followup_svc.ensure_followup(store, MEMO_ID, llm=llm)
    assert memo["followup"]["status"] == "ready"

    proposal = _accept_meeting(store, memo)
    store.tables["company_feature_flags"].append({"company_id": COMPANY, "flag": MEETINGS_FLAG, "enabled": True})
    feature_flags.clear_cache()
    refresh_meeting_today(store, company_id=COMPANY, user_id=USER, now=NOW, tz_name=TZ)

    from app.services.hoy.confirmations import DealSnapshot

    deal = DealSnapshot(provider="hubspot", pipeline_id="default", stage_id="qualifiedtobuy", stage_labels=BOOKED_LABELS)
    pending = pending_confirm_parts(
        memo=memo,
        proposal_rows=[{**proposal, "decision": "pending"}],
        config=CRM_CONFIG,
        deal=deal,
        supabase=store,
        company_id=COMPANY,
    )
    if pending is not None:
        signal = build_confirm_signal(pending, tz_name=TZ)
        store.table("action_signals").upsert(
            {
                "company_id": COMPANY,
                "user_id": USER,
                "connection_id": CONNECTION,
                "contact_id": CONTACT,
                "deal_id": DEAL,
                "memo_id": MEMO_ID,
                "type": signal.type,
                "dedupe_key": signal.dedupe_key,
                "payload": signal.payload,
                "status": "pending",
                "coverage": "complete",
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
        ).execute()

    return memo, llm


def _assert_harmony(store: _Store, memo: dict, llm: FakeLLM | None = None):
    intel = memo["extraction"]["intelligence"]
    assert intel["prompt_version"] == PROMPT_VERSION
    assert intel["input_revision"] == revision_for_memo(memo)

    tasks = commitment_tasks(memo, tz_name=TZ)
    assert tasks and tasks[0].text == "Llamar el jueves"
    assert tasks[0].due_date == "2026-09-24"

    end = day_end(NOW, TZ)
    signals = fresh_signals([memo], now=NOW, day_end=end)
    commitment = next(s for s in signals if s.type == "commitment_due")
    assert commitment.payload["text"] == COMMITMENT_TEXT
    assert commitment.due_at.date().isoformat() == "2026-09-24"
    assert "llam" in reason(commitment).lower()

    objection = next(s for s in signals if s.type == "objection_open")
    assert objection.payload["category"] == "price"
    assert "caro" in objection.payload["quote"].lower()

    meeting_rows = store.tables["action_signals"]
    meeting_sig = next((r for r in meeting_rows if r.get("type") == "meeting_today"), None)
    assert meeting_sig is not None
    assert meeting_sig["payload"]["starts_at"] == MEETING_START
    pure = meeting_today_signal(
        store.tables["meeting_proposals"][0], memo, now=NOW, tz_name=TZ
    )
    assert pure is not None
    assert pure.due_at.hour == 11

    brief = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        playbook_entries=PLAYBOOK_ENTRIES,
        playbook_steps=PLAYBOOK_STEPS,
    )
    hook = brief["lines"][0]
    assert PAIN_QUOTE in hook["text"]
    why = next(line for line in brief["lines"] if line["type"] == "why")
    assert "llam" in why["text"].lower()
    say = next(line for line in brief["lines"] if line["type"] == "say")
    assert say["text"] == "Precio: compáralo con un comercial más."

    if llm is not None:
        ctx = json.loads(llm.messages[1]["content"])
        facts = c04_facts(intel, TZ)
        assert ctx["pain_quote"] == facts["pain_quote"] == PAIN_QUOTE
        assert ctx["commitments"][0]["text"] == facts["commitments"][0]["text"] == COMMITMENT_TEXT
        assert tasks[0].text.lower() == COMMITMENT_TEXT.lower()
        assert ctx["commitments"][0]["day"] == facts["commitments"][0]["day"]
        assert ctx["meeting"]["time"] == facts["meeting"]["time"] == "11:00"

    score_row = store.tables["memo_scores"][0]["score"]
    assert score_row["value"] is not None
    patterns = store.tables["interaction_patterns"]
    assert any(p.get("category") == "price" for p in patterns)
    brief_post = aggregate_brief(
        screening=None,
        score=score_row,
        patterns=patterns,
        playbook_present=True,
        job_error=False,
        input_revision=score_row["input_revision"],
        audio_available=True,
    )
    assert brief_post["status"] == "ready"
    assert score_row["value"] is not None

    confirm = next((r for r in meeting_rows if r.get("type") == "confirm_pending"), None)
    assert confirm is not None
    assert confirm["status"] == "pending"
    assert "reunión" in confirm["payload"]["reason"].lower() or "meeting" in confirm["payload"]["reason"].lower()

    objections_team = objection_counts(
        [{"category": "price", "kind": "objection", "superseded": False, "observed_at": CAPTURE}],
        start=datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc),
    )
    assert objections_team[0]["name"] == "price"

    snapshot = build_snapshot(
        scope="self",
        period_start="2026-09-21T22:00:00Z",
        period_end="2026-09-28T22:00:00Z",
        timezone=TZ,
        interactions=[{
            "captured_at": CAPTURE,
            "connected": True,
            "meeting_agreed": True,
            "memo_id": MEMO_ID,
        }],
        outcomes={"coverage": "complete", "won": 0, "lost": 0},
        adherence_parts=[{"met_steps": 1, "missed_steps": 1, "unknown_steps": 0, "not_applicable_steps": 0}],
        channels={"call": 0, "visit": 1} if memo.get("interaction_kind") == "visit" else {"call": 1, "visit": 0},
    )
    assert snapshot["metrics"]["meetings_agreed"] == 1
    assert snapshot["metrics"]["adherence"] == 0.5


@pytest.mark.parametrize("channel", ["call", "whatsapp"])
def test_harmony_all_surfaces_share_commitment_facts(channel):
    store = _Store()
    if channel == "whatsapp":
        memo = asyncio.run(_whatsapp_capture(store))
    else:
        memo = _base_memo(channel=channel)
        store.tables["memos"] = [memo]

    memo, llm = asyncio.run(_run_pipeline(store, memo))
    _assert_harmony(store, memo, llm)
