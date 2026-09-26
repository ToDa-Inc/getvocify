"""F16 T2: the rep home reads. Off is a missing route, only the rep's own data, and the day is the rep's."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import followup as followup_api
from app.api import memos as memos_api
from app.api import today as today_api
from app.api.router import api_router
from app.deps import get_membership, get_supabase, get_user_id
from app.services import feature_flags
from app.services.coaching import brief_preferences
from app.services.company import Membership

# Saturday 26 Sep 2026, 12:00 in Madrid (CEST, UTC+2). Madrid midnight = 25 Sep 22:00Z.
NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
COMPANY = "co-1"
REP = "user-rep"
OWNER = "user-owner"
OTHER = "user-other"
FLAG = "REP_WORKSPACE_ENABLED"


class _Result:
    def __init__(self, data):
        self.data = data


def _read(row: dict, column: str):
    if "->>" in column:
        head, key = column.split("->>", 1)
        value = row.get(head)
        return value.get(key) if isinstance(value, dict) else None
    return row.get(column)


def _instant(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


class _Query:
    def __init__(self, store: "_Store", name: str):
        self._store = store
        self._name = name
        self._filters: list = []
        self._order = None
        self._limit = None
        self._offset = 0

    def _log(self, *entry):
        self._store.log.append((self._name, *entry))

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._log("eq", column, value)
        self._filters.append(lambda row: _read(row, column) == value)
        return self

    def in_(self, column, values):
        allowed = set(values)
        self._log("in", column, tuple(sorted(allowed)))
        self._filters.append(lambda row: _read(row, column) in allowed)
        return self

    def gte(self, column, value):
        self._log("gte", column, value)
        bound = _instant(value)

        def keep(row):
            current = _read(row, column)
            return current is not None and _instant(current) >= bound

        self._filters.append(keep)
        return self

    def or_(self, expression):
        self._log("or", expression)
        clauses = [clause.split(".", 2) for clause in expression.split(",")]

        def keep(row):
            for column, op, value in clauses:
                current = row.get(column)
                if op == "eq" and current == value:
                    return True
                if op == "is" and value == "null" and current is None:
                    return True
            return False

        self._filters.append(keep)
        return self

    def order(self, column, desc=False):
        self._log("order", column, desc)
        self._order = (column, desc)
        return self

    def limit(self, count):
        self._log("limit", count)
        self._limit = count
        return self

    def offset(self, count):
        self._log("offset", count)
        self._offset = count
        return self

    def execute(self):
        rows = [row for row in self._store.tables.get(self._name, []) if all(keep(row) for keep in self._filters)]
        if self._order:
            column, desc = self._order
            rows.sort(key=lambda row: _instant(row.get(column)), reverse=desc)
        rows = rows[self._offset:]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result([dict(row) for row in rows])


class _Store:
    def __init__(self, *, flag_on: bool = True):
        self.tables: dict[str, list[dict]] = {
            "company_feature_flags": [{"company_id": COMPANY, "flag": FLAG, "enabled": True}] if flag_on else [],
            "memos": [],
            "action_signals": [],
            "outbound_calls": [],
        }
        self.log: list[tuple] = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(brief_preferences, "_supabase", None)
    monkeypatch.setattr(followup_api, "_now", lambda: NOW, raising=False)
    monkeypatch.setattr(memos_api, "load_viewer_scope", lambda _supabase, _user_id: (None, [], {}))
    today_api._CLOCK[0] = NOW
    yield
    today_api._CLOCK[0] = today_api._CLOCK_DEFAULT
    feature_flags.clear_cache()


def _client(store: _Store, *, user: str = REP, role: str = "member") -> TestClient:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=user, role=role, status="active",
    )
    app.dependency_overrides[get_user_id] = lambda: user
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def _uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _memo(n: int, **overrides) -> dict:
    row = {
        "id": _uuid(n),
        "user_id": REP,
        "company_id": COMPANY,
        "status": "approved",
        "audio_duration": 60.0,
        "hubspot_contact_id": f"contact-{n}",
        "extraction": {"summary": "Resumen", "contactName": f"Contacto {n}", "companyName": f"Empresa {n}"},
        "followup": None,
        "screening_outcome": None,
        "capture_started_at": None,
        "created_at": (NOW - timedelta(days=1)).isoformat(),
    }
    row.update(overrides)
    return row


def _ready(subject: str = "Números que vimos", **extra) -> dict:
    return {
        "status": "ready",
        "subject": subject,
        "body": "Hola, te paso los números.",
        "started_at": "2026-09-25T09:59:00+00:00",
        "ready_at": "2026-09-25T10:00:00+00:00",
        **extra,
    }


def _commitment(due_at: str, text: str = "Enviar la propuesta", **extra) -> dict:
    return {
        "id": f"com-{due_at}-{text}",
        "kind": "send",
        "origin": "rep_promise",
        "text": text,
        "due_at": due_at,
        "temporal_precision": "time",
        "evidence_refs": ["ev-1"],
        **extra,
    }


def _with_commitments(n: int, commitments: list[dict], **overrides) -> dict:
    extraction = {
        "summary": "Resumen",
        "contactName": f"Contacto {n}",
        "companyName": f"Empresa {n}",
        "intelligence": {"version": 1, "commitments": commitments},
    }
    return _memo(n, extraction=extraction, **overrides)


def _signal(n: int, **overrides) -> dict:
    row = {
        "id": f"sig-{n}",
        "company_id": COMPANY,
        "user_id": REP,
        "connection_id": "crm-A",
        "contact_id": f"contact-{n}",
        "deal_id": None,
        "memo_id": _uuid(n),
        "type": "commitment_due",
        "dedupe_key": f"commitment:{n}",
        "payload": {"text": "Llamar"},
        "status": "resolved",
        "version": 2,
        "previous_status": "pending",
        "last_action_request_id": f"act-{n}",
        "last_action_at": "2026-09-26T08:00:00+00:00",
        "undo_deadline": "2026-09-26T08:00:05+00:00",
        "snoozed_until": None,
    }
    row.update(overrides)
    return row


def _call(n: int, **overrides) -> dict:
    row = {
        "carrier_call_id": f"call-{n}",
        "user_id": REP,
        "hubspot_contact_id": f"contact-{n}",
        "memo_id": _uuid(n),
        "status": "logged",
        "call_disposition": "connected",
        "created_at": "2026-09-26T09:00:00+00:00",
        "answered_at": "2026-09-26T09:00:10+00:00",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------- flag


def test_flag_off_hides_the_three_reads():
    client = _client(_Store(flag_on=False))
    for path in (
        "/api/v1/followups",
        "/api/v1/followups?status=bogus",
        "/api/v1/today/upcoming",
        "/api/v1/today/upcoming?days=99",
        "/api/v1/today/done",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json() == {"detail": "Not Found"}, path


def test_flag_on_serves_the_three_reads():
    client = _client(_Store())
    for path in ("/api/v1/followups", "/api/v1/today/upcoming", "/api/v1/today/done"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json() == [], path


# ---------------------------------------------------------------- /followups


def test_followups_only_list_the_author_drafts():
    store = _Store()
    store.tables["memos"] = [_memo(1, followup=_ready())]
    owner = _client(store, user=OWNER, role="owner").get("/api/v1/followups")
    assert owner.status_code == 200
    assert owner.json() == []
    rep = _client(store).get("/api/v1/followups")
    assert rep.json() == [
        {
            "memo_id": _uuid(1),
            "contact_id": "contact-1",
            "contact_name": "Contacto 1",
            "company_name": "Empresa 1",
            "subject": "Números que vimos",
            "status": "ready",
            "generated_at": "2026-09-25T10:00:00+00:00",
        }
    ]


def test_ready_excludes_sent_and_generating_and_keeps_copied():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, followup={**_ready(), "status": "sent", "sent_at": "2026-09-26T08:00:00+00:00"}),
        _memo(2, followup={"status": "generating", "started_at": "2026-09-26T09:59:00+00:00"}),
        _memo(3, followup=_ready(copied_at="2026-09-26T08:30:00+00:00", final_subject="Asunto final")),
        _memo(4, followup=None),
    ]
    rows = _client(store).get("/api/v1/followups?status=ready").json()
    assert [row["memo_id"] for row in rows] == [_uuid(3)]
    assert rows[0]["subject"] == "Asunto final"


def test_followups_accepts_generating_and_unavailable():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, followup={"status": "generating", "started_at": "2026-09-26T09:59:00+00:00"},
              created_at="2026-09-26T09:58:00+00:00"),
        _memo(2, followup={"status": "unavailable", "reason": "error", "started_at": "2026-09-26T09:00:00+00:00"},
              created_at="2026-09-26T08:58:00+00:00"),
        _memo(3, followup=_ready(), created_at="2026-09-26T07:00:00+00:00"),
    ]
    rows = _client(store).get("/api/v1/followups?status=generating,unavailable").json()
    assert [(row["memo_id"], row["status"], row["subject"]) for row in rows] == [
        (_uuid(1), "generating", None),
        (_uuid(2), "unavailable", None),
    ]
    assert rows[0]["generated_at"] == "2026-09-26T09:59:00+00:00"


def test_followups_window_is_seven_days_newest_first():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, followup=_ready(), created_at=(NOW - timedelta(days=8)).isoformat()),
        _memo(2, followup=_ready(), created_at=(NOW - timedelta(days=6)).isoformat()),
        _memo(3, followup=_ready(), created_at=(NOW - timedelta(hours=2)).isoformat()),
    ]
    rows = _client(store).get("/api/v1/followups").json()
    assert [row["memo_id"] for row in rows] == [_uuid(3), _uuid(2)]


def test_followups_rejects_sent_and_unknown_status():
    client = _client(_Store())
    assert client.get("/api/v1/followups?status=sent").status_code == 422
    assert client.get("/api/v1/followups?status=ready,nope").status_code == 422


# ---------------------------------------------------------------- /memos?status


def test_memos_status_filter_keeps_only_that_status():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, status="pending_review"),
        _memo(2, status="approved"),
        _memo(3, status="pending_review", user_id=OTHER),
        _memo(4, status="failed"),
    ]
    response = _client(store).get("/api/v1/memos?status=pending_review&limit=5")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [_uuid(1)]
    assert ("memos", "eq", "status", "pending_review") in store.log


def test_memos_without_status_is_unchanged():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, status="pending_review", created_at="2026-09-26T09:00:00+00:00"),
        _memo(2, status="approved", created_at="2026-09-26T08:00:00+00:00"),
        _memo(3, status="failed", created_at="2026-09-26T07:00:00+00:00"),
    ]
    response = _client(store).get("/api/v1/memos")
    assert response.status_code == 200
    assert [(row["id"], row["status"]) for row in response.json()] == [
        (_uuid(1), "pending_review"),
        (_uuid(2), "approved"),
        (_uuid(3), "failed"),
    ]
    memo_calls = [entry[1:] for entry in store.log if entry[0] == "memos"]
    assert memo_calls == [
        ("order", "created_at", True),
        ("limit", 20),
        ("offset", 0),
        ("eq", "user_id", REP),
    ]


def test_memos_unknown_status_is_422():
    assert _client(_Store()).get("/api/v1/memos?status=archived").status_code == 422


# ---------------------------------------------------------------- /today/upcoming


def test_upcoming_window_follows_madrid_days():
    store = _Store()
    store.tables["memos"] = [
        _with_commitments(1, [
            _commitment("2026-09-26T23:30:00+02:00", "Hoy a última hora"),
            _commitment("2026-09-27T00:30:00+02:00", "Mañana temprano"),
            _commitment("2026-10-03T23:59:00+02:00", "Último día"),
            _commitment("2026-10-04T00:00:00+02:00", "Fuera de la ventana"),
            _commitment("2026-09-28T00:00:00+02:00", "Solo el día", temporal_precision="date"),
        ]),
    ]
    rows = _client(store).get("/api/v1/today/upcoming?days=7").json()
    assert [row["text"] for row in rows] == ["Mañana temprano", "Solo el día", "Último día"]
    assert rows[1]["precision"] == "date"
    assert rows[0] == {
        "memo_id": _uuid(1),
        "contact_id": "contact-1",
        "contact_name": "Contacto 1",
        "company_name": "Empresa 1",
        "text": "Mañana temprano",
        "due_at": "2026-09-27T00:30:00+02:00",
        "precision": "time",
        "crm_task_id": None,
    }


def test_upcoming_follows_the_rep_zone(monkeypatch):
    monkeypatch.setitem(brief_preferences._STORE, REP, {"timezone": "Atlantic/Canary"})
    store = _Store()
    # 00:30 tomorrow in Madrid is still 23:30 today in the Canaries.
    store.tables["memos"] = [
        _with_commitments(1, [
            _commitment("2026-09-26T22:30:00+00:00", "Aún hoy en Canarias"),
            _commitment("2026-09-26T23:30:00+00:00", "Mañana en Canarias"),
        ]),
    ]
    rows = _client(store).get("/api/v1/today/upcoming").json()
    assert [row["text"] for row in rows] == ["Mañana en Canarias"]


def test_upcoming_carries_the_crm_task_id_or_null():
    store = _Store()
    store.tables["memos"] = [
        _with_commitments(1, [
            _commitment("2026-09-28T10:00:00+02:00", "Con tarea", crm_task_id="task-77"),
            _commitment("2026-09-29T10:00:00+02:00", "Sin tarea"),
        ]),
    ]
    rows = _client(store).get("/api/v1/today/upcoming").json()
    assert [(row["text"], row["crm_task_id"]) for row in rows] == [("Con tarea", "task-77"), ("Sin tarea", None)]


def test_upcoming_ignores_other_reps():
    store = _Store()
    store.tables["memos"] = [
        _with_commitments(1, [_commitment("2026-09-28T10:00:00+02:00", "Mío")]),
        _with_commitments(2, [_commitment("2026-09-28T11:00:00+02:00", "De otro")], user_id=OTHER),
    ]
    rows = _client(store).get("/api/v1/today/upcoming").json()
    assert [row["text"] for row in rows] == ["Mío"]


def test_upcoming_lists_the_same_commitment_once():
    store = _Store()
    repeated = _commitment("2026-09-28T10:00:00+02:00", "Enviar el caso")
    store.tables["memos"] = [_with_commitments(1, [repeated, dict(repeated)])]
    rows = _client(store).get("/api/v1/today/upcoming").json()
    assert [row["text"] for row in rows] == ["Enviar el caso"]


def test_upcoming_newest_conversation_with_the_contact_decides():
    store = _Store()
    older = _with_commitments(
        1, [_commitment("2026-09-28T10:00:00+02:00", "Superado")],
        hubspot_contact_id="contact-9", created_at=(NOW - timedelta(days=3)).isoformat(),
    )
    newer = _with_commitments(
        2, [], hubspot_contact_id="contact-9", created_at=(NOW - timedelta(days=1)).isoformat(),
    )
    store.tables["memos"] = [older, newer]
    assert _client(store).get("/api/v1/today/upcoming").json() == []


def test_upcoming_days_bounds():
    store = _Store()
    store.tables["memos"] = [
        _with_commitments(1, [
            _commitment("2026-09-27T10:00:00+02:00", "Mañana"),
            _commitment("2026-10-09T10:00:00+02:00", "Día 13"),
        ]),
    ]
    client = _client(store)
    assert client.get("/api/v1/today/upcoming?days=0").status_code == 422
    assert client.get("/api/v1/today/upcoming?days=15").status_code == 422
    assert [row["text"] for row in client.get("/api/v1/today/upcoming?days=1").json()] == ["Mañana"]
    assert [row["text"] for row in client.get("/api/v1/today/upcoming?days=14").json()] == ["Mañana", "Día 13"]


# ---------------------------------------------------------------- /today/done


def test_done_resets_at_local_midnight():
    store = _Store()
    store.tables["memos"] = [_memo(1), _memo(2)]
    store.tables["action_signals"] = [
        _signal(1, last_action_at="2026-09-25T21:59:00+00:00", undo_deadline="2026-09-25T21:59:05+00:00"),
        _signal(2, last_action_at="2026-09-25T22:01:00+00:00", undo_deadline="2026-09-25T22:01:05+00:00"),
    ]
    rows = _client(store).get("/api/v1/today/done").json()
    assert rows == [
        {"kind": "signal", "contact_name": "Contacto 2", "at": "2026-09-25T22:01:00+00:00", "memo_id": _uuid(2)},
    ]


def test_done_counts_only_signals_the_rep_resolved():
    store = _Store()
    store.tables["memos"] = [_memo(n) for n in range(1, 7)]
    store.tables["action_signals"] = [
        _signal(1),
        _signal(2, status="dismissed"),
        _signal(3, status="snoozed", snoozed_until="2026-09-27T08:00:00+00:00"),
        _signal(4, last_action_at=None, undo_deadline=None, last_action_request_id=None),
        _signal(5, undo_deadline=None),
        _signal(6, previous_status="snoozed"),
    ]
    rows = _client(store).get("/api/v1/today/done").json()
    assert [(row["kind"], row["memo_id"]) for row in rows] == [("signal", _uuid(1))]


def test_done_lists_follow_ups_sent_today():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, followup={**_ready(), "status": "sent", "sent_at": "2026-09-26T08:15:00.123456+00:00"}),
        _memo(2, followup={**_ready(), "status": "sent", "sent_at": "2026-09-25T21:00:00+00:00"}),
        _memo(3, followup=_ready(copied_at="2026-09-26T08:30:00+00:00")),
    ]
    rows = _client(store).get("/api/v1/today/done").json()
    assert rows == [
        {"kind": "followup", "contact_name": "Contacto 1", "at": "2026-09-26T08:15:00.123456+00:00", "memo_id": _uuid(1)},
    ]


def test_done_counts_only_connected_calls():
    store = _Store()
    store.tables["memos"] = [_memo(n) for n in range(1, 6)]
    store.tables["outbound_calls"] = [
        _call(1),
        _call(2, call_disposition="voicemail"),
        _call(3, call_disposition="no_response"),
        _call(4, call_disposition=None, status="recorded"),
        _call(5, call_disposition="busy", answered_at=None),
        _call(6, memo_id=None, hubspot_contact_id="contact-1", created_at="2026-09-25T21:30:00+00:00"),
    ]
    rows = _client(store).get("/api/v1/today/done").json()
    assert rows == [
        {"kind": "call", "contact_name": "Contacto 1", "at": "2026-09-26T09:00:10+00:00", "memo_id": _uuid(1)},
    ]


def test_done_ignores_other_reps():
    store = _Store()
    store.tables["memos"] = [
        _memo(1, user_id=OTHER, followup={**_ready(), "status": "sent", "sent_at": "2026-09-26T08:00:00+00:00"}),
    ]
    store.tables["action_signals"] = [_signal(1, user_id=OTHER)]
    store.tables["outbound_calls"] = [_call(1, user_id=OTHER)]
    assert _client(store).get("/api/v1/today/done").json() == []


def test_done_caps_at_fifty_newest_first():
    store = _Store()
    store.tables["memos"] = [_memo(1)]
    base = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)
    store.tables["action_signals"] = [
        _signal(1, id=f"sig-{n}", dedupe_key=f"k-{n}", last_action_at=(base + timedelta(minutes=n)).isoformat(),
                undo_deadline=(base + timedelta(minutes=n, seconds=5)).isoformat())
        for n in range(60)
    ]
    store.tables["outbound_calls"] = [_call(1, created_at="2026-09-26T09:30:00+00:00", answered_at=None)]
    rows = _client(store).get("/api/v1/today/done").json()
    assert len(rows) == 50
    assert rows[0] == {"kind": "call", "contact_name": "Contacto 1", "at": "2026-09-26T09:30:00+00:00", "memo_id": _uuid(1)}
    stamps = [datetime.fromisoformat(row["at"]) for row in rows]
    assert stamps == sorted(stamps, reverse=True)
    assert rows[-1]["at"] == (base + timedelta(minutes=11)).isoformat()
