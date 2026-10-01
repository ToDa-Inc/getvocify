"""GET /briefs end to end: flag off is the pre-E3 brief byte for byte; flag on reads the real tables."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-briefs-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-briefs-32b")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import briefs as briefs_api
from app.deps import get_membership, get_supabase
from app.services import crm_providers, feature_flags
from app.services.briefs.v2 import prepare_brief_v2
from app.services.crm_copilot.tools import HubSpotBundle
from app.services.company import Membership
from tests.playbooks.live_double import live_view_rows
from app.services.intelligence.extract import PROMPT_VERSION
from app.services.intelligence.worker import revision_for_memo

HERE = Path(__file__).resolve().parent
MIGRATIONS = HERE.parents[1] / "migrations"
PRE_E3 = json.loads((HERE / "fixtures" / "brief_pre_e3.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def _columns(migration: str, table: str) -> set[str]:
    sql = (MIGRATIONS / migration).read_text(encoding="utf-8")
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", sql, re.S).group(1)
    names = set()
    for line in body.splitlines():
        token = line.strip().split(" ", 1)[0]
        if token and token.islower() and token not in {"unique", "primary"}:
            names.add(token)
    return names


SCHEMA = {
    "action_signals": _columns("043_action_signals.sql", "action_signals"),
    "playbooks": _columns("040_company_playbooks.sql", "playbooks"),
    "playbook_versions": _columns("040_company_playbooks.sql", "playbook_versions") | {"updated_at", "qualification"},
    "playbooks_live": {"playbook_id", "company_id", "sales_motion_key", "version_id"},  # the view of 066_playbooks_v2
}


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.eqs, self.ins, self.desc, self.n = [], [], False, None

    def select(self, cols):
        known = SCHEMA.get(self.name)
        if known is not None and cols != "*":
            unknown = {col.strip() for col in cols.split(",")} - known
            if unknown:
                raise RuntimeError(f"column {sorted(unknown)} does not exist on {self.name}")
        return self

    def eq(self, column, value):
        self.eqs.append((column, value))
        return self

    def in_(self, column, values):
        self.ins.append((column, set(values)))
        return self

    def order(self, _column, desc=False):
        self.desc = desc
        return self

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        self.db.reads.append(self.name)
        self.db.queries.append((self.name, dict(self.eqs), self.n))
        if self.name in self.db.failing:
            raise RuntimeError(f"{self.name} down")
        source = live_view_rows(self.db.tables.get("playbooks", [])) if self.name == "playbooks_live" else self.db.tables.get(self.name, [])
        rows = [row for row in source if all(row.get(c) == v for c, v in self.eqs)]
        rows = [row for row in rows if all(row.get(c) in v for c, v in self.ins)]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=self.desc)
        return SimpleNamespace(data=rows[: self.n] if self.n else rows)


class _Db:
    def __init__(self, tables, failing=()):
        self.tables = tables
        self.failing = set(failing)
        self.reads: list[str] = []
        self.queries: list[tuple[str, dict, int | None]] = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(briefs_api, "rep_timezone", lambda _user_id: "Europe/Madrid")
    monkeypatch.setattr(briefs_api, "_now", lambda: NOW)
    briefs_api.set_brief_tasks(None)
    monkeypatch.setattr(crm_providers, "build_crm_provider", _no_live_crm)
    yield
    briefs_api.set_brief_tasks(None)
    feature_flags.clear_cache()


def _no_live_crm(*_args, **_kwargs):
    raise AssertionError("tests never build a live CRM provider")


def _get(db, *, membership=None, **params):
    app = FastAPI()
    app.include_router(briefs_api.router)
    app.dependency_overrides[get_membership] = lambda: membership or Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: db
    query = {"connection_id": "hubspot", "contact_id": "42", **params}
    response = TestClient(app).get("/api/v1/briefs", params=query)
    assert response.status_code == 200, response.text
    return response.json()


def _flags(**flags):
    return [{"company_id": "co-1", "flag": name, "enabled": value} for name, value in flags.items()]


def _no_crm_tasks(*_args, **_kwargs):
    raise AssertionError("flag off must not read CRM tasks")


# --- Flag off / no row: the pre-E3 brief (fixture captured from 4b1987f) ---

@pytest.mark.parametrize("case", PRE_E3["cases"], ids=[case["name"] for case in PRE_E3["cases"]])
@pytest.mark.parametrize("flag_rows", [[], _flags(BRIEF_V2_ENABLED=False)], ids=["no_row", "row_off"])
def test_flag_off_is_the_pre_e3_brief(case, flag_rows):
    briefs_api.set_brief_tasks(_no_crm_tasks)
    db = _Db(
        {"memos": case["memos"], "company_feature_flags": flag_rows},
        failing={"memos"} if case.get("memos_fail") else (),
    )
    params = {"deal_id": case["deal_id"]} if case.get("deal_id") else {}
    body = _get(db, **params)
    assert body == case["expected"]
    assert set(db.reads) <= {"memos", "company_feature_flags"}


# --- Flag on: the real wiring ---

def _memo(intelligence=None, **extra):
    row = {
        "id": "memo-1",
        "company_id": "co-1",
        "user_id": "user-a",
        "created_at": "2026-09-11T08:00:00Z",
        "capture_started_at": "2026-09-11T08:00:00Z",
        "hubspot_contact_id": "42",
        "hubspot_deal_id": None,
        "matched_deal_id": None,
        "playbook_version_id": None,
        "sales_motion_key": "outbound",
        "extraction": {"summary": "Hablaron del almacén."},
    }
    row.update(extra)
    intel = {
        "version": 1,
        "pain_confirmed": False,
        "objections": [],
        "commitments": [],
        "competitor_mentions": [],
        "playbook_observations": [],
        "evidence": [],
        **(intelligence or {}),
        "prompt_version": PROMPT_VERSION,
    }
    intel["input_revision"] = revision_for_memo(row)
    row["extraction"] = {**row["extraction"], "intelligence": intel}
    return row


NO_REPLY_ROW = {
    "id": "sig-1",
    "company_id": "co-1",
    "user_id": "user-a",
    "connection_id": "conn-1",
    "contact_id": "42",
    "deal_id": None,
    "memo_id": None,
    "type": "no_reply",
    "dedupe_key": "no_reply:42:2026-09-14",
    "payload": {"email_at": "2026-09-14T09:00:00+00:00", "email_date": "2026-09-14", "subject": "Propuesta", "email_id": "e-1"},
    "status": "pending",
}

PLAYBOOK = {"id": "pb-1", "company_id": "co-1", "sales_motion_key": "outbound", "active_version_id": "v-1"}
VERSION = {
    "id": "v-1",
    "playbook_id": "pb-1",
    "status": "published",
    "steps": [
        {"step_id": "pitch", "label": "Pitch", "criterion": "Explicó el producto"},
        {"step_id": "qualify", "label": "Cualificar", "criterion": "Decisor y presupuesto"},
    ],
    "entries": [{"entry_id": "price-1", "category": "price", "guidance": "compáralo con un comercial más.", "source_ref": "pb:1"}],
}


def _tables(memos, *, flags=None, signals=(), playbooks=(), versions=()):
    return {
        "memos": list(memos),
        "company_feature_flags": flags if flags is not None else _flags(BRIEF_V2_ENABLED=True),
        "action_signals": list(signals),
        "playbooks": list(playbooks),
        "playbook_versions": list(versions),
    }


def _tasks(tasks, coverage="complete"):
    calls = []

    def reader(company_id):
        calls.append(company_id)
        return tasks, coverage

    reader.calls = calls
    return reader


def test_flag_on_reads_the_no_reply_signal_by_its_real_columns():
    briefs_api.set_brief_tasks(_tasks([]))
    db = _Db(_tables(
        [_memo()],
        flags=_flags(BRIEF_V2_ENABLED=True, HOY_NO_REPLY_ENABLED=True),
        signals=[NO_REPLY_ROW, {**NO_REPLY_ROW, "id": "sig-other", "contact_id": "99"}],
    ))
    body = _get(db)
    assert body["status"] == "ready"
    assert [line["type"] for line in body["lines"]] == ["hook", "why"]
    assert body["lines"][1]["text"] == "Le escribiste el 14 sep («Propuesta») y no ha respondido."
    assert body["lines"][1]["source_ref"] == "sig-1"


def test_flag_on_without_no_reply_flag_skips_the_signal_and_uses_the_crm_task():
    reader = _tasks([
        {"remote_id": "t-9", "title": "Llamar a otro", "contact_id": "99"},
        {"remote_id": "t-1", "title": "Llamar el jueves", "contact_id": "42"},
    ])
    briefs_api.set_brief_tasks(reader)
    db = _Db(_tables([_memo()], signals=[NO_REPLY_ROW]))
    body = _get(db)
    assert "action_signals" not in db.reads
    assert reader.calls == ["co-1"]
    assert body["lines"][1] == {"type": "why", "text": "Llamar el jueves", "source_ref": "t-1", "observed_at": None}


def test_flag_on_commitment_due_today_wins_over_no_reply_and_task():
    briefs_api.set_brief_tasks(_tasks([{"remote_id": "t-1", "title": "Llamar el jueves", "contact_id": "42"}]))
    memo = _memo({"commitments": [{
        "id": "com-1", "kind": "call", "origin": "prospect_request", "text": "llamar",
        "due_at": "2026-09-26T09:00:00+02:00", "temporal_precision": "time", "evidence_refs": ["ev-1"],
    }], "evidence": [{"id": "ev-1", "quote": "llámame el viernes"}]})
    db = _Db(_tables(
        [memo],
        flags=_flags(BRIEF_V2_ENABLED=True, HOY_NO_REPLY_ENABLED=True),
        signals=[NO_REPLY_ROW],
    ))
    body = _get(db)
    assert body["lines"][1]["text"] == "Pidió que le llamaras hoy a las 09:00."


def test_flag_on_reads_the_published_playbook_for_say_and_label():
    briefs_api.set_brief_tasks(_tasks([]))
    memo = _memo({
        "objections": [{"id": "obj-1", "category": "price", "resolution": "open", "quote": "está caro", "evidence_refs": ["ev-o"]}],
        "evidence": [{"id": "ev-o", "quote": "está caro"}],
        "playbook_observations": [
            {"step_id": "pitch", "status": "met", "evidence_refs": []},
            {"step_id": "qualify", "status": "missed", "evidence_refs": []},
        ],
    })
    db = _Db(_tables([memo], playbooks=[PLAYBOOK, {**PLAYBOOK, "id": "pb-x", "sales_motion_key": "inbound"}], versions=[VERSION]))
    body = _get(db)
    assert body["status"] == "ready"
    assert body["lines"][-1] == {
        "type": "say", "text": "Precio: compáralo con un comercial más.",
        "source_ref": "obj-1", "observed_at": None, "source": "playbook",
    }
    assert body["label"] == "Pitch hecho · falta cualificar"


def test_flag_on_without_sales_motion_reads_no_playbook_and_has_no_label():
    briefs_api.set_brief_tasks(_tasks([]))
    memo = _memo({
        "playbook_observations": [{"step_id": "pitch", "status": "met", "evidence_refs": []}],
    }, sales_motion_key=None)
    db = _Db(_tables([memo], playbooks=[PLAYBOOK], versions=[VERSION]))
    body = _get(db)
    assert "playbooks_live" not in db.reads
    assert body["label"] is None


# --- Partial sub-reads are not silent ---

def test_failed_no_reply_read_marks_the_brief_partial():
    briefs_api.set_brief_tasks(_tasks([]))
    db = _Db(
        _tables([_memo()], flags=_flags(BRIEF_V2_ENABLED=True, HOY_NO_REPLY_ENABLED=True)),
        failing={"action_signals"},
    )
    body = _get(db)
    assert body["status"] == "partial"
    assert body["notice"] == "No se pudo cargar todo."
    assert body["lines"][0]["type"] == "hook"


def test_malformed_no_reply_signal_marks_the_brief_partial():
    briefs_api.set_brief_tasks(_tasks([]))
    broken = {**NO_REPLY_ROW, "payload": {"subject": "sin fecha"}}
    db = _Db(_tables([_memo()], flags=_flags(BRIEF_V2_ENABLED=True, HOY_NO_REPLY_ENABLED=True), signals=[broken]))
    body = _get(db)
    assert body["status"] == "partial"


def test_failed_playbook_read_marks_the_brief_partial():
    briefs_api.set_brief_tasks(_tasks([]))
    db = _Db(_tables([_memo()], playbooks=[PLAYBOOK], versions=[VERSION]), failing={"playbooks_live"})
    body = _get(db)
    assert body["status"] == "partial"
    assert body["label"] is None


@pytest.mark.parametrize("coverage", ["unavailable", "forbidden"])
def test_failed_crm_task_read_marks_the_brief_partial(coverage):
    briefs_api.set_brief_tasks(_tasks([], coverage))
    db = _Db(_tables([_memo()]))
    body = _get(db)
    assert body["status"] == "partial"
    assert body["notice"] == "No se pudo cargar todo."


def test_crm_task_reader_that_raises_marks_the_brief_partial():
    def boom(_company_id):
        raise RuntimeError("crm down")

    briefs_api.set_brief_tasks(boom)
    db = _Db(_tables([_memo()]))
    body = _get(db)
    assert body["status"] == "partial"


def test_no_crm_connection_is_not_a_failed_read():
    db = _Db({**_tables([_memo()]), "crm_connections": []})
    body = _get(db)
    assert "crm_connections" in db.reads
    assert body["status"] == "ready"


# --- E4 cold call: no memos. The CRM SDK layer is faked; the profile read, source map and Hoy reason run for real ---

HUBSPOT_CONN = {"id": "hubspot", "company_id": "co-1", "status": "connected", "provider": "hubspot"}
PIPEDRIVE_CONN = {"id": "pd-1", "company_id": "co-1", "status": "connected", "provider": "pipedrive"}
HUBSPOT_PROPS = {
    "jobtitle": "Directora comercial",
    "company": "Acme",
    "createdate": "2026-09-03T06:00:00Z",
    "hs_analytics_source": "ORGANIC_SEARCH",
    "hs_lead_source": "WEBFORM",
}
UNCALLED_WHY = {
    "type": "why",
    "text": None,
    "reason": "no_calls_logged",
    "since": "3 sep",
    "source_ref": "hubspot:42:",
    "observed_at": "2026-09-26T08:00:00Z",
}


def _priority_row(contact_id="42", *, owner="user-a", pain=False):
    payload = {"contacted": False, "last_call_at": None}
    if pain:
        payload = {"contacted": True, "pain_confirmed": True, "pain_at": "2026-09-25T08:00:00Z"}
    return {
        "company_id": "co-1",
        "connection_id": "hubspot",
        "contact_id": contact_id,
        "deal_id": "",
        "owner_user_id": owner,
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": "2026-09-26T08:00:00Z",
        "payload": payload,
    }


def _cold(*, connections=(HUBSPOT_CONN,), priority=(), failing=()):
    return _Db(
        {**_tables([]), "crm_connections": list(connections), "contact_priority_context": list(priority)},
        failing=failing,
    )


class _HubSpotContacts:
    def __init__(self, props, error=None):
        self.props, self.error, self.calls = props, error, []

    async def get(self, contact_id, properties=None):
        self.calls.append((contact_id, list(properties or [])))
        if self.error is not None:
            raise self.error
        return {"id": contact_id, "properties": self.props}


def _fake_hubspot(monkeypatch, props=HUBSPOT_PROPS, error=None):
    contacts = _HubSpotContacts(props, error)
    built = []

    def build(supabase, connection):
        built.append((supabase, connection.get("id")))
        return SimpleNamespace(_connection=connection)

    monkeypatch.setattr(crm_providers, "build_crm_provider", build)
    monkeypatch.setattr(HubSpotBundle, "from_provider", staticmethod(lambda _provider: SimpleNamespace(contacts=contacts)))
    return contacts, built


class _PipedriveSearch:
    def __init__(self, person, org):
        self.person, self.org = person, org

    async def get_person(self, _person_id):
        return self.person

    async def get_organization(self, _org_id):
        return self.org

    async def deals_for_person(self, _person_id, limit=8):
        return []


def _fake_pipedrive(monkeypatch, person, org):
    search = _PipedriveSearch(person, org)
    monkeypatch.setattr(
        crm_providers,
        "build_crm_provider",
        lambda _supabase, connection: SimpleNamespace(_connection=connection, _search=lambda: search),
    )


def test_cold_hubspot_contact_reads_the_sdk_and_carries_the_hoy_reason(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    contacts, _built = _fake_hubspot(monkeypatch)
    db = _cold(priority=[_priority_row()])
    body = _get(db)
    assert body["status"] == "ready"
    assert body["lines"] == [
        {
            "type": "who",
            "text": "Directora comercial en Acme · búsqueda orgánica, 3 sep",
            "source_ref": "42",
            "observed_at": "2026-09-03T06:00:00Z",
        },
        UNCALLED_WHY,
    ]
    assert contacts.calls == [("42", ["jobtitle", "company", "createdate", "hs_analytics_source"])]
    assert "playbooks_live" not in db.reads


def test_cold_hubspot_unknown_source_is_omitted(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props={**HUBSPOT_PROPS, "jobtitle": "AE", "hs_analytics_source": "AI_REFERRALS"})
    body = _get(_cold())
    assert body["lines"][0]["text"] == "AE en Acme · 3 sep"


def test_cold_hubspot_lead_source_is_not_an_origin(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props={**HUBSPOT_PROPS, "hs_analytics_source": None})
    body = _get(_cold())
    assert body["lines"][0]["text"] == "Directora comercial en Acme · 3 sep"


def test_cold_hubspot_profile_uses_the_endpoint_supabase_for_token_refresh(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _contacts, built = _fake_hubspot(monkeypatch)
    db = _cold()
    _get(db)
    assert built == [(db, "hubspot")]


def test_cold_pipedrive_contact_has_role_company_and_date_but_no_origin(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_pipedrive(
        monkeypatch,
        person={"id": 42, "name": "Ana Ruiz", "job_title": "CEO", "org_id": {"value": 7}, "label": 5, "add_time": "2026-09-03 06:00:00"},
        org={"id": 7, "name": "Acme"},
    )
    body = _get(_cold(connections=[PIPEDRIVE_CONN]), connection_id="pd-1")
    assert body["status"] == "ready"
    assert body["lines"][0]["text"] == "CEO en Acme · 3 sep"


def test_cold_salesforce_connection_has_no_who_line_and_does_not_break():
    briefs_api.set_brief_tasks(_tasks([]))
    salesforce = {"id": "sf-1", "company_id": "co-1", "status": "connected", "provider": "salesforce"}
    body = _get(_cold(connections=[salesforce]), connection_id="sf-1")
    assert body["status"] == "no_conversation"
    assert body["text"] == "Sin conversación todavía."


def test_cold_without_crm_connection_is_no_conversation_not_partial():
    briefs_api.set_brief_tasks(_tasks([]))
    body = _get(_cold(connections=[]))
    assert body["status"] == "no_conversation"
    assert body["text"] == "Sin conversación todavía."


def test_cold_without_crm_properties_falls_back_to_no_conversation(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props={})
    body = _get(_cold())
    assert body["status"] == "no_conversation"
    assert body["text"] == "Sin conversación todavía."


def test_cold_crm_profile_failure_is_partial_and_keeps_the_hoy_reason(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, error=RuntimeError("401 Unauthorized"))
    body = _get(_cold(priority=[_priority_row()]))
    assert body["status"] == "partial"
    assert body["notice"] == "No se pudo cargar todo."
    assert body["lines"] == [{**UNCALLED_WHY, "since": None}]


def test_cold_priority_read_failure_is_partial(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch)
    body = _get(_cold(failing={"contact_priority_context"}))
    assert body["status"] == "partial"
    assert [line["type"] for line in body["lines"]] == ["who"]


def test_cold_crm_task_wins_over_the_hoy_reason(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([{"remote_id": "t-1", "title": "Llamar el jueves", "contact_id": "42"}]))
    _fake_hubspot(monkeypatch)
    body = _get(_cold(priority=[_priority_row()]))
    assert body["lines"][1] == {"type": "why", "text": "Llamar el jueves", "source_ref": "t-1", "observed_at": None}


def test_cold_hoy_reason_is_computed_on_this_contact_row_only(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch)
    ahead = [_priority_row(str(100 + n), pain=True) for n in range(25)]
    db = _cold(priority=[*ahead, _priority_row()])
    body = _get(db)
    assert body["lines"][1] == UNCALLED_WHY
    reads = [(eqs, limit) for name, eqs, limit in db.queries if name == "contact_priority_context"]
    assert reads == [({"company_id": "co-1", "contact_id": "42"}, None)]


def test_cold_hoy_reason_does_not_depend_on_the_caller_owning_the_row(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch)
    body = _get(_cold(priority=[_priority_row(owner="user-b")]))
    assert body["lines"][1] == UNCALLED_WHY


# --- T4 review (BLOCKING #5): HANDOFF_ENABLED restricts a non-manager to their own memos
# plus a still-active handoff SDR's, for this contact - flag off or a manager/team rep
# keeps today's full-company read. ---

def test_handoff_restricted_user_ids_none_when_flag_off():
    membership = Membership(id="m", company_id="co-1", user_id="ae-1", role="member", status="active")
    db = _Db({"company_feature_flags": []})
    assert briefs_api._handoff_restricted_user_ids(
        db, membership, connection_id="hubspot", contact_id="42",
    ) is None


def test_handoff_restricted_user_ids_none_for_a_manager():
    membership = Membership(id="m", company_id="co-1", user_id="boss", role="admin", status="active")
    db = _Db({"company_feature_flags": _flags(HANDOFF_ENABLED=True)})
    assert briefs_api._handoff_restricted_user_ids(
        db, membership, connection_id="hubspot", contact_id="42",
    ) is None


def test_handoff_restricted_user_ids_includes_the_active_sdr():
    membership = Membership(id="m", company_id="co-1", user_id="ae-1", role="member", status="active")
    db = _Db({
        "company_feature_flags": _flags(HANDOFF_ENABLED=True),
        "deal_handoffs": [
            {"company_id": "co-1", "connection_id": "hubspot", "contact_id": "42",
             "sdr_user_id": "rep-a", "ae_user_id": "ae-1", "status": "active"},
        ],
        "company_members": [{"company_id": "co-1", "user_id": "rep-a", "status": "active"}],
    })
    result = briefs_api._handoff_restricted_user_ids(db, membership, connection_id="hubspot", contact_id="42")
    assert result == ["ae-1", "rep-a"]


def test_handoff_restricted_user_ids_excludes_an_sdr_no_longer_in_the_company():
    membership = Membership(id="m", company_id="co-1", user_id="ae-1", role="member", status="active")
    db = _Db({
        "company_feature_flags": _flags(HANDOFF_ENABLED=True),
        "deal_handoffs": [
            {"company_id": "co-1", "connection_id": "hubspot", "contact_id": "42",
             "sdr_user_id": "rep-a", "ae_user_id": "ae-1", "status": "active"},
        ],
        "company_members": [{"company_id": "co-1", "user_id": "rep-a", "status": "removed"}],
    })
    result = briefs_api._handoff_restricted_user_ids(db, membership, connection_id="hubspot", contact_id="42")
    assert result == ["ae-1"]


def test_read_memos_restricts_to_allowed_user_ids():
    own_memo = _memo(id="memo-ae", user_id="ae-1", created_at="2026-09-20T08:00:00Z")
    sdr_memo = _memo(id="memo-sdr", user_id="rep-a", created_at="2026-09-21T08:00:00Z")
    other_memo = _memo(id="memo-other", user_id="rep-b", created_at="2026-09-22T08:00:00Z")
    db = _Db({"memos": [own_memo, sdr_memo, other_memo]})
    rows, coverage = briefs_api._read_memos(
        db, "co-1", "42", allowed_user_ids=["ae-1", "rep-a"],
    )
    assert coverage == "complete"
    assert {row["id"] for row in rows} == {"memo-ae", "memo-sdr"}


def test_read_memos_empty_allowed_user_ids_skips_the_query_entirely():
    db = _Db({"memos": [_memo(id="memo-ae", user_id="ae-1")]})
    rows, coverage = briefs_api._read_memos(db, "co-1", "42", allowed_user_ids=[])
    assert rows == []
    assert coverage == "complete"
    assert "memos" not in db.reads


def test_brief_restricts_to_own_and_handoff_sdr_memos_for_a_member(monkeypatch):
    """End to end: an AE's brief for this contact is ready, restricted by HANDOFF_ENABLED
    through the same _read_memos path the unit tests above cover directly."""
    briefs_api.set_brief_tasks(_tasks([]))
    ae_membership = Membership(id="m", company_id="co-1", user_id="ae-1", role="member", status="active")
    own_memo = _memo(id="memo-ae", user_id="ae-1", created_at="2026-09-20T08:00:00Z")
    sdr_memo = _memo(id="memo-sdr", user_id="rep-a", created_at="2026-09-21T08:00:00Z")
    other_memo = _memo(id="memo-other", user_id="rep-b", created_at="2026-09-22T08:00:00Z")
    db = _Db({
        **_tables(
            [own_memo, sdr_memo, other_memo],
            flags=_flags(BRIEF_V2_ENABLED=True, HANDOFF_ENABLED=True),
        ),
        "deal_handoffs": [
            {"company_id": "co-1", "connection_id": "hubspot", "contact_id": "42",
             "sdr_user_id": "rep-a", "ae_user_id": "ae-1", "status": "active"},
        ],
        "company_members": [{"company_id": "co-1", "user_id": "rep-a", "status": "active"}],
    })
    body = _get(db, membership=ae_membership)
    assert body["status"] == "ready"


def test_brief_flag_off_keeps_reading_every_company_memo_for_the_contact():
    """Flag off (today's behaviour, unchanged): a member's brief for this contact still
    reads a teammate's memo with no restriction at all."""
    briefs_api.set_brief_tasks(_tasks([]))
    member_membership = Membership(id="m", company_id="co-1", user_id="ae-1", role="member", status="active")
    own_memo = _memo(id="memo-ae", user_id="ae-1")
    other_memo = _memo(id="memo-other", user_id="rep-b", created_at="2026-09-22T08:00:00Z")
    db = _Db(_tables([own_memo, other_memo], flags=_flags(BRIEF_V2_ENABLED=True)))
    body = _get(db, membership=member_membership)
    assert body["status"] == "ready"


def test_flag_on_with_memo_is_exactly_the_e3_brief_and_reads_no_profile(monkeypatch):
    built = []
    monkeypatch.setattr(crm_providers, "build_crm_provider", lambda *args: built.append(args))
    briefs_api.set_brief_tasks(_tasks([]))
    memo = _memo()
    db = _Db({**_tables([memo]), "crm_connections": [HUBSPOT_CONN], "contact_priority_context": [_priority_row()]})
    body = _get(db)
    expected = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name="Europe/Madrid",
        now=NOW,
        no_reply=None,
        crm_task=None,
        playbook_steps=[],
        playbook_entries=[],
    )
    assert body == json.loads(json.dumps(expected))
    assert built == []
    assert "contact_priority_context" not in db.reads


