"""«Sugerencias»: what the team's calls taught, grouped and ranked for the head of sales, taken into the playbook with
their words or set aside with a reason Vocify learns from."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import playbook_suggestions as api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.intelligence.findings import build_messages
from app.services.playbooks import suggestions as engine
from app.services.playbooks.conduct import InMemoryConductStore, set_conduct_store
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository
from tests.reporting.fake_db import FakeDB

STEP = {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y pide un minuto."}
NAMES = {"u-ana": "Ana", "u-dani": "Daniel"}


def row(memo, user, at, findings, motion="discovery"):
    return {"memo_id": memo, "user_id": user, "observed_at": at, "motion": motion, "is_conversation": True, "findings": findings}


PROVIDER = {
    "topic": "Ya tienen otro proveedor", "quote": "Eh, no, ahora ya cambiamos para otro.",
    "said": "Ya cambiamos a otro proveedor hace poco.", "reply": "Ah, ya cambiasteis entonces.", "after": "ended",
    "better": "Entiendo. ¿Qué os gustaría que hiciera y no hace?",
}
ROWS = [
    row("m1", "u-ana", "2026-11-13T10:20:00+00:00", {
        "new_objections": [PROVIDER],
        "questions": [
            {"topic": "Gestión de CAE", "quote": "¿y los CAE?", "said": "¿Gestionáis los CAE?", "answered": "no", "better": None, "covered_by": None},
            {"topic": "Precio por vehículo", "quote": "¿cuánto?", "answered": "yes", "answer": "15 €", "covered_by": None},
        ],
    }),
    row("m2", "u-dani", "2026-11-12T09:00:00+00:00", {
        "new_objections": [{
            **PROVIDER, "quote": "Ya trabajamos con otro desde verano.", "said": "Ya trabajamos con otro proveedor desde verano.",
            "reply": "¿Y qué es lo que mejor os funciona?", "reply_said": "¿Qué es lo que mejor os funciona de él?", "after": "advanced",
        }],
        "worked": [{
            "topic": "Prueba de un mes sin permanencia", "quote": "Lo que podemos hacer es una prueba de un mes",
            "said": "Podemos hacer una prueba de un mes sin permanencia.", "after_quote": "Vale, pásamelo",
            "why": "Quitó el miedo a atarse.", "use_when": "Cuando no quieran atarse sin haberlo probado",
        }],
        "signals": [{"topic": "Renovación en marzo", "quote": "nos acaba en marzo", "line": "¿Qué tendría que pasar antes de marzo?", "why": "Una fecha."}],
    }),
]


def test_the_same_thing_in_the_same_call_type_is_one_suggestion_ranked_by_what_it_cost():
    found = engine.build_suggestions(ROWS, NAMES, {"discovery": "Llamada en frío"})
    assert [s["title"] for s in found][:1] == ["Ya tienen otro proveedor"]
    provider = found[0]
    assert (provider["kind"], provider["count"], provider["lost"], provider["reps"]) == ("objection", 2, 1, ["Ana", "Daniel"])
    assert provider["motion_label"] == "Llamada en frío"
    # A colleague's words after which the call went on beat the line the reading wrote.
    assert (provider["draft"], provider["draft_from"]) == ("¿Qué es lo que mejor os funciona de él?", "colleague")
    # The exchange as it happened: the client first, then the rep; what they meant next to their words.
    assert provider["examples"][0]["turns"][0] == {"who": "client", "quote": "Eh, no, ahora ya cambiamos para otro.", "said": "Ya cambiamos a otro proveedor hace poco."}
    titles = {s["title"]: s for s in found}
    # A question answered in the call is not a gap; one nobody answered is, with no draft when nothing supports one.
    assert "Precio por vehículo" not in titles and titles["Gestión de CAE"]["draft"] is None
    worked = titles["Prueba de un mes sin permanencia"]
    assert worked["examples"][0]["turns"][0]["who"] == "rep" and worked["use_when"].startswith("Cuando no quieran")


def test_a_decision_hides_it_and_an_isolated_case_comes_back_when_it_keeps_happening():
    key = engine.suggestion_key("objection", "discovery", "Ya tienen otro proveedor")
    isolated = {key: {"decision": "dismissed", "reason": "isolated", "count_at": 1}}
    assert key not in {s["key"] for s in engine.build_suggestions(ROWS[:1], NAMES, {}, isolated)}
    # Two more times than when it was set aside: it is back.
    more = ROWS + [row("m3", "u-ana", "2026-11-11T09:00:00+00:00", {"new_objections": [PROVIDER]})]
    assert key in {s["key"] for s in engine.build_suggestions(more, NAMES, {}, isolated)}
    for decision in ({"decision": "accepted"}, {"decision": "dismissed", "reason": "not_applicable", "count_at": 1}):
        assert key not in {s["key"] for s in engine.build_suggestions(more, NAMES, {}, {key: decision})}


def test_an_answer_is_named_by_the_title_and_said_the_clients_way():
    suggestion = engine.build_suggestions(ROWS, NAMES, {})[0]
    content = engine.add_answer({"steps": [STEP], "objections": []}, suggestion, "  Entiendo. ¿Qué os funciona?  ")
    added = content["objections"][-1]
    assert (added["label"], added["trigger"], added["guidance"]) == (
        "Ya tienen otro proveedor", "Ya cambiamos a otro proveedor hace poco.", "Entiendo. ¿Qué os funciona?")
    with pytest.raises(ValueError, match="already_in_playbook"):
        engine.add_answer(content, suggestion, "Otra vez")
    with pytest.raises(ValueError, match="text_required"):
        engine.add_answer({"objections": []}, suggestion, "   ")


def test_what_worked_becomes_a_situation_of_how_we_work():
    worked = next(s for s in engine.build_suggestions(ROWS, NAMES, {}) if s["kind"] == "worked")
    conduct = engine.add_situation(None, worked, "Ofrece una prueba de un mes sin permanencia con un vehículo.")
    (situation,) = conduct["situations"]
    assert situation["name"] == "Prueba de un mes sin permanencia"
    assert situation["when"] == "Cuando no quieran atarse sin haberlo probado"
    assert situation["example"] == "Lo que podemos hacer es una prueba de un mes"


def test_the_reasons_teach_the_reading_of_the_next_calls():
    criteria = engine.reading_criteria({
        "a": {"decision": "dismissed", "reason": "not_applicable", "topic": "Huelga de transporte"},
        "b": {"decision": "dismissed", "reason": "covered", "topic": "Ya tienen otro proveedor", "covered_by": "objection:custom:competencia"},
        "c": {"decision": "dismissed", "reason": "isolated", "topic": "Caso raro"},
        "d": {"decision": "accepted", "topic": "Gestión de CAE"},
    })
    assert criteria == {"ignored": ["Huelga de transporte"], "covered": [{"topic": "Ya tienen otro proveedor", "answer": "objection:custom:competencia"}]}
    messages = build_messages("You: hola", call={}, answers=[{"id": "competencia", "label": "Competencia", "answer": "x"}], criteria=criteria)
    payload = messages[-1]["content"]
    assert '"also_said": ["Ya tienen otro proveedor"]' in payload and '"not_relevant": ["Huelga de transporte"]' in payload


# --- the API ----------------------------------------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co-1", user_id="u-1", role="owner", status="active")
    app.dependency_overrides[get_supabase] = lambda: FakeDB()
    repo = InMemoryPlaybookRepository()
    repo.save_draft("co-1", "discovery", [STEP], [])
    repo.publish("co-1", "discovery")
    set_playbook_repository(repo)
    conduct = InMemoryConductStore()
    set_conduct_store(conduct)
    store = engine.InMemoryDecisionStore()
    engine.set_decision_store(store)
    monkeypatch.setattr(api, "_load", lambda supabase, membership: (
        engine.build_suggestions(ROWS, NAMES, {}, store.all("co-1")), store.all("co-1")))
    monkeypatch.setattr(api, "_answers", lambda *a: {"discovery": []})
    monkeypatch.setattr(api, "_playbooks_changed", lambda company_id: None)
    test_client = TestClient(app)
    test_client.repo, test_client.conduct, test_client.store = repo, conduct, store
    yield test_client
    set_playbook_repository(None)
    set_conduct_store(None)
    engine.set_decision_store(None)


def test_only_the_head_of_sales_sees_them(client):
    client.app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co-1", user_id="u-2", role="member", status="active")
    assert client.get("/api/v1/playbook-assistant/suggestions").status_code == 403


def test_accepting_an_objection_puts_it_live_with_their_words(client):
    first = client.get("/api/v1/playbook-assistant/suggestions").json()["suggestions"][0]
    response = client.post(f"/api/v1/playbook-assistant/suggestions/{first['key']}/accept", json={"text": "Entiendo. ¿Qué os funciona mejor?"})
    body = response.json()
    assert response.status_code == 200 and body["published"] is True and body["learned"] == 1
    assert first["key"] not in {s["key"] for s in body["suggestions"]}
    live = client.repo.editor_snapshot("co-1", "discovery", include_draft=False)["version"]["entries"]
    assert any(e.get("label") == "Ya tienen otro proveedor" and e["guidance"] == "Entiendo. ¿Qué os funciona mejor?" for e in live)


def test_what_worked_goes_to_how_we_work(client):
    worked = next(s for s in client.get("/api/v1/playbook-assistant/suggestions").json()["suggestions"] if s["kind"] == "worked")
    response = client.post(f"/api/v1/playbook-assistant/suggestions/{worked['key']}/accept", json={"text": "Ofrece la prueba de un mes."})
    assert response.status_code == 200
    assert client.conduct.get("co-1", "discovery")["situations"][0]["do"] == "Ofrece la prueba de un mes."


def test_a_reason_is_required_and_covered_needs_the_answer_and_undo_brings_it_back(client):
    first = client.get("/api/v1/playbook-assistant/suggestions").json()["suggestions"][0]
    url = f"/api/v1/playbook-assistant/suggestions/{first['key']}"
    assert client.post(f"{url}/dismiss", json={}).status_code == 422
    assert client.post(f"{url}/dismiss", json={"reason": "covered"}).json()["detail"] == {"code": "covered_by_required"}
    dismissed = client.post(f"{url}/dismiss", json={"reason": "not_applicable"}).json()
    assert first["key"] not in {s["key"] for s in dismissed["suggestions"]}
    assert client.store.all("co-1")[first["key"]]["reason"] == "not_applicable"
    restored = client.post(f"{url}/undo").json()
    assert first["key"] in {s["key"] for s in restored["suggestions"]}


def test_an_answer_that_does_not_fit_says_why_and_decides_nothing(client):
    client.repo.save_draft("co-1", "discovery", [STEP], [
        {"category": "custom", "id": "ya_tienen_otro_proveedor", "label": "Ya tienen otro proveedor", "guidance": "Ya escrita."}])
    client.repo.publish("co-1", "discovery")
    first = client.get("/api/v1/playbook-assistant/suggestions").json()["suggestions"][0]
    response = client.post(f"/api/v1/playbook-assistant/suggestions/{first['key']}/accept", json={"text": "Nueva."})
    assert response.status_code == 422 and response.json()["detail"] == {"code": "already_in_playbook"}
    assert client.store.all("co-1") == {}


def test_an_opening_in_one_call_is_that_deals_coaching_and_a_reply_is_not_listed_twice():
    one = engine.build_suggestions(ROWS, NAMES, {})
    assert "Renovación en marzo" not in {s["title"] for s in one}
    again = ROWS + [row("m4", "u-ana", "2026-11-10T09:00:00+00:00", {"signals": [{"topic": "Renovación en marzo", "quote": "en marzo renovamos", "line": "¿Y antes?"}]})]
    assert "Renovación en marzo" in {s["title"] for s in engine.build_suggestions(again, NAMES, {})}
    reply = row("m5", "u-ana", "2026-11-09T09:00:00+00:00", {
        "new_objections": [{"topic": "Compromiso de 12 meses", "quote": "no me ato 12 meses", "reply": "Te pongo un mes de prueba sin coste", "after": "advanced"}],
        "worked": [{"topic": "Prueba de un mes", "quote": "Te pongo un mes de prueba sin coste", "after_quote": "Vale", "why": "x"}],
    })
    titles = {s["title"]: s for s in engine.build_suggestions([reply], NAMES, {})}
    assert "Prueba de un mes" not in titles and titles["Compromiso de 12 meses"]["draft"] == "Te pongo un mes de prueba sin coste"



def test_a_member_without_a_name_reads_as_a_name_not_an_email():
    assert engine.display_name("daniel.clavero@movertis.com") == "Daniel Clavero"
    assert engine.display_name("Naiara Segura") == "Naiara Segura"


class _Draft:
    def __init__(self, answer):
        self.answer = answer

    async def chat_json(self, messages, **_):
        return self.answer


def _draft(answer, material):
    import asyncio

    question = next(s for s in engine.build_suggestions(ROWS, NAMES, {}) if s["kind"] == "question")
    return asyncio.run(engine.write_draft(question, material=material, answers=[], company_name="Movertis", llm=_Draft(answer)))


def test_vocify_completes_an_answer_only_from_the_companys_own_words():
    material = {"value_short": "Gestionamos los CAE de toda la flota desde la plataforma, con certificación MITECO."}
    grounded = {"text": "Sí, los CAE los gestionamos desde la plataforma, con certificación.", "facts": ["Gestionamos los CAE de toda la flota"]}
    assert _draft(grounded, material).startswith("Sí, los CAE")
    # A fact that is not in the material, no fact at all, or nothing to say: nothing is shown.
    assert _draft({"text": "Cuesta 9 € al mes.", "facts": ["9 € al mes"]}, material) is None
    assert _draft({"text": "Depende, lo miro.", "facts": []}, material) is None
    assert _draft({"text": None, "facts": []}, material) is None


def test_the_draft_endpoint_writes_nothing_and_answers_null_when_it_cannot(client, monkeypatch):
    first_question = next(s for s in client.get("/api/v1/playbook-assistant/suggestions").json()["suggestions"] if s["kind"] == "question")

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(engine, "write_draft", nothing)
    monkeypatch.setattr("app.services.copilot.load_grounding.load_company_knowledge", lambda *a, **k: {})
    response = client.post(f"/api/v1/playbook-assistant/suggestions/{first_question['key']}/draft")
    assert response.status_code == 200 and response.json() == {"text": None}
    assert client.store.all("co-1") == {}


def test_the_call_line_is_plain_text_never_markdown():
    assert api._call_line({"outcome": "Rechaza evaluar Vocify: plan ya definido.", "summary": "## Perfil"}) == "Rechaza evaluar Vocify: plan ya definido."
    assert api._call_line({"summary": "## Perfil del contacto\n**Resultado:** No interesado.\n- más"}) == "Resultado: No interesado."
    assert api._call_line({}) is None


def test_the_conversation_around_a_moment_is_the_turns_before_and_after_its_own():
    turns = [{"who": w, "text": t} for w, t in [
        ("rep", "Hola, soy Ana."), ("client", "Dime."), ("rep", "Te llamo por la flota."),
        ("client", "Eh, no, ahora ya cambiamos para otro."), ("rep", "Ah, ya cambiasteis."), ("client", "Sí."), ("rep", "Vale, gracias."),
    ]]
    window = engine.moment_window(turns, ["ahora ya cambiamos para otro", "Ah, ya cambiasteis"])
    assert [t["text"] for t in window] == ["Dime.", "Te llamo por la flota.", "Eh, no, ahora ya cambiamos para otro.", "Ah, ya cambiasteis.", "Sí.", "Vale, gracias."]
    assert [t["moment"] for t in window] == [False, False, True, True, False, False]
    assert engine.moment_window(turns, ["nadie dijo esto"]) == []


def test_another_version_is_asked_with_the_one_on_screen_and_what_the_rep_said():
    import asyncio

    seen = {}

    class _Seen:
        async def chat_json(self, messages, **_):
            seen["payload"] = messages[-1]["content"]
            return {"text": None, "facts": []}

    question = next(s for s in engine.build_suggestions(ROWS, NAMES, {}) if s["kind"] == "objection")
    asyncio.run(engine.write_draft(question, material={}, answers=[], company_name="X", llm=_Seen(), avoid="La de antes."))
    assert '"write_a_different_one_than": "La de antes."' in seen["payload"] and "what_the_rep_said" in seen["payload"]
