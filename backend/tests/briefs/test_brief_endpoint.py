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
from app.services.briefs.contact_read import ContactProfileReadFailed
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
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
    "playbook_versions": _columns("040_company_playbooks.sql", "playbook_versions"),
}


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.eqs, self.desc, self.n = [], False, None

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

    def order(self, _column, desc=False):
        self.desc = desc
        return self

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        self.db.reads.append(self.name)
        if self.name in self.db.failing:
            raise RuntimeError(f"{self.name} down")
        rows = [row for row in self.db.tables.get(self.name, []) if all(row.get(c) == v for c, v in self.eqs)]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=self.desc)
        return SimpleNamespace(data=rows[: self.n] if self.n else rows)


class _Db:
    def __init__(self, tables, failing=()):
        self.tables = tables
        self.failing = set(failing)
        self.reads: list[str] = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(briefs_api, "rep_timezone", lambda _user_id: "Europe/Madrid")
    monkeypatch.setattr(briefs_api, "_now", lambda: NOW)
    briefs_api.set_brief_tasks(None)
    briefs_api.set_brief_profile_reader(None)
    yield
    briefs_api.set_brief_tasks(None)
    briefs_api.set_brief_profile_reader(None)
    feature_flags.clear_cache()


def _get(db, **params):
    app = FastAPI()
    app.include_router(briefs_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
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
    assert body["lines"][1]["text"] == "Pidió que la llamaras hoy."


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
    assert "playbooks" not in db.reads
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
    db = _Db(_tables([_memo()], playbooks=[PLAYBOOK], versions=[VERSION]), failing={"playbooks"})
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


# --- E4 cold call: no memos ---

COLD_PLAYBOOK = {"id": "pb-cold", "company_id": "co-1", "sales_motion_key": "outbound", "active_version_id": "v-cold"}
COLD_VERSION = {
    "id": "v-cold",
    "playbook_id": "pb-cold",
    "status": "published",
    "steps": [
        {
            "step_id": "opening",
            "label": "Apertura",
            "criterion": "Saluda",
            "reference_phrase": "Hola, soy Toni de Vocify.",
        },
    ],
    "entries": [],
}


def _profile(**extra):
    base = {
        "jobtitle": "Directora comercial",
        "company_name": "Acme",
        "source_label": "lead de formulario web",
        "created_at": "2026-09-03T08:00:00+02:00",
        "sales_motion_key": "outbound",
        "source_ref": "42",
    }
    base.update(extra)
    return base


def _priority_context(contact_id="42", reason="no_calls_logged"):
    return [{
        "company_id": "co-1",
        "connection_id": "hubspot",
        "contact_id": contact_id,
        "deal_id": "",
        "owner_user_id": "user-a",
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": "2026-09-26T08:00:00Z",
        "payload": {"contacted": False, "last_call_at": None},
    }]


def test_flag_on_cold_contact_with_full_crm_profile():
    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(lambda _conn, _cid: _profile())
    db = _Db({
        **_tables([], playbooks=[COLD_PLAYBOOK], versions=[COLD_VERSION]),
        "contact_priority_context": _priority_context(),
        "crm_connections": [{"id": "hubspot", "company_id": "co-1", "status": "connected", "provider": "hubspot"}],
    })
    body = _get(db)
    assert body["status"] == "ready"
    assert [line["type"] for line in body["lines"]] == ["who", "why", "open"]
    assert body["lines"][0]["text"] == "Directora comercial en Acme · lead de formulario web, 3 sep"
    assert body["lines"][1]["text"] == "Nuevo, sin llamar desde el 3 sep"
    assert body["lines"][2]["source"] == "playbook"


def test_flag_on_cold_contact_without_crm_data_falls_back_to_no_conversation():
    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(lambda _conn, _cid: {})
    db = _Db(_tables([]))
    body = _get(db)
    assert body["status"] == "no_conversation"
    assert body["text"] == "Sin conversación todavía."


def test_flag_on_cold_contact_crm_profile_failure_is_partial():
    def boom(_conn, _cid):
        raise ContactProfileReadFailed("down")

    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(boom)
    db = _Db(_tables([]))
    body = _get(db)
    assert body["status"] == "partial"
    assert body["notice"] == "No se pudo cargar todo."


def test_flag_on_cold_hubspot_profile_reader_is_used():
    seen = []

    def reader(conn, cid):
        seen.append((conn.get("provider"), cid))
        return _profile(jobtitle="AE")

    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(reader)
    db = _Db({
        **_tables([]),
        "crm_connections": [{"id": "hubspot", "company_id": "co-1", "status": "connected", "provider": "hubspot"}],
    })
    body = _get(db)
    assert seen == [("hubspot", "42")]
    assert body["lines"][0]["text"] == "AE en Acme · lead de formulario web, 3 sep"


def test_flag_on_cold_pipedrive_profile_reader_is_used():
    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(
        lambda conn, _cid: _profile(jobtitle="CEO", company_name="Acme", source_label=None) if conn.get("provider") == "pipedrive" else {},
    )
    db = _Db({
        **_tables([]),
        "crm_connections": [{"id": "pd-1", "company_id": "co-1", "status": "connected", "provider": "pipedrive"}],
    })
    body = _get(db, connection_id="pd-1")
    assert body["lines"][0]["text"] == "CEO en Acme · 3 sep"


def test_flag_on_cold_without_opening_step_has_no_open_line():
    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(lambda _conn, _cid: _profile())
    version = {**COLD_VERSION, "steps": [{"step_id": "pitch", "label": "Pitch", "criterion": "Explicó"}]}
    db = _Db(_tables([], playbooks=[COLD_PLAYBOOK], versions=[version]))
    body = _get(db)
    assert [line["type"] for line in body["lines"]] == ["who"]


def test_flag_on_with_memo_is_unchanged_from_e3():
    briefs_api.set_brief_tasks(_tasks([]))
    briefs_api.set_brief_profile_reader(lambda _conn, _cid: _profile())
    db = _Db(_tables([_memo()]))
    body = _get(db)
    assert body["lines"][0]["type"] == "hook"
    assert "who" not in {line["type"] for line in body["lines"]}