# --- T7: SALES_ROLES_ENABLED gates the SDR two-line format at the endpoint ---

def test_sdr_membership_with_sales_roles_flag_gets_two_line_brief():
    briefs_api.set_brief_tasks(_tasks([]))
    sdr_membership = Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active", sales_role="sdr",
    )
    memo = _memo()
    db = _Db(_tables([memo], flags=_flags(BRIEF_V2_ENABLED=True, SALES_ROLES_ENABLED=True)))
    body = _get(db, membership=sdr_membership)
    assert body["status"] == "ready"
    assert len(body["lines"]) <= 2


def test_null_sales_role_counts_as_general_for_the_two_line_brief():
    """D1: null sales_role behaves as general."""
    briefs_api.set_brief_tasks(_tasks([]))
    general_membership = Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active", sales_role=None,
    )
    memo = _memo()
    db = _Db(_tables([memo], flags=_flags(BRIEF_V2_ENABLED=True, SALES_ROLES_ENABLED=True)))
    body = _get(db, membership=general_membership)
    expected = prepare_brief_v2(
        coverage="complete", memos=[memo], tz_name="Europe/Madrid", now=NOW,
        no_reply=None, crm_task=None, playbook_steps=[], playbook_entries=[], sdr_two_line=True,
    )
    assert body == json.loads(json.dumps(expected))


