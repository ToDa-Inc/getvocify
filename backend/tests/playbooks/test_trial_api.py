"""The trial's API (/api/v1/playbook-assistant/trial): a session of 10 to 12 cases, each run with the draft, decided
with one of the verdicts, and activated at the end. Same gate as the rest of the assistant."""

from __future__ import annotations

import pytest

from app.api import playbook_assistant
from app.services.playbooks.assistant_store import SqlAssistantStore
from app.services.playbooks.structure import set_playbook_structure_llm
from app.services.playbooks.structured import MAX_GUIDANCE
from tests.playbooks.test_assistant_api import BASE, STEP, _MissingTables, _clean, make_client  # noqa: F401 (the autouse flag fixture)

T = f"{BASE}/trial"


def run_of(say_this, *, detected="price", entry_id=None, label=None, source_id="objection:price"):
    return {
        "detected": detected, "entry_id": entry_id, "label": label, "grounded": True,
        "card": {"say_this": say_this, "source_id": source_id, "objection_type": detected} if say_this else None,
    }


class Runner:
    """Stands in for run_case: answers per call, in order (the last repeats), and remembers the snapshots it was given."""

    def __init__(self, *runs):
        self.runs, self.snapshots = list(runs), []

    async def __call__(self, case, *, snapshot, knowledge, product_context, lang):
        self.snapshots.append(snapshot)
        return self.runs.pop(0) if len(self.runs) > 1 else self.runs[0]


@pytest.fixture
def runner(monkeypatch):
    def install(*runs, similar="Ya tenemos una herramienta gratuita que cubre eso."):
        fake = Runner(*runs)
        monkeypatch.setattr(playbook_assistant, "run_case", fake)

        async def phrase(case, lang, *, llm=None):
            return similar

        monkeypatch.setattr(playbook_assistant, "similar_phrase", phrase)
        return fake

    return install


def start(client, **body):
    return client.post(T, json={"motion_key": "discovery", "lang": "es", **body})


def first_case(trial):
    return trial["cases"][0]["id"]


def guidance(client, key="discovery"):
    version = client.repo.editor_snapshot("co-1", key, include_draft=True)["version"]
    return {e["category"]: e["guidance"] for e in version["entries"]}


def test_it_is_only_for_an_owner_or_admin_and_dark_without_the_tables():
    assert start(make_client(role="member")).status_code == 403
    missing = make_client(db=_MissingTables(), store="sql")
    response = start(missing)
    assert response.status_code == 503 and response.json()["detail"] == {"code": "not_activated"}


def test_a_trial_has_ten_to_twelve_cases_and_is_resumed_not_restarted():
    client = make_client()
    trial = start(client).json()
    assert 10 <= trial["total"] <= 12 and trial["decided"] == 0 and trial["status"] == "open"
    assert trial["current_id"] == first_case(trial) and trial["result"]["total"] == 0
    assert all(set(c) == {"id", "source", "client_text", "verdict"} for c in trial["cases"])
    again = start(client).json()
    assert again["id"] == trial["id"] and [c["id"] for c in again["cases"]] == [c["id"] for c in trial["cases"]]
    assert client.get(f"{T}/{trial['id']}").json()["id"] == trial["id"]


def test_running_a_case_shows_the_card_made_from_the_draft_and_keeps_it(runner):
    fake = runner(run_of("Pregunta cuánto tiempo pierden."))
    client = make_client()
    trial = start(client).json()
    case = first_case(trial)
    ran = client.post(f"{T}/{trial['id']}/cases/{case}/run").json()
    assert ran["run"]["card"]["say_this"] == "Pregunta cuánto tiempo pierden." and ran["case"]["id"] == case
    assert [s["sales_motion_key"] for s in fake.snapshots] == ["discovery"] and fake.snapshots[0]["version_id"]
    assert client.get(f"{T}/{trial['id']}").json()["runs"][case]["detected"] == "price"


def test_approving_changes_nothing_and_counts():
    client = make_client()
    trial = start(client).json()
    case = first_case(trial)
    done = client.post(f"{T}/{trial['id']}/cases/{case}/verdict", json={"verdict": "approve"})
    assert done.status_code == 200
    body = done.json()
    assert body["result"]["approved"] == 1 and body["trial"]["decided"] == 1 and body["trial"]["current_id"] != case
    assert guidance(client) == {}


