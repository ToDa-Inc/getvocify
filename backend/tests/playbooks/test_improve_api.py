"""The improvement API (/api/v1/playbook-assistant/improve): the numbers, the later batch that judges finished calls, the
queue of answers that keep failing and what the Head of Sales does with them. Coverage is always there; everything that
depends on judging calls needs PLAYBOOK_SUCCESS_RATE_ENABLED as well."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.playbooks.assistant_store import get_assistant_store
from app.services.playbooks.structure import set_playbook_structure_llm
from app.services.playbooks.structured import MAX_GUIDANCE
from tests.playbooks.test_assistant_api import BASE, STEP, _MissingTables, _clean, make_client  # noqa: F401 (the autouse flag fixture)
from tests.playbooks.test_structure import FakeLLM
from tests.reporting.fake_db import FakeDB

I = f"{BASE}/improve"
PRICE = {"category": "price", "guidance": "Respuesta antigua.", "entry_id": "objection:price", "source_ref": "editor"}


@pytest.fixture
def success_on(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_SUCCESS_RATE_ENABLED", True)
    feature_flags.clear_cache()


def hours_ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def calls_db(count=3, *, answered=True):
    """`count` objections about price raised in finished calls, each with the card live help showed and the post-call reading."""
    events, memos = [], []
    for i in range(count):
        events.append({
            "id": f"e{i}", "company_id": "co-1", "kind": "suggest", "is_objection": True, "created_at": hours_ago(30 + i),
            "capture_id": f"m{i}", "latest_turn": f"Es muy caro para nosotros caso {i}", "objection_type": "price",
            "source_id": "objection:price" if answered else None, "say_this": "Pregunta cuánto pierden.", "sales_motion_key": "discovery",
        })
        memos.append({
            "id": f"m{i}", "company_id": "co-1", "transcript": "x", "extraction": {"intelligence": {"objections": [
                {"kind": "objection", "category": "price", "quote": f"Es muy caro para nosotros caso {i}", "response": "Depende.", "resolution": "open"},
            ]}},
        })
    return FakeDB({"live_assist_events": events, "memos": memos})


def seeded(client):
    client.repo.save_draft("co-1", "discovery", [STEP], [PRICE])
    return client


def guidance(client):
    version = client.repo.editor_snapshot("co-1", "discovery", include_draft=True)["version"]
    return {e.get("label") or e["category"]: e["guidance"] for e in version["entries"]}


def refreshed(client):
    set_playbook_structure_llm(FakeLLM({"used": "not_used"}))
    return client.post(f"{I}/refresh")


def queue_of(client):
    return client.get(f"{I}/queue").json()


def first_moment(client):
    return queue_of(client)["groups"][0]["moments"][0]["id"]


# --- who may, and what each flag opens --------------------------------------------------------------------


def test_it_is_only_for_an_owner_or_admin():
    assert make_client(role="member").get(f"{I}/stats").status_code == 403


def test_a_company_without_events_gets_empty_counts_and_no_success_rate():
    body = make_client().get(f"{I}/stats")
    assert body.status_code == 200
    assert body.json() == {"coverage": {"detected": 0, "answered": 0, "rate": None}}


def test_coverage_is_there_without_the_success_flag_and_works_before_the_tables_exist():
    client = make_client(db=calls_db(4), store="sql")  # the plain database answers, the assistant's tables do not exist
    body = client.get(f"{I}/stats").json()
    assert body == {"coverage": {"detected": 4, "answered": 4, "rate": 1.0}}


def test_the_numbers_of_judged_calls_need_the_success_flag(success_on, monkeypatch):
    client = make_client()
    body = client.get(f"{I}/stats").json()
    assert body["success"]["rate"] is None and body["success"]["sample"] == 0 and body["queue"] == {"answers": 0, "cases": 0}
    monkeypatch.setattr(settings, "PLAYBOOK_SUCCESS_RATE_ENABLED", False)
    feature_flags.clear_cache()
    assert "success" not in client.get(f"{I}/stats").json() and "queue" not in client.get(f"{I}/stats").json()


def test_judging_and_the_queue_do_not_exist_without_the_success_flag():
    client = seeded(make_client(db=calls_db()))
    for call in (client.post(f"{I}/refresh"), client.get(f"{I}/queue"), client.post(f"{I}/publish")):
        assert call.status_code == 404


def test_with_the_flag_but_without_the_tables_the_answer_is_a_calm_503(success_on):
    response = make_client(db=_MissingTables(), store="sql").get(f"{I}/stats")
    assert response.status_code == 503 and response.json()["detail"] == {"code": "not_activated"}


# --- judging later, in batches --------------------------------------------------------------------------------


def test_refreshing_judges_the_finished_calls_queues_the_failing_answer_and_never_repeats(success_on):
    client = seeded(make_client(db=calls_db(3)))
    assert refreshed(client).json() == {"judged": 3, "queued": 3}
    assert refreshed(client).json() == {"judged": 0, "queued": 0}
    stats = client.get(f"{I}/stats").json()
    assert stats["coverage"] == {"detected": 3, "answered": 3, "rate": 1.0}
    assert stats["success"]["sample"] == 3 and stats["success"]["used"] == 0 and stats["success"]["rate"] is None
    assert stats["queue"] == {"answers": 1, "cases": 3}


def test_two_failing_cases_are_not_yet_a_queue_entry(success_on):
    client = seeded(make_client(db=calls_db(2)))
    assert refreshed(client).json() == {"judged": 2, "queued": 0}
    assert queue_of(client) == {"groups": [], "publish": []}


def test_a_card_whose_call_has_not_been_read_yet_is_left_for_later(success_on):
    db = calls_db(3)
    db.tables["memos"][0]["extraction"] = None
    assert refreshed(seeded(make_client(db=db))).json()["judged"] == 2


# --- the queue ------------------------------------------------------------------------------------------------


def test_the_queue_shows_each_failing_answer_with_what_it_says_and_its_cases(success_on):
    client = seeded(make_client(db=calls_db(3)))
    refreshed(client)
    [group] = queue_of(client)["groups"]
    assert group["answer_key"] == "objection:price" and group["sales_motion_key"] == "discovery"
    assert group["answer"] == {"category": "price", "label": None, "guidance": "Respuesta antigua."}
    assert group["failing"] == 3 and group["total"] == 3 and group["marks"] == ["unused"] * 3
    assert group["stats"]["rate"] is None
    [first, *_] = group["moments"]
    assert set(first) == {"id", "event_id", "client_text", "suggestion_text", "rep_text", "mark"}
    assert first["mark"] == "unused" and first["suggestion_text"] == "Pregunta cuánto pierden."


def queue_ready(success_on):
    client = seeded(make_client(db=calls_db(3)))
    refreshed(client)
    return client


def act(client, moment_id, action, **body):
    return client.post(f"{I}/queue/{moment_id}/action", json={"action": action, **body})


def test_correcting_changes_the_answer_in_the_draft_and_closes_that_case(success_on):
    client = queue_ready(success_on)
    moment = first_moment(client)
    done = act(client, moment, "correct", text="Lo comparamos con lo que pierden al mes.")
    assert done.status_code == 200
    assert guidance(client)["price"] == "Lo comparamos con lo que pierden al mes."
    stored = get_assistant_store(None).get_moment("co-1", moment)
    assert stored["status"] == "corrected" and stored["outcome"]["motion"] == "discovery"
    after = queue_of(client)
    assert len(after["groups"][0]["moments"]) == 2 and after["publish"] == ["discovery"]


def test_keeping_the_answer_closes_the_case_and_changes_nothing(success_on):
    client = queue_ready(success_on)
    moment = first_moment(client)
    assert act(client, moment, "keep").status_code == 200
    assert guidance(client)["price"] == "Respuesta antigua."
    assert get_assistant_store(None).get_moment("co-1", moment)["status"] == "kept"
    assert queue_of(client)["publish"] == []


def test_a_branch_is_added_to_the_answer_for_that_situation(success_on):
    client = queue_ready(success_on)
    act(client, first_moment(client), "branch", text="Enseña el ahorro de horas.", when="lo comparan con una herramienta gratuita")
    assert guidance(client)["price"] == "Respuesta antigua. Si lo comparan con una herramienta gratuita: Enseña el ahorro de horas."


def test_a_new_objection_keeps_the_answer_as_one_of_its_own(success_on):
    client = queue_ready(success_on)
    done = act(client, first_moment(client), "new_objection", text="Cuenta el caso de la tienda de Valencia.", when="Es muy caro para nosotros")
    assert done.status_code == 200
    assert guidance(client)["price"] == "Respuesta antigua." and "Cuenta el caso de la tienda de Valencia." in guidance(client).values()


def test_an_answer_that_does_not_fit_or_is_missing_changes_nothing(success_on):
    client = queue_ready(success_on)
    moment = first_moment(client)
    assert act(client, moment, "correct").status_code == 422
    assert act(client, moment, "correct", text="x" * (MAX_GUIDANCE + 1)).json()["detail"] == {"code": "guidance_too_long"}
    assert guidance(client)["price"] == "Respuesta antigua."
    assert get_assistant_store(None).get_moment("co-1", moment)["status"] == "open"


def test_unknown_actions_cases_and_cases_already_dealt_with_are_refused(success_on):
    client = queue_ready(success_on)
    moment = first_moment(client)
    assert act(client, moment, "delete").status_code == 422
    assert act(client, "nope", "keep").status_code == 404
    act(client, moment, "keep")
    assert act(client, moment, "keep").status_code == 409


def test_publishing_sends_the_changed_call_types_live_once(success_on):
    client = queue_ready(success_on)
    act(client, first_moment(client), "correct", text="Lo comparamos con lo que pierden al mes.")
    assert client.post(f"{I}/publish").json() == {"published": ["discovery"], "failed": []}
    assert client.post(f"{I}/publish").json() == {"published": [], "failed": []}
    assert queue_of(client)["publish"] == []


# --- the Head of Sales corrects a verdict -----------------------------------------------------------------


def used_outcomes(client, count=3):
    store = get_assistant_store(None)
    for i in range(count):
        store.upsert_outcome("co-1", {
            "event_id": f"x{i}", "observed_at": hours_ago(30), "sales_motion_key": "discovery", "source_id": "objection:price",
            "used": "used", "resolved": "not_resolved", "resolved_by": "extraction", "client_text": "Es caro", "suggestion_text": "Pregunta.",
        })


def verdict(client, event_id, resolved):
    return client.post(f"{I}/outcomes/{event_id}/verdict", json={"resolved": resolved})


def test_correcting_a_verdict_changes_the_success_rate_and_says_who_decided(success_on):
    client = seeded(make_client())
    used_outcomes(client)
    assert client.get(f"{I}/stats").json()["success"]["rate"] == 0.0
    assert verdict(client, "x0", "resolved").status_code == 200
    stored = get_assistant_store(None).get_outcome("co-1", "x0")
    assert stored["resolved"] == "resolved" and stored["resolved_by"] == "admin"
    assert client.get(f"{I}/stats").json()["success"]["rate"] == pytest.approx(1 / 3)


def test_a_case_the_boss_says_did_settle_it_leaves_the_queue(success_on):
    client = seeded(make_client())
    used_outcomes(client)
    store = get_assistant_store(None)
    for i in range(3):
        store.add_moment("co-1", {
            "source": "real", "sales_motion_key": "discovery", "entry_id": "objection:price", "client_text": "Es caro",
            "outcome": {"event_id": f"x{i}", "mark": "failed"},
        })
    assert len(queue_of(client)["groups"][0]["moments"]) == 3
    verdict(client, "x1", "resolved")
    assert [m["event_id"] for m in queue_of(client)["groups"][0]["moments"]] == ["x0", "x2"]


def test_a_verdict_for_an_unknown_card_or_a_made_up_value_is_refused(success_on):
    client = seeded(make_client())
    assert verdict(client, "ghost", "resolved").status_code == 404
    used_outcomes(client, 1)
    assert verdict(client, "x0", "maybe").status_code == 422
