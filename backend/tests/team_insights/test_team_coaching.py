"""Equipo (Head of Sales): do they follow the playbook, does it work, why we lose (team_coaching)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-coaching-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-coaching-32")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import team_insights as team_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.team_insights import team_coaching as answers
from tests.reporting.fake_db import FakeDB

COMPANY = "77777777-7777-7777-7777-777777777777"
ANA = "88888888-8888-8888-8888-888888888888"
LUIS = "66666666-6666-6666-6666-666666666666"
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
STEPS = [
    {"step_id": "open", "label": "Apertura", "criterion": "Se presenta"},
    {"step_id": "pain", "label": "Dolor", "criterion": "Pregunta por el dolor"},
]


def _row(states: dict, *, meeting=False, conv=True, user=ANA):
    return {
        "memo_id": "m", "user_id": user, "observed_at": NOW.isoformat(), "motion": "discovery",
        "is_conversation": conv, "full_process": True, "meeting_agreed": meeting,
        "steps": [{"step_id": k, "label": k, "state": v, "criterion": None} for k, v in states.items()],
    }


# --- does the playbook work -------------------------------------------------------------------


def test_a_step_that_goes_with_meetings_helps_and_thin_sides_give_no_verdict():
    rows = (
        [_row({"open": "done", "pain": "done"}, meeting=True) for _ in range(4)]
        + [_row({"open": "done", "pain": "done"}) for _ in range(2)]
        + [_row({"open": "done", "pain": "missing"}) for _ in range(5)]
        + [_row({"open": "missing", "pain": "missing"}) for _ in range(5)]
    )
    effects = {e["step_id"]: e for e in answers.step_effects(rows, STEPS)}
    pain = effects["pain"]
    assert (pain["with"]["calls"], pain["with"]["goals"], pain["without"]["calls"]) == (6, 4, 10)
    assert pain["verdict"] == "helps"
    assert effects["open"]["verdict"] == "helps"  # 4 meetings in 11 done, none in 5 skipped
    assert answers.step_effects(rows[:6], STEPS)[1]["verdict"] == "few_data"  # nobody skipped pain


def test_no_verdict_without_enough_goals_and_the_meeting_step_never_judges_itself():
    rows = [_row({"open": "done"}) for _ in range(6)] + [_row({"open": "missing"}) for _ in range(6)]
    assert answers.step_effects(rows, STEPS[:1])[0]["verdict"] == "few_data"  # no meetings at all
    meeting_step = {"step_id": "cierre", "label": "Cerrar", "criterion": "Agenda", "outcome": "meeting_booked"}
    assert [e["step_id"] for e in answers.step_effects(rows, [*STEPS[:1], meeting_step])] == ["open"]


def test_a_step_that_goes_with_fewer_meetings_hurts():
    rows = (
        [_row({"open": "done"}) for _ in range(6)]
        + [_row({"open": "missing"}, meeting=True) for _ in range(3)]
        + [_row({"open": "missing"}) for _ in range(3)]
    )
    assert answers.step_effects(rows, STEPS[:1])[0]["verdict"] == "hurts"


def test_rep_matrix_is_each_rep_against_each_step():
    rows = {ANA: [_row({"open": "done", "pain": "missing"}, meeting=True)], LUIS: [_row({"open": "missing"}, user=LUIS)]}
    ana, luis = answers.rep_matrix(rows, [{"userId": ANA, "name": "Ana"}, {"userId": LUIS, "name": "Luis"}], STEPS)
    assert (ana["adherence"], ana["conversations"], ana["meetings"]) == (0.5, 1, 1)
    assert ana["steps"]["pain"] == {"done": 0, "applicable": 1, "rate": 0.0}
    assert luis["steps"]["pain"]["applicable"] == 0


# --- why we lose ------------------------------------------------------------------------------


def _signal(memo_id, *, at, resistances=(), conversation=True, outcome=None, keys=("c1",)):
    return {
        "memo_id": memo_id, "user_id": ANA, "motion": "discovery", "observed_at": at, "keys": list(keys),
        "conversation": conversation, "rep_outcome": outcome,
        "resistances": [
            {"kind": kind, "category": category, "objection_id": None, "resolution": resolution, "quote": quote}
            for kind, category, resolution, quote in resistances
        ],
    }


def test_the_cause_is_the_objection_left_open_then_an_obstacle():
    open_price = _signal("a", at=NOW, resistances=[
        ("obstacle", "bad_moment", None, "Estoy conduciendo"),
        ("objection", "timing", "resolved", "Ahora no"),
        ("objection", "price", "open", "Es caro"),
    ])
    assert answers.loss_cause(open_price, [], set())["cause"] == "price"
    obstacle = _signal("b", at=NOW, resistances=[("obstacle", "wrong_person", None, "No llevo yo eso")])
    assert answers.loss_cause(obstacle, [], set())["cause"] == "obstacle:wrong_person"


def test_a_call_with_nothing_to_say_looks_at_the_contacts_earlier_calls():
    earlier = _signal("e", at=NOW - timedelta(days=5), resistances=[("objection", "status_quo", "open", "Nos va bien así")])
    other_contact = _signal("x", at=NOW - timedelta(days=1), resistances=[("objection", "price", "open", "Caro")], keys=("c9",))
    last = _signal("l", at=NOW, outcome="not_interested")
    found = answers.loss_cause(last, [earlier, other_contact, last], set())
    assert (found["cause"], found["memo_id"], found["from_history"]) == ("status_quo", "e", True)


def test_never_talked_to_is_its_own_cause_without_any_model():
    no_answers = [_signal(f"n{i}", at=NOW - timedelta(days=i + 1), conversation=False) for i in range(6)]
    last = _signal("l", at=NOW, conversation=False, outcome="not_interested")
    assert answers.loss_cause(last, [*no_answers, last], set())["cause"] == "no_conversation"
    talked = _signal("t", at=NOW, conversation=True, outcome="disqualified")
    assert answers.loss_cause(talked, [talked], set())["cause"] == "unclear"


def test_losses_count_vocify_and_crm_and_rank_causes():
    signals = [
        _signal("a", at=NOW, outcome="not_interested", resistances=[("objection", "price", "open", "Es caro")]),
        _signal("b", at=NOW - timedelta(hours=1), outcome="disqualified", resistances=[("objection", "price", "open", "Sin presupuesto")], keys=("c2",)),
        _signal("c", at=NOW - timedelta(hours=2), conversation=False, keys=("c3",)),  # lost in HubSpot only
        _signal("d", at=NOW - timedelta(hours=3), outcome="follow_up", keys=("c4",)),  # not a loss
    ]
    body = answers.losses(signals, {"c"}, {}, {ANA: "Ana"})
    assert body["total"] == 3 and body["by_source"] == {"not_interested": 1, "disqualified": 1, "crm_lost": 1}
    assert [(c["cause"], c["count"]) for c in body["causes"]] == [("price", 2), ("no_conversation", 1)]
    assert body["causes"][0]["share"] == pytest.approx(2 / 3, abs=1e-4)
    assert body["causes"][0]["examples"][0] == {
        "memo_id": "a", "quote": "Es caro", "rep": "Ana", "observed_at": NOW.isoformat(), "from_history": False,
    }


# --- GET /team/coaching -------------------------------------------------------------------------


def _memo(memo_id, user, statuses, *, days_ago=1, meeting=False, outcome=None, objections=(), **over):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    memo = {
        "id": memo_id, "user_id": user, "company_id": COMPANY, "sales_motion_key": "discovery",
        "screening_outcome": "connected", "audio_duration": 120,
        "rep_outcome": "meeting_booked" if meeting else outcome,
        "capture_started_at": at, "created_at": at, "hubspot_contact_id": f"c-{memo_id}",
        "extraction": {"summary": "", "intelligence": {
            "playbook_observations": [
                {"step_id": sid, "label": sid, "criterion": next(s["criterion"] for s in STEPS if s["step_id"] == sid), "status": st}
                for sid, st in statuses.items()
            ],
            "objections": [
                {"kind": "objection", "category": category, "resolution": "open", "quote": quote}
                for category, quote in objections
            ],
        }},
    }
    memo.update(over)
    return memo


def _client(memos, role="owner"):
    app = FastAPI()
    app.include_router(team_api.router)
    store = FakeDB({
        "memos": memos,
        "playbooks": [{"id": "pb", "company_id": COMPANY, "sales_motion_key": "discovery", "active_version_id": "v"}],
        "playbook_versions": [{"id": "v", "playbook_id": "pb", "status": "published", "steps": STEPS, "entries": []}],
        "company_members": [
            {"id": "o", "company_id": COMPANY, "user_id": "boss", "role": "owner", "status": "active"},
            {"id": "a", "company_id": COMPANY, "user_id": ANA, "role": "member", "status": "active"},
            {"id": "l", "company_id": COMPANY, "user_id": LUIS, "role": "member", "status": "active"},
        ],
    })
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id=COMPANY, user_id="boss", role=role, status="active")
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


@pytest.fixture(autouse=True)
def _now(monkeypatch):
    monkeypatch.setattr(team_api, "_trend_now", lambda: NOW)


def test_team_coaching_answers_the_three_questions():
    memos = [
        _memo("a1", ANA, {"open": "met", "pain": "met"}, meeting=True),
        _memo("a2", ANA, {"open": "met", "pain": "missed"}, outcome="not_interested", objections=[("price", "Es caro")]),
        _memo("l1", LUIS, {"open": "missed", "pain": "missed"}),
    ]
    body = _client(memos).get("/api/v1/team/coaching?period=month").json()
    assert body["type"] == "discovery" and body["types"][0]["conversations"] == 3
    follow = body["follow"]
    assert (follow["adherence"], follow["conversations"]) == (0.5, 3)
    assert {rep["user_id"]: rep["adherence"] for rep in follow["reps"]} == {ANA: 0.75, LUIS: 0.0}
    assert [s["step_id"] for s in body["works"]["steps"]] == ["open", "pain"]
    assert body["works"]["steps"][1]["verdict"] == "few_data"  # three calls are not a verdict
    assert body["losses"]["total"] == 1 and body["losses"]["causes"][0]["cause"] == "price"


def test_team_coaching_is_for_the_head_of_sales_only():
    assert _client([], role="member").get("/api/v1/team/coaching").status_code == 403
    empty = _client([]).get("/api/v1/team/coaching").json()
    assert empty["type"] is None and empty["follow"]["reps"] == []