def test_a_correction_changes_the_draft_runs_the_case_again_and_checks_a_similar_phrase(runner):
    runner(run_of("Respuesta antigua."), run_of("Lo comparamos con lo que pierden al mes."), run_of("Pregunta cuánto tiempo pierden con esa herramienta."))
    client = make_client()
    client.repo.save_draft("co-1", "discovery", [STEP], [{"category": "price", "guidance": "Respuesta antigua.", "entry_id": "objection:price", "source_ref": "editor"}])
    trial = start(client).json()
    case = first_case(trial)
    client.post(f"{T}/{trial['id']}/cases/{case}/run")
    done = client.post(f"{T}/{trial['id']}/cases/{case}/verdict", json={"verdict": "corrected", "text": "Lo comparamos con lo que pierden al mes."}).json()
    assert guidance(client)["price"] == "Lo comparamos con lo que pierden al mes."
    assert done["run"]["card"]["say_this"] == "Lo comparamos con lo que pierden al mes."
    assert done["similar"]["text"] == "Ya tenemos una herramienta gratuita que cubre eso."
    assert done["similar"]["run"]["card"]["say_this"] == "Pregunta cuánto tiempo pierden con esa herramienta."
    assert done["result"]["approved"] == 0 and done["result"]["total"] == 1


def test_a_branch_for_the_similar_phrase_is_added_to_the_answer(runner):
    runner(run_of("Respuesta antigua."))
    client = make_client()
    client.repo.save_draft("co-1", "discovery", [STEP], [{"category": "price", "guidance": "Respuesta antigua.", "entry_id": "objection:price", "source_ref": "editor"}])
    trial = start(client).json()
    case = first_case(trial)
    client.post(f"{T}/{trial['id']}/cases/{case}/run")
    body = {"verdict": "branch", "text": "Enseña el ahorro de horas.", "when": "lo comparan con una herramienta gratuita"}
    done = client.post(f"{T}/{trial['id']}/cases/{case}/verdict", json=body).json()
    assert guidance(client)["price"] == "Respuesta antigua. Si lo comparan con una herramienta gratuita: Enseña el ahorro de horas."
    assert done["similar"] is None


def test_an_answer_that_does_not_fit_is_a_422_and_neither_the_draft_nor_the_count_move(runner):
    runner(run_of("Respuesta antigua."))
    client = make_client()
    client.repo.save_draft("co-1", "discovery", [STEP], [{"category": "price", "guidance": "Respuesta antigua.", "entry_id": "objection:price", "source_ref": "editor"}])
    trial = start(client).json()
    case = first_case(trial)
    client.post(f"{T}/{trial['id']}/cases/{case}/run")
    refused = client.post(f"{T}/{trial['id']}/cases/{case}/verdict", json={"verdict": "corrected", "text": "x" * (MAX_GUIDANCE + 1)})
    assert refused.status_code == 422 and refused.json()["detail"] == {"code": "guidance_too_long"}
    assert guidance(client)["price"] == "Respuesta antigua."
    assert client.get(f"{T}/{trial['id']}").json()["decided"] == 0


def test_unknown_things_have_clear_codes():
    client = make_client()
    trial = start(client).json()
    assert client.post(f"{T}/nope/cases/x/run").json()["detail"] == {"code": "session_not_found"}
    assert client.post(f"{T}/{trial['id']}/cases/nope/run").json()["detail"] == {"code": "case_not_found"}
    bad = client.post(f"{T}/{trial['id']}/cases/{first_case(trial)}/verdict", json={"verdict": "maybe"})
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "bad_verdict"}


def test_the_result_has_no_percentage_until_three_cases_are_decided():
    client = make_client()
    trial = start(client).json()
    for index, case in enumerate(trial["cases"][:4]):
        client.post(f"{T}/{trial['id']}/cases/{case['id']}/verdict", json={"verdict": "approve" if index < 3 else "unknown"})
        result = client.get(f"{T}/{trial['id']}/result").json()
        assert (result["percent"] is None) == (index < 2)
    assert result == {"approved": 3, "total": 4, "percent": 75, "weak_topics": [], "warn": True, "can_activate": True}


def test_activating_publishes_the_drafts_the_trial_touched_and_closes_it(runner):
    runner(run_of("Respuesta antigua."))
    client = make_client()
    client.repo.save_draft("co-1", "discovery", [STEP], [{"category": "price", "guidance": "Respuesta antigua.", "entry_id": "objection:price", "source_ref": "editor"}])
    trial = start(client).json()
    case = first_case(trial)
    client.post(f"{T}/{trial['id']}/cases/{case}/run")
    client.post(f"{T}/{trial['id']}/cases/{case}/verdict", json={"verdict": "corrected", "text": "Lo comparamos con lo que pierden."})
    done = client.post(f"{T}/{trial['id']}/activate").json()
    assert done["published"] == ["discovery"] and done["failed"] == []
    assert client.repo.list_types("co-1")["discovery"]["status"] == "published"
    assert client.get(f"{T}/{trial['id']}").json()["status"] == "done"
    assert client.get(f"{BASE}/trial/{trial['id']}").status_code == 200