def test_ae_membership_keeps_the_three_line_brief_even_with_sales_roles_flag_on():
    briefs_api.set_brief_tasks(_tasks([]))
    ae_membership = Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active", sales_role="ae",
    )
    memo = _memo(intelligence={
        "pain_confirmed": True,
        "evidence": [{"id": "ev-1", "quote": "se nos escapan leads", "source_type": "transcript", "source_id": "memo-1"}],
    })
    db = _Db(_tables([memo], flags=_flags(BRIEF_V2_ENABLED=True, SALES_ROLES_ENABLED=True)))
    body = _get(db, membership=ae_membership)
    expected = prepare_brief_v2(
        coverage="complete", memos=[memo], tz_name="Europe/Madrid", now=NOW,
        no_reply=None, crm_task=None, playbook_steps=[], playbook_entries=[], sdr_two_line=False,
    )
    assert body == json.loads(json.dumps(expected))


def test_sales_roles_flag_off_keeps_the_three_line_brief_for_an_sdr():
    briefs_api.set_brief_tasks(_tasks([]))
    sdr_membership = Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active", sales_role="sdr",
    )
    memo = _memo()
    db = _Db(_tables([memo], flags=_flags(BRIEF_V2_ENABLED=True)))
    body = _get(db, membership=sdr_membership)
    expected = prepare_brief_v2(
        coverage="complete", memos=[memo], tz_name="Europe/Madrid", now=NOW,
        no_reply=None, crm_task=None, playbook_steps=[], playbook_entries=[], sdr_two_line=False,
    )
    assert body == json.loads(json.dumps(expected))


