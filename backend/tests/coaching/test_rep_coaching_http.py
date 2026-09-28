"""GET /coaching/me/* and /coaching/examples: self-scope, per-flow, anonymous examples."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-rep-coaching-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-rep-coaching-32")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import coaching as coaching_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from tests.reporting.fake_db import FakeDB

COMPANY = "77777777-7777-7777-7777-777777777777"
REP = "88888888-8888-8888-8888-888888888888"
PEER = "66666666-6666-6666-6666-666666666666"
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)  # Thursday
STEPS = [
    {"step_id": "open", "label": "Apertura", "criterion": "Se presenta", "example": "Hola, soy Ana"},
    {"step_id": "pain", "label": "Dolor", "criterion": "Pregunta por el dolor"},
]


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch):
    real = coaching_api.madrid_week_bounds
    monkeypatch.setattr(coaching_api, "madrid_week_bounds", lambda *, now=None: real(now=now or NOW))


def _memo(memo_id, user, statuses, *, days_ago=0, motion="discovery", agreed=False, quotes=None, **over):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    obs = [
        {"step_id": sid, "label": sid, "criterion": "", "status": st, "quote": (quotes or {}).get(sid)}
        for sid, st in statuses.items()
    ]
    memo = {
        "id": memo_id, "user_id": user, "company_id": COMPANY, "sales_motion_key": motion,
        "screening_outcome": "connected", "audio_duration": 90, "rep_outcome": None,
        "capture_started_at": at, "created_at": at,
        "extraction": {"summary": f"Resumen {memo_id}", "intelligence": {
            "playbook_observations": obs, "meeting": {"agreed": agreed}}},
    }
    memo.update(over)
    return memo


def _client(memos, *, sales_role="sdr", published=("discovery",), patterns=None, fail_tables=()):
    app = FastAPI()
    app.include_router(coaching_api.router)
    playbooks, versions = [], []
    for motion in published:
        playbooks.append({"id": f"pb-{motion}", "company_id": COMPANY, "sales_motion_key": motion, "active_version_id": f"v-{motion}"})
        versions.append({"id": f"v-{motion}", "playbook_id": f"pb-{motion}", "status": "published", "steps": STEPS,
                         "entries": [{"category": "price", "guidance": "Habla de valor"}]})
    store = FakeDB({
        "memos": memos, "playbooks": playbooks, "playbook_versions": versions,
        "interaction_patterns": patterns or [],
        "company_members": [
            {"id": "mem-1", "company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
            {"id": "mem-2", "company_id": COMPANY, "user_id": PEER, "role": "member", "status": "active"},
        ],
    })
    store.fail_tables = set(fail_tables)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=REP, role="member", status="active", sales_role=sales_role,
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def test_summary_no_playbook_is_not_invented():
    client = _client([_memo("m1", REP, {"open": "met"})], published=())
    body = client.get("/api/v1/coaching/me/summary").json()
    assert body["playbook_published"] is False
    assert body["steps"] == [] and body["focus"] is None and body["conversion"] is None
    assert body["numbers"]["interactions"] == 0
    for path in ("/coaching/me/interactions", "/coaching/me/process", "/coaching/examples"):
        data = client.get(f"/api/v1{path}").json()
        assert all(v == [] for k, v in data.items() if k != "weeks")


def test_summary_self_scope_and_focus():
    memos = [
        _memo("p1", REP, {"open": "missed", "pain": "met"}, days_ago=7),
        _memo("p2", REP, {"open": "missed", "pain": "met"}, days_ago=8),
        _memo("p3", REP, {"open": "met", "pain": "met"}, days_ago=9),
        _memo("t1", REP, {"open": "met", "pain": "met"}, days_ago=1, agreed=True),
        _memo("x1", PEER, {"open": "missed", "pain": "missed"}, days_ago=1),
    ]
    body = _client(memos).get("/api/v1/coaching/me/summary").json()
    assert body["flow"] == "sdr" and body["motion"] == "discovery" and body["playbook_published"] is True
    assert body["week_start"] == "2026-09-21"
    assert body["numbers"] == {"conversations": 1, "meetings_agreed": 1, "process_complete": 1, "interactions": 1}
    assert body["prev_numbers"]["interactions"] == 3
    opening = next(s for s in body["steps"] if s["step_id"] == "open")
    assert opening["rate"] == 1.0 and opening["prev_rate"] == pytest.approx(0.3333, abs=1e-3)
    assert body["focus"]["step_id"] == "open" and body["focus"]["criterion"] == "Se presenta"
    assert body["focus"]["example"] == "Hola, soy Ana"
    assert len(body["focus"]["progress"]) == 5
    assert body["focus"]["week_total"] == {"done": 1, "applicable": 1, "rate": 1.0}
    assert body["focus"]["achieved"] is False
    assert body["conversion"] is None


def test_ae_flow_uses_closing_playbook():
    memos = [_memo("c1", REP, {"open": "met"}, motion="closing"), _memo("d1", REP, {"open": "met"}, motion="discovery")]
    body = _client(memos, sales_role="ae", published=("closing",)).get("/api/v1/coaching/me/summary").json()
    assert body["flow"] == "ae" and body["motion"] == "closing" and body["numbers"]["interactions"] == 1
    assert _client(memos, sales_role="ae", published=("discovery",)).get("/api/v1/coaching/me/summary").json()["playbook_published"] is False


def test_general_role_picks_flow_with_most_interactions():
    memos = [_memo(f"c{i}", REP, {"open": "met"}, motion="closing") for i in range(2)] + [_memo("d", REP, {"open": "met"})]
    body = _client(memos, sales_role=None, published=("discovery", "closing")).get("/api/v1/coaching/me/summary").json()
    assert body["flow"] == "ae"


def test_rep_outcome_column_missing_is_tolerated():
    client = _client([_memo("m1", REP, {"open": "met"}, rep_outcome="meeting_booked")])
    assert client.get("/api/v1/coaching/me/summary").json()["numbers"]["meetings_agreed"] == 1
    from app.services.coaching import rep_coaching_reads as reads

    class _NoOutcome:
        def __init__(self, inner):
            self.inner = inner

        def table(self, name):
            query = self.inner.table(name)
            select = query.select

            def guarded(columns, *a, **k):
                if "rep_outcome" in columns:
                    raise RuntimeError("column memos.rep_outcome does not exist")
                return select(columns, *a, **k)

            query.select = guarded
            return query

    inner = client.app.dependency_overrides[get_supabase]()
    memos = reads.load_memos(_NoOutcome(inner), COMPANY, [REP], start=NOW - timedelta(days=30))
    assert [m["id"] for m in memos] == ["m1"]


def test_interactions_filters_and_order():
    memos = [
        _memo("a", REP, {"open": "met", "pain": "missed"}, days_ago=3),
        _memo("b", REP, {"open": "missed", "pain": "met"}, days_ago=1, agreed=True),
        _memo("c", REP, {"open": "met", "pain": "met"}, days_ago=2),
        _memo("z", PEER, {"open": "met"}, days_ago=1),
        _memo("old", REP, {"open": "met"}, days_ago=90),
    ]
    client = _client(memos)
    ids = lambda q: [i["memo_id"] for i in client.get(f"/api/v1/coaching/me/interactions{q}").json()["items"]]
    assert ids("") == ["b", "c", "a"]
    assert ids("?limit=2") == ["b", "c"]
    assert ids("?step_id=open&state=missing") == ["b"]
    assert ids("?state=missing") == ["a", "b"] or ids("?state=missing") == ["b", "a"]
    assert ids("?meeting=true") == ["b"]
    assert ids("?meeting=false") == ["c", "a"]
    assert client.get("/api/v1/coaching/me/interactions?state=bogus").status_code == 422
    item = client.get("/api/v1/coaching/me/interactions").json()["items"][0]
    assert item["steps"][0] == {"step_id": "open", "label": "open", "state": "missing", "quote": None}


def test_process_by_week_and_objections():
    memos = [
        _memo("a", REP, {"open": "met", "pain": "missed"}, days_ago=1),
        _memo("b", REP, {"open": "missed", "pain": "missed"}, days_ago=8),
    ]
    patterns = [
        {"memo_id": "a", "category": "price", "kind": "objection", "resolution": "resolved", "created_at": NOW.isoformat()},
        {"memo_id": "a", "category": "price", "kind": "objection", "resolution": "open", "created_at": NOW.isoformat()},
        {"memo_id": "zzz", "category": "timing", "kind": "objection", "resolution": "open", "created_at": NOW.isoformat()},
    ]
    body = _client(memos, patterns=patterns).get("/api/v1/coaching/me/process?weeks=3").json()
    assert body["weeks"] == ["2026-09-07", "2026-09-14", "2026-09-21"]
    opening = next(s for s in body["steps"] if s["step_id"] == "open")
    assert [w["applicable"] for w in opening["by_week"]] == [0, 1, 1]
    assert opening["by_week"][0]["rate"] is None and opening["rate"] == 0.5
    assert body["objections"] == [{"category": "price", "total": 2, "resolved": 1, "open": 1}]


def test_examples_are_anonymous_and_from_winning_peers():
    memos = [
        _memo("w1", PEER, {"open": "met"}, agreed=True, quotes={"open": "Buenas, soy Luis"}),
        _memo("w2", PEER, {"open": "met"}, agreed=False, quotes={"open": "no cuenta"}),
        _memo("mine", REP, {"open": "met"}, agreed=True, quotes={"open": "mi cita"}),
    ]
    patterns = [{"memo_id": "w1", "category": "price", "kind": "objection", "resolution": "resolved",
                 "response": "Mostré el ROI", "created_at": NOW.isoformat()}]
    response = _client(memos, patterns=patterns).get("/api/v1/coaching/examples")
    body = response.json()
    opening = next(s for s in body["steps"] if s["step_id"] == "open")
    assert opening["moments"] == [{"quote": "Buenas, soy Luis"}]
    assert opening["example"] == "Hola, soy Ana"
    assert body["objections"] == [{"category": "price", "guidance": "Habla de valor", "best_response": "Mostré el ROI"}]
    text = response.text
    assert PEER not in text and "w1" not in text and "mine" not in text and "mi cita" not in text


def test_memo_reads_page_past_the_postgrest_row_cap(monkeypatch):
    """A busy team's four weeks exceed one PostgREST page; nothing is silently dropped."""
    from app.services.coaching import rep_coaching_reads as reads

    monkeypatch.setattr(reads, "_PAGE_SIZE", 2)
    db = FakeDB()
    db.tables["memos"] = [
        {"id": f"m{i}", "user_id": REP, "company_id": COMPANY, "created_at": (NOW - timedelta(hours=i)).isoformat()}
        for i in range(5)
    ]
    rows = reads.load_memos(db, COMPANY, [REP], start=NOW - timedelta(days=1))
    assert sorted(r["id"] for r in rows) == [f"m{i}" for i in range(5)]
