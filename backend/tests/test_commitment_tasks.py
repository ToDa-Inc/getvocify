"""COMMITMENT_TASKS_ENABLED: CRM tasks come from C04 commitments, with the text and due date Hoy shows."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-commitment-tasks")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-commitment-tasks")

import copy
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.models.memo import ApproveMemoRequest, MemoExtraction
from app.services import commitment_tasks as ct
from app.services import feature_flags, memo_approval
from app.services.coaching import brief_preferences
from app.services.crm_providers.hubspot_provider import HubSpotCRMProvider
from app.services.crm_providers.pipedrive_provider import PipedriveCRMProvider
from app.services.hubspot.types import SyncResult
from app.services.intelligence.extract import PROMPT_VERSION
from app.services.intelligence.worker import revision_for_memo

COMPANY = "co-tasks"
MEMO_ID = "88888888-8888-8888-8888-888888888888"
FLAG_ON = [{"company_id": COMPANY, "flag": "COMMITMENT_TASKS_ENABLED", "enabled": True}]
MADRID = ZoneInfo("Europe/Madrid")


def _commitment(cid, *, text, due_at, precision, kind="call", origin="rep_promise"):
    return {
        "id": cid, "kind": kind, "origin": origin, "text": text, "due_at": due_at,
        "temporal_precision": precision, "evidence_refs": [f"ev-{cid}"],
    }


TIMED = _commitment(
    "com-1", text="llamar el martes a las 18:00", due_at="2026-09-29T18:00:00+02:00",
    precision="time", origin="prospect_request",
)
DAY = _commitment(
    "com-2", text="enviar el caso de logística", due_at="2026-09-24T00:00:00+02:00",
    precision="date", kind="send",
)
UNDATED = _commitment("com-3", text="preparar la propuesta", due_at=None, precision="unknown", kind="other")


def _memo(commitments=(TIMED, DAY, UNDATED), *, current=True, next_steps=("Llamar a Ana",)):
    memo = {
        "id": MEMO_ID,
        "user_id": "u-1",
        "company_id": COMPANY,
        "status": "pending_review",
        "matched_deal_id": "D1",
        "transcript": "hola",
        "audio_duration": 1,
        "created_at": "2026-09-22T10:00:00Z",
        "extraction": {"companyName": "Acme", "nextSteps": list(next_steps)},
    }
    memo["extraction"]["intelligence"] = {
        "version": 1,
        "input_revision": revision_for_memo(memo) if current else "rev-old",
        "status": "ready",
        "commitments": copy.deepcopy(list(commitments)),
        "objections": [],
        "evidence": [],
        "prompt_version": PROMPT_VERSION,
    }
    return memo


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


# --- Date rules -------------------------------------------------------------


def test_a_timed_commitment_keeps_its_time_and_its_text():
    [task] = ct.commitment_tasks(_memo([TIMED]), tz_name="Europe/Madrid")
    assert task.text == "Llamar el martes a las 18:00"
    assert task.due_at == datetime(2026, 9, 29, 18, 0, tzinfo=MADRID)
    assert task.due_date == "2026-09-29"
    assert task.commitment_id == "com-1"


def test_a_day_only_commitment_is_due_at_nine_in_the_rep_timezone():
    [madrid] = ct.commitment_tasks(_memo([DAY]), tz_name="Europe/Madrid")
    assert madrid.due_at == datetime(2026, 9, 24, 9, 0, tzinfo=MADRID)
    [mexico] = ct.commitment_tasks(_memo([DAY]), tz_name="America/Mexico_City")
    assert mexico.due_at == datetime(2026, 9, 24, 9, 0, tzinfo=ZoneInfo("America/Mexico_City"))
    assert mexico.due_date == "2026-09-24"


def test_an_undated_commitment_has_no_date():
    [task] = ct.commitment_tasks(_memo([UNDATED]), tz_name="Europe/Madrid")
    assert task.due_at is None
    assert task.due_date is None


def test_rep_promises_and_prospect_requests_both_become_tasks():
    tasks = ct.commitment_tasks(_memo([TIMED, DAY]), tz_name="Europe/Madrid")
    assert [t.commitment_id for t in tasks] == ["com-1", "com-2"]


def test_without_current_c04_the_caller_keeps_next_steps():
    assert ct.commitment_tasks(_memo(current=False), tz_name="Europe/Madrid") is None
    bare = {"id": MEMO_ID, "company_id": COMPANY, "extraction": {"nextSteps": ["Llamar a Ana"]}}
    assert ct.commitment_tasks(bare, tz_name="Europe/Madrid") is None


def test_current_c04_without_commitments_means_no_task_rows():
    assert ct.commitment_tasks(_memo([]), tz_name="Europe/Madrid") == []


def test_the_rep_timezone_is_the_one_hoy_uses():
    brief_preferences.write_preference("u-tz", {"highlight_mode": "immediate", "timezone": "America/Mexico_City"})
    try:
        assert ct.rep_timezone("u-tz") == "America/Mexico_City"
    finally:
        brief_preferences._STORE.pop("u-tz", None)
    assert ct.rep_timezone("u-without-preference") == "Europe/Madrid"
    assert ct.rep_timezone(None) == "Europe/Madrid"


# --- Review rows the rep kept -------------------------------------------------


def test_kept_rows_match_by_text_and_edited_rows_stay_next_steps():
    tasks = ct.commitment_tasks(_memo(), tz_name="Europe/Madrid")
    reviewed = MemoExtraction(
        nextSteps=["enviar el caso  de logística", "Llamar a Ana el viernes"],
        raw_extraction={"nextStepSchedules": ["2026-09-24", "viernes"]},
    )
    kept, extraction = ct.split_reviewed(tasks, reviewed)
    assert [t.commitment_id for t in kept] == ["com-2"]
    assert extraction.nextSteps == ["Llamar a Ana el viernes"]
    assert extraction.raw_extraction["nextStepSchedules"] == [""]


def test_a_schedule_never_overrides_a_kept_commitment():
    tasks = ct.commitment_tasks(_memo([DAY, UNDATED]), tz_name="Europe/Madrid")
    reviewed = MemoExtraction(
        nextSteps=["Enviar el caso de logística", "Preparar la propuesta"],
        raw_extraction={"nextStepSchedules": ["2026-09-25", "2026-09-26"]},
    )
    kept, extraction = ct.split_reviewed(tasks, reviewed)
    assert [t.commitment_id for t in kept] == ["com-2", "com-3"]
    assert [t.due_at for t in kept] == [datetime(2026, 9, 24, 9, 0, tzinfo=MADRID), None]
    assert extraction.nextSteps == []
    assert extraction.raw_extraction["nextStepSchedules"] == []


def test_stored_v2_intelligence_is_no_longer_current():
    memo = _memo()
    memo["extraction"]["intelligence"]["prompt_version"] = "intelligence_v2"
    assert ct.commitment_tasks(memo, tz_name="Europe/Madrid") is None


# --- Preview kwargs (endpoint) -------------------------------------------------


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, name):
        self._db = db
        self._name = name
        self._filters: list[tuple[str, object]] = []
        self._update = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def single(self):
        return self

    def update(self, payload):
        self._update = payload
        return self

    def execute(self):
        rows = list(self._db.tables.get(self._name, []))
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        if self._update is not None:
            self._db.updates.append((self._name, self._update))
            return _Result([{**row, **self._update} for row in rows])
        return _Result(rows)


class _DB:
    def __init__(self, **tables):
        self.tables = tables
        self.updates: list[tuple[str, dict]] = []

    def table(self, name):
        return _Query(self, name)


def test_flag_off_preview_gets_no_commitment_kwargs():
    db = _DB(company_feature_flags=[])
    assert ct.preview_kwargs(db, memo=_memo(), connection={"provider": "hubspot"}) == {}


def test_flag_on_preview_gets_the_commitment_tasks_for_hubspot_and_pipedrive():
    db = _DB(company_feature_flags=FLAG_ON)
    for provider in ("hubspot", "pipedrive"):
        kwargs = ct.preview_kwargs(db, memo=_memo(), connection={"provider": provider})
        assert [t.commitment_id for t in kwargs["commitment_tasks"]] == ["com-1", "com-2", "com-3"]


def test_salesforce_review_is_as_before_with_the_flag_on():
    db = _DB(company_feature_flags=FLAG_ON)
    assert ct.preview_kwargs(db, memo=_memo(), connection={"provider": "salesforce"}) == {}


def test_flag_on_preview_without_current_c04_keeps_next_steps():
    db = _DB(company_feature_flags=FLAG_ON)
    assert ct.preview_kwargs(db, memo=_memo(current=False), connection={"provider": "hubspot"}) == {}


class _Recorder:
    def __init__(self):
        self.kwargs: dict = {}

    async def build_preview(self, **kwargs):
        self.kwargs = kwargs

    async def sync_memo(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [HubSpotCRMProvider, PipedriveCRMProvider])
async def test_hubspot_and_pipedrive_pass_commitment_tasks_to_their_review(cls):
    recorder = _Recorder()
    provider = object.__new__(cls)
    provider._preview_service = lambda: recorder
    tasks = ct.commitment_tasks(_memo(), tz_name="Europe/Madrid")
    await provider.build_preview(
        memo_id=MEMO_ID, transcript="", extraction=MemoExtraction(), matched_deals=[],
        selected_deal_id=None, allowed_fields=None, commitment_tasks=tasks,
    )
    assert recorder.kwargs["commitment_tasks"] is tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [HubSpotCRMProvider, PipedriveCRMProvider])
async def test_hubspot_and_pipedrive_pass_commitment_tasks_to_their_sync(cls):
    recorder = _Recorder()
    provider = object.__new__(cls)
    provider._sync_service = lambda: recorder
    tasks = ct.commitment_tasks(_memo(), tz_name="Europe/Madrid")
    await provider.sync_memo(
        memo_id=MEMO_ID, user_id="u-1", connection_id="conn-1", extraction=MemoExtraction(),
        commitment_tasks=tasks,
    )
    assert recorder.kwargs["commitment_tasks"] is tasks


# --- Approval (approve_memo_core) ----------------------------------------------


class _Provider:
    def __init__(self, task_ids=None):
        self.calls: list[dict] = []
        self.task_ids = task_ids or {}

    async def sync_memo(self, **kwargs):
        self.calls.append(kwargs)
        return SyncResult(memo_id=MEMO_ID, success=True, deal_id="D1", commitment_task_ids=dict(self.task_ids))


def _approve_env(monkeypatch, *, provider_name="hubspot", flags=FLAG_ON, memo=None, task_ids=None):
    memo = memo or _memo()
    db = _DB(memos=[memo], company_feature_flags=list(flags))
    provider = _Provider(task_ids)
    connection = {"id": "conn-1", "provider": provider_name, "company_id": COMPANY}
    config = SimpleNamespace(
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


def _reviewed(memo, next_steps):
    extraction = copy.deepcopy(memo["extraction"])
    extraction["nextSteps"] = list(next_steps)
    return ApproveMemoRequest(extraction=MemoExtraction(**extraction), deal_id="D1")


@pytest.mark.asyncio
async def test_flag_off_approval_writes_next_steps_as_before(monkeypatch):
    db, provider = _approve_env(monkeypatch, flags=[])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", None)
    call = provider.calls[0]
    assert "commitment_tasks" not in call
    assert call["extraction"].nextSteps == ["Llamar a Ana"]


@pytest.mark.asyncio
async def test_approval_without_current_c04_writes_next_steps(monkeypatch):
    db, provider = _approve_env(monkeypatch, memo=_memo(current=False))
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", None)
    call = provider.calls[0]
    assert "commitment_tasks" not in call
    assert call["extraction"].nextSteps == ["Llamar a Ana"]


@pytest.mark.asyncio
async def test_unattended_approval_writes_every_commitment(monkeypatch):
    db, provider = _approve_env(monkeypatch)
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", None)
    call = provider.calls[0]
    assert [t.commitment_id for t in call["commitment_tasks"]] == ["com-1", "com-2", "com-3"]
    assert call["extraction"].nextSteps == []


@pytest.mark.asyncio
async def test_a_row_the_rep_removed_is_not_created(monkeypatch):
    memo = _memo()
    db, provider = _approve_env(monkeypatch, memo=memo)
    payload = _reviewed(memo, ["Enviar el caso de logística", "Llamar a Ana el viernes"])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", payload)
    call = provider.calls[0]
    assert [t.commitment_id for t in call["commitment_tasks"]] == ["com-2"]
    assert call["commitment_tasks"][0].due_at == datetime(2026, 9, 24, 9, 0, tzinfo=MADRID)
    assert call["extraction"].nextSteps == ["Llamar a Ana el viernes"]


@pytest.mark.asyncio
async def test_created_task_ids_are_stored_on_their_commitments(monkeypatch):
    db, provider = _approve_env(monkeypatch, task_ids={"com-2": "T-9"})
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", None)
    [(table, update)] = [u for u in db.updates if u[0] == "memos"]
    commitments = update["extraction"]["intelligence"]["commitments"]
    assert [c.get("crm_task_id") for c in commitments] == [None, "T-9", None]
    assert update["extraction"]["intelligence"]["prompt_version"] == PROMPT_VERSION


@pytest.mark.asyncio
async def test_reviewed_approval_stores_task_ids_on_the_reviewed_copy(monkeypatch):
    memo = _memo()
    db, provider = _approve_env(monkeypatch, memo=memo, task_ids={"com-1": "T-1"})
    payload = _reviewed(memo, ["Llamar el martes a las 18:00"])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", payload)
    [(_table, update)] = [u for u in db.updates if u[0] == "memos"]
    assert update["extraction"]["nextSteps"] == ["Llamar el martes a las 18:00"]
    commitments = update["extraction"]["intelligence"]["commitments"]
    assert [c.get("crm_task_id") for c in commitments] == ["T-1", None, None]


def _legacy_memo():
    """Two commitments plus the legacy nextSteps and their schedule hints the extraction stored."""
    memo = _memo([DAY, UNDATED], next_steps=("Mandar el caso", "Preparar propuesta"))
    memo["extraction"]["raw_extraction"] = {"nextStepSchedules": ["2026-09-25", "2026-09-26"]}
    memo["extraction"]["intelligence"]["input_revision"] = revision_for_memo(memo)
    return memo


def _dashboard_payload(memo, row_texts):
    """buildApproveExtraction (src/lib/extraction-omit.ts): memo.extraction with nextSteps
    replaced by the row texts; raw_extraction.nextStepSchedules is left as stored."""
    extraction = copy.deepcopy(memo["extraction"])
    extraction["nextSteps"] = list(row_texts)
    return ApproveMemoRequest(extraction=MemoExtraction(**extraction), deal_id="D1")


def _extension_payload(memo, rows):
    """chrome-extension buildApproveExtraction: nextSteps and nextStepSchedules from the rows
    (text, preview due date), which taskRowsFromPreview takes from the commitment rows."""
    extraction = copy.deepcopy(memo["extraction"])
    extraction["nextSteps"] = [text for text, _due in rows]
    extraction["raw_extraction"] = {
        **extraction.get("raw_extraction", {}),
        "nextStepSchedules": [due or "" for _text, due in rows],
    }
    return ApproveMemoRequest(extraction=MemoExtraction(**extraction), deal_id="D1")


@pytest.mark.asyncio
async def test_dashboard_review_with_untouched_rows_keeps_both_commitments(monkeypatch):
    memo = _legacy_memo()
    db, provider = _approve_env(monkeypatch, memo=memo, task_ids={"com-2": "T-2", "com-3": "T-3"})
    payload = _dashboard_payload(memo, ["Enviar el caso de logística", "Preparar la propuesta"])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", payload)
    call = provider.calls[0]
    assert [t.commitment_id for t in call["commitment_tasks"]] == ["com-2", "com-3"]
    assert [t.due_at for t in call["commitment_tasks"]] == [datetime(2026, 9, 24, 9, 0, tzinfo=MADRID), None]
    assert call["extraction"].nextSteps == []
    [(_table, update)] = [u for u in db.updates if u[0] == "memos"]
    assert [c.get("crm_task_id") for c in update["extraction"]["intelligence"]["commitments"]] == ["T-2", "T-3"]


@pytest.mark.asyncio
async def test_dashboard_review_edited_row_is_a_next_step_without_a_stale_date(monkeypatch):
    memo = _legacy_memo()
    db, provider = _approve_env(monkeypatch, memo=memo)
    payload = _dashboard_payload(memo, ["Enviar el caso de logística y precios", "Preparar la propuesta"])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", payload)
    call = provider.calls[0]
    assert [t.commitment_id for t in call["commitment_tasks"]] == ["com-3"]
    assert call["extraction"].nextSteps == ["Enviar el caso de logística y precios"]
    assert call["extraction"].raw_extraction["nextStepSchedules"] == [""]


@pytest.mark.asyncio
async def test_dashboard_review_removed_row_is_not_created(monkeypatch):
    memo = _legacy_memo()
    db, provider = _approve_env(monkeypatch, memo=memo)
    payload = _dashboard_payload(memo, ["Preparar la propuesta"])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", payload)
    call = provider.calls[0]
    assert [t.commitment_id for t in call["commitment_tasks"]] == ["com-3"]
    assert call["extraction"].nextSteps == []


@pytest.mark.asyncio
async def test_extension_review_keeps_every_commitment_with_its_date(monkeypatch):
    memo = _legacy_memo()
    db, provider = _approve_env(monkeypatch, memo=memo)
    payload = _extension_payload(memo, [("Enviar el caso de logística", "2026-09-24"), ("Preparar la propuesta", None)])
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", payload)
    call = provider.calls[0]
    assert [t.commitment_id for t in call["commitment_tasks"]] == ["com-2", "com-3"]
    assert [t.due_at for t in call["commitment_tasks"]] == [datetime(2026, 9, 24, 9, 0, tzinfo=MADRID), None]
    assert call["extraction"].nextSteps == []


@pytest.mark.asyncio
async def test_salesforce_approval_gets_no_commitment_tasks(monkeypatch):
    db, provider = _approve_env(monkeypatch, provider_name="salesforce")
    await memo_approval.approve_memo_core(db, MEMO_ID, "u-1", None)
    call = provider.calls[0]
    assert "commitment_tasks" not in call
    assert call["extraction"].nextSteps == ["Llamar a Ana"]