# --- Lista 4 T3 (E9): BRIEF_COMPANY_HOOK_ENABLED adds one «gancho de empresa» line from
# another contact of the same company that the viewer may read. Off = unchanged. ---

def _colleague(memo_id="memo-manuel", *, user_id="user-a", contact_id="77", company="Factorial S.L.",
               created_at="2026-09-12T08:00:00Z", summary="Le interesó el fichaje. Pidió precios."):
    return {
        "id": memo_id,
        "company_id": "co-1",
        "user_id": user_id,
        "created_at": created_at,
        "capture_started_at": created_at,
        "hubspot_contact_id": contact_id,
        "hubspot_deal_id": None,
        "matched_deal_id": None,
        "playbook_version_id": None,
        "sales_motion_key": None,
        "extraction": {"companyName": company, "contactName": "Manuel García", "summary": summary},
    }


FACTORIAL_PROPS = {**HUBSPOT_PROPS, "company": "Factorial"}
MANUEL_HOOK = {
    "type": "company",
    "text": "En Factorial ya hablaste con Manuel García el 12 sep: Le interesó el fichaje.",
    "source_ref": "memo-manuel",
    "observed_at": "2026-09-12T08:00:00Z",
}


def _cold_with(colleagues, *, flags, failing=(), extra=None):
    return _Db(
        {
            **_tables(colleagues, flags=flags),
            "crm_connections": [HUBSPOT_CONN],
            "contact_priority_context": [_priority_row()],
            **(extra or {}),
        },
        failing=failing,
    )


def test_company_hook_flag_off_leaves_the_cold_brief_unchanged(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    off = _get(_cold_with([_colleague()], flags=_flags(BRIEF_V2_ENABLED=True)))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    without_colleague = _get(_cold_with([], flags=_flags(BRIEF_V2_ENABLED=True)))
    assert off == without_colleague
    assert "company" not in {line["type"] for line in off["lines"]}


def test_company_hook_on_appends_the_colleague_line_to_the_cold_brief(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    body = _get(_cold_with([_colleague()], flags=flags))
    assert body["status"] == "ready"
    assert [line["type"] for line in body["lines"]] == ["who", "why", "company"]
    assert body["lines"][-1] == MANUEL_HOOK


def test_company_hook_does_not_count_toward_max_lines(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    memo = _memo(
        {"pain_confirmed": True, "evidence": [{"id": "ev-1", "quote": "Perdemos horas"}],
         "competitor_mentions": [{"name": "Holded"}]},
        extraction={"summary": "Hablaron del almacén.", "companyName": "Factorial"},
    )
    db = _Db(_tables(
        [memo, _colleague()], flags=flags, signals=[NO_REPLY_ROW],
    ))
    db.tables["company_feature_flags"] += _flags(HOY_NO_REPLY_ENABLED=True)
    body = _get(db)
    assert [line["type"] for line in body["lines"]][-1] == "company"
    assert [line["type"] for line in body["lines"]] == ["hook", "why", "say", "company"]


def test_company_hook_on_history_brief_uses_the_memo_company_name_without_reading_the_crm(monkeypatch):
    built = []
    monkeypatch.setattr(crm_providers, "build_crm_provider", lambda *args: built.append(args))
    briefs_api.set_brief_tasks(_tasks([]))
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "companyName": "FACTORIAL"})
    db = _Db({**_tables([memo, _colleague()], flags=flags), "crm_connections": [HUBSPOT_CONN]})
    body = _get(db)
    assert body["status"] == "ready"
    assert body["lines"][-1] == {**MANUEL_HOOK, "text": MANUEL_HOOK["text"].replace("En Factorial", "En FACTORIAL")}
    assert built == []


def test_company_hook_history_brief_falls_back_to_the_crm_company(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    db = _Db({**_tables([_memo(), _colleague()], flags=flags), "crm_connections": [HUBSPOT_CONN]})
    assert _get(db)["lines"][-1] == MANUEL_HOOK


def test_company_hook_excludes_a_colleague_memo_the_member_may_not_read(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    teammate = _colleague("memo-teammate", user_id="user-b", created_at="2026-09-20T08:00:00Z")
    body = _get(_cold_with([teammate], flags=flags))
    assert "company" not in {line["type"] for line in body["lines"]}

    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    body = _get(_cold_with([teammate, _colleague()], flags=flags))
    assert body["lines"][-1]["source_ref"] == "memo-manuel"


def test_company_hook_reads_a_teammate_memo_for_a_manager_and_words_it_se_hablo(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    teammate = _colleague("memo-teammate", user_id="user-b", created_at="2026-09-20T08:00:00Z")
    admin = Membership(id="m", company_id="co-1", user_id="user-a", role="admin", status="active")
    body = _get(_cold_with([teammate, _colleague()], flags=flags), membership=admin)
    assert body["lines"][-1]["source_ref"] == "memo-teammate"
    assert body["lines"][-1]["text"].startswith("En Factorial ya se habló con Manuel García el 20 sep:")


def test_company_hook_reads_the_handoff_sdr_memo_of_that_contact_only(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True, HANDOFF_ENABLED=True)
    ae = Membership(id="m", company_id="co-1", user_id="ae-1", role="member", status="active")
    handed = _colleague("memo-handed", user_id="rep-a", contact_id="77", created_at="2026-09-10T08:00:00Z")
    not_handed = _colleague("memo-not-handed", user_id="rep-a", contact_id="88", created_at="2026-09-20T08:00:00Z")
    extra = {
        "deal_handoffs": [
            {"company_id": "co-1", "connection_id": "hubspot", "contact_id": "77",
             "sdr_user_id": "rep-a", "ae_user_id": "ae-1", "status": "active"},
        ],
        "company_members": [{"company_id": "co-1", "user_id": "rep-a", "status": "active"}],
    }
    body = _get(_cold_with([handed, not_handed], flags=flags, extra=extra), membership=ae)
    assert body["lines"][-1]["source_ref"] == "memo-handed"
    assert "ya se habló" in body["lines"][-1]["text"]


def test_company_hook_failed_colleague_read_is_just_no_line(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    real = briefs_api._colleague_memos

    def boom(*_args, **_kwargs):
        raise RuntimeError("memos down")

    monkeypatch.setattr(briefs_api, "_colleague_memos", boom)
    body = _get(_cold_with([_colleague()], flags=flags))
    monkeypatch.setattr(briefs_api, "_colleague_memos", real)
    assert body["status"] == "ready"
    assert [line["type"] for line in body["lines"]] == ["who", "why"]


def test_company_hook_without_a_crm_company_reads_no_colleagues(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props={**HUBSPOT_PROPS, "company": ""})
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    db = _cold_with([_colleague()], flags=flags)
    body = _get(db)
    assert "company" not in {line["type"] for line in body["lines"]}
    assert [name for name, eqs, _n in db.queries if name == "memos" and "hubspot_contact_id" not in eqs] == []


def test_company_hook_scan_is_capped_and_scoped_to_the_company(monkeypatch):
    briefs_api.set_brief_tasks(_tasks([]))
    _fake_hubspot(monkeypatch, props=FACTORIAL_PROPS)
    flags = _flags(BRIEF_V2_ENABLED=True, BRIEF_COMPANY_HOOK_ENABLED=True)
    db = _cold_with([_colleague()], flags=flags)
    _get(db)
    scans = [(eqs, n) for name, eqs, n in db.queries if name == "memos" and "hubspot_contact_id" not in eqs]
    assert scans == [({"company_id": "co-1"}, briefs_api.COMPANY_HOOK_SCAN)]
