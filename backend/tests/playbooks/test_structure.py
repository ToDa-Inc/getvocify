"""Structure with AI (playbooks v2, T1): the model's output always saves, a failing model
never blocks, and the endpoint reads PDF/audio the way imports do."""

import asyncio
import base64
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbook_intake import router as playbook_intake_router
from app.api.playbooks import router as playbooks_router
from app.services.playbooks.api_support import set_playbook_transcriber
from app.services.playbooks.structure import set_playbook_structure_llm
from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks import structure as structure_module
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository
from app.services.playbooks.structure import detect_language, structure_source
from app.services.playbooks.structured import (
    MAX_CRITERION,
    MAX_GUIDANCE,
    MAX_LABEL,
    OBJECTION_CATEGORIES,
    normalize_objections,
    normalize_steps,
    parse_playbook_text,
)
from app.services.text_guard import generic_criterion
from tests.playbooks.test_imports import _pdf_bytes

SCRIPT = (
    "Primero me presento y pregunto si tiene un minuto. Luego digo por qué llamo: vi que abrieron "
    "oficina en Valencia. Después le pregunto cómo llevan hoy el seguimiento de leads. "
    "Si dice que no tiene tiempo: 'Lo entiendo, ¿te llamo mañana a las 10 y son cinco minutos?'. "
    "Al final propongo una demo con día y hora."
)

GOOD = {
    "reason": None,
    "steps": [
        {"label": "Apertura con permiso", "criterion": "Se presenta y pregunta si tiene un minuto.", "example": None},
        {"label": "Motivo de la llamada", "criterion": "Conecta la llamada con la nueva oficina en Valencia."},
        {"label": "Seguimiento de leads", "criterion": "Pregunta cómo llevan hoy el seguimiento y el prospecto lo describe."},
        {"label": "Demo con día y hora", "criterion": "Propone una demo con día y hora y el prospecto acepta."},
    ],
    "objections": [{"category": "timing", "guidance": "Lo entiendo. ¿Te llamo mañana a las 10 y son cinco minutos?"}],
}


class FakeLLM:
    """chat_json stand-in: answers in order (the last one repeats); an Exception is raised."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(out, BaseException):
            raise out
        return out


def run(source, llm, key="discovery", lang="es"):
    return asyncio.run(structure_source(source, key, lang, llm=llm))


def assert_saves(result):
    """Whatever comes back must pass the same validation the editor's save uses."""
    if result["steps"]:
        normalize_steps(result["steps"])
    normalize_objections(result["objections"])
    assert len(result["steps"]) <= 7 or result["fallback"]
    for entry in result["objections"]:
        assert entry["category"] in OBJECTION_CATEGORIES


# --- the model path ---


def test_a_good_answer_passes_normalize_and_keeps_the_managers_words():
    llm = FakeLLM(GOOD)
    result = run(SCRIPT, llm)
    assert result["fallback"] is False
    assert result["reason"] is None
    assert [s["label"] for s in result["steps"]][0] == "Apertura con permiso"
    assert result["objections"] == [
        {"category": "timing", "guidance": "Lo entiendo. ¿Te llamo mañana a las 10 y son cinco minutos?"}
    ]
    assert_saves(result)
    assert len(llm.calls) == 1


def test_one_call_with_a_short_timeout_and_no_client_retries():
    llm = FakeLLM(GOOD)
    run(SCRIPT, llm, key="closing", lang="es")
    call = llm.calls[0]
    assert call["timeout"] == 25.0
    assert call["max_retries"] == 0
    system, user = call["messages"]
    assert system["role"] == "system" and "no_process" in system["content"]
    assert "closing" in user["content"] and "Demo y cierre" in user["content"]
    assert "proposal" in user["content"].lower() or "Siguiente paso con fecha" in user["content"]
    assert SCRIPT in user["content"]



def test_a_whole_document_gets_the_longer_timeout():
    llm = FakeLLM(GOOD)
    run(SCRIPT + " " + "Seguimos con el proceso habitual del equipo. " * 80, llm)
    assert llm.calls[0]["timeout"] == 60.0


def test_markdown_the_model_copies_never_reaches_a_step():
    answer = {**GOOD, "steps": [{"label": "**Apertura** con permiso", "criterion": "Se presenta y pide **un minuto**."}]}
    result = run(SCRIPT, FakeLLM(answer))
    assert result["steps"][0]["label"] == "Apertura con permiso"
    assert result["steps"][0]["criterion"] == "Se presenta y pide un minuto."

def test_the_prompt_names_only_the_seven_categories():
    prompt = structure_module._system_prompt()
    for category in OBJECTION_CATEGORIES:
        assert category in prompt


def test_labels_criteria_and_guidance_are_clipped_not_rejected():
    long_label = "Descubrir el dolor del prospecto " * 6
    long_criterion = "El prospecto nombra un problema concreto con sus palabras. " * 12
    long_guidance = "Entiendo, ¿comparado con qué lo estás mirando? " * 30
    llm = FakeLLM({
        "steps": [{"label": long_label, "criterion": long_criterion}],
        "objections": [{"category": "price", "guidance": long_guidance}],
    })
    result = run(SCRIPT, llm)
    assert result["fallback"] is False
    assert 0 < len(result["steps"][0]["label"]) <= MAX_LABEL
    assert 0 < len(result["steps"][0]["criterion"]) <= MAX_CRITERION
    assert 0 < len(result["objections"][0]["guidance"]) <= MAX_GUIDANCE
    assert_saves(result)


def test_more_than_seven_steps_become_seven_and_grouped():
    steps = [{"label": f"Paso {i}", "criterion": f"El prospecto confirma el punto {i}."} for i in range(1, 21)]
    result = run(SCRIPT, FakeLLM({"reason": None, "steps": steps, "objections": []}))
    assert len(result["steps"]) == 7
    assert result["reason"] == "grouped"
    assert result["fallback"] is False
    assert_saves(result)


def test_the_model_saying_grouped_is_kept():
    steps = [{"label": f"Etapa {i}", "criterion": f"Se confirma la etapa {i}."} for i in range(1, 6)]
    result = run(SCRIPT, FakeLLM({"reason": "grouped", "steps": steps, "objections": []}))
    assert result["reason"] == "grouped"
    assert len(result["steps"]) == 5


def test_only_the_seven_categories_survive_once_each():
    llm = FakeLLM({
        "steps": GOOD["steps"],
        "objections": [
            {"category": "Price", "guidance": "Compara con el coste de un comercial."},
            {"category": "price", "guidance": "Otra respuesta."},
            {"category": "budget", "guidance": "No existe esa categoría."},
            {"category": "trust", "guidance": "  "},
            {"category": "authority", "guidance": "Preparamos un resumen para quien decide."},
        ],
    })
    result = run(SCRIPT, llm)
    assert result["objections"] == [
        {"category": "price", "guidance": "Compara con el coste de un comercial."},
        {"category": "authority", "guidance": "Preparamos un resumen para quien decide."},
    ]


def test_an_example_is_kept_only_when_the_source_says_it_literally():
    steps = [
        {"label": "Demo con día y hora", "criterion": "Propone día y hora.", "example": "Al final propongo una demo con día y hora."},
        {"label": "Apertura", "criterion": "Se presenta.", "example": "Hola, soy Marta y te llamo por algo que no está en el guion."},
    ]
    result = run(SCRIPT, FakeLLM({"steps": steps, "objections": []}))
    assert result["steps"][0]["example"] == "Al final propongo una demo con día y hora."
    assert "example" not in result["steps"][1]


def test_the_model_own_step_ids_are_ignored():
    llm = FakeLLM({"steps": [{"step_id": "Bad Id!", "label": "Apertura", "criterion": "Se presenta."}]})
    result = run(SCRIPT, llm)
    assert result["steps"][0]["step_id"] == "apertura"


# --- attitude criteria ---


@pytest.mark.parametrize("text", [
    "Genera confianza con el prospecto",
    "Construye rapport desde el primer minuto",
    "Aporta valor en cada respuesta",
    "Escucha activa de las necesidades",
    "Escucha activamente",
    "Empatiza con el cliente",
    "Es empático y cercano",
    "Transmite seguridad y profesionalidad",
    "Se muestra seguro durante la llamada",
    "Build rapport with the buyer",
    "Adds value in every answer",
    "Uses active listening",
    "Be confident on the call",
    "Shows empathy for the customer",
    "Genera CONFIANZA",
])
def test_generic_criteria_are_recognised(text):
    assert generic_criterion(text) is True


@pytest.mark.parametrize("text", [
    "El prospecto acepta un día y una hora",
    "Se presenta y pide 30 segundos antes de contar nada",
    "Pregunta cómo lo hacen hoy y el prospecto nombra un problema concreto",
    "The prospect agrees to a day and time",
    "Menciona un caso de un cliente del mismo sector",
    "",
])
def test_observable_criteria_are_not_generic(text):
    assert generic_criterion(text) is False


def generic_answer():
    return {
        "steps": [
            {"label": "Apertura", "criterion": "Genera confianza con el prospecto."},
            {"label": "Demo con día y hora", "criterion": "Propone una demo con día y hora y el prospecto acepta."},
        ],
        "objections": [],
    }


def test_a_generic_criterion_asks_the_model_once_more_with_a_note():
    llm = FakeLLM(generic_answer(), GOOD)
    result = run(SCRIPT, llm)
    assert len(llm.calls) == 2
    retry = llm.calls[1]["messages"]
    assert retry[-1]["role"] == "user" and "Genera confianza" in retry[-1]["content"]
    assert retry[-2]["role"] == "assistant"
    assert [s["label"] for s in result["steps"]] == [s["label"] for s in GOOD["steps"]]
    assert all(s["criterion"] for s in result["steps"])
    assert result["fallback"] is False


def test_still_generic_after_the_retry_leaves_that_criterion_empty_for_review():
    llm = FakeLLM(generic_answer(), generic_answer())
    result = run(SCRIPT, llm)
    assert len(llm.calls) == 2
    assert result["fallback"] is False
    first, second = result["steps"]
    assert first["label"] == "Apertura" and first["criterion"] == ""
    assert second["criterion"].startswith("Propone una demo")
    assert_saves(result)  # an empty criterion still saves (it becomes the label)


def test_a_retry_that_fails_keeps_the_first_answer():
    llm = FakeLLM(generic_answer(), RuntimeError("boom"))
    result = run(SCRIPT, llm)
    assert result["fallback"] is False
    assert result["steps"][0]["criterion"] == ""
    assert result["steps"][1]["criterion"]


def test_a_clean_answer_is_asked_only_once():
    llm = FakeLLM(GOOD)
    run(SCRIPT, llm)
    assert len(llm.calls) == 1


# --- the model is down or useless ---

NUMBERED = (
    "1. Apertura: se presenta y pide un minuto\n"
    "2. Descubrir el dolor: pregunta cómo lo hacen hoy\n"
    "   y deja hablar al prospecto\n"
    "3. Cerrar reunión - propone día y hora"
)


@pytest.mark.parametrize("failure", [
    RuntimeError("provider down"),
    asyncio.TimeoutError(),
    ValueError("Invalid JSON"),
    ["not", "an", "object"],
    {"steps": "nope"},
    {"steps": [], "objections": []},  # nothing and no reason
    {"steps": [{"label": "  ", "criterion": "x"}]},
])
def test_a_failing_model_falls_back_to_the_line_parser(failure):
    result = run(NUMBERED, FakeLLM(failure))
    assert result["fallback"] is True
    assert [s["label"] for s in result["steps"]] == ["Apertura", "Descubrir el dolor", "Cerrar reunión"]
    assert result["steps"][1]["criterion"] == "pregunta cómo lo hacen hoy y deja hablar al prospecto"
    assert result["objections"] == []
    assert_saves(result)


def test_without_any_client_configured_it_still_returns_the_parser_result(monkeypatch):
    class Broken:
        def __init__(self, *a, **k):
            raise RuntimeError("no api key")

    monkeypatch.setattr("app.services.llm.LLMClient", Broken)
    result = asyncio.run(structure_source(NUMBERED, "discovery", "es"))
    assert result["fallback"] is True and len(result["steps"]) == 3


def test_a_source_without_a_process_returns_no_steps_and_no_process():
    llm = FakeLLM({"reason": "no_process", "steps": [], "objections": []})
    result = run(
        "Vocify es la plataforma de inteligencia comercial para equipos de ventas. Precios desde 49 euros "
        "al mes por usuario, con integración nativa con HubSpot y Pipedrive.",
        llm,
    )
    assert result == {"steps": [], "objections": [], "qualification": [], "reason": "no_process", "fallback": False}


def test_a_very_short_source_is_marked_too_short_and_still_gets_its_step():
    result = run("llamamos y agendamos", FakeLLM({"steps": [{"label": "Agendar", "criterion": "Se agenda una reunión."}]}))
    assert result["reason"] == "too_short"
    assert [s["label"] for s in result["steps"]] == ["Agendar"]
    assert result["fallback"] is False


def test_a_very_short_source_the_model_calls_no_process_still_yields_a_step():
    result = run("llamamos y agendamos", FakeLLM({"reason": "no_process", "steps": []}))
    assert result["reason"] == "too_short"
    assert len(result["steps"]) == 1
    assert_saves(result)


def test_a_source_with_no_letters_never_calls_the_model():
    llm = FakeLLM(GOOD)
    result = run("  ...  ", llm)
    assert result["steps"] == [] and result["reason"] == "too_short"
    assert llm.calls == []


def test_the_source_language_is_detected():
    assert detect_language("First I ask them how the team handles leads and then we book a call") == "en"
    assert detect_language("Primero le pregunto cómo llevan el seguimiento de los leads") == "es"
    assert detect_language("") == "es"


# --- parsePlaybookText port ---


def test_parser_numbered_steps_split_label_and_criterion():
    steps = parse_playbook_text("1. Apertura: se presenta\n2) Cualificar — quién decide\n- Cerrar - agenda")
    assert steps == [
        {"label": "Apertura", "criterion": "se presenta"},
        {"label": "Cualificar", "criterion": "quién decide"},
        {"label": "Cerrar", "criterion": "agenda"},
    ]


def test_parser_lines_under_a_step_extend_its_description():
    steps = parse_playbook_text("Paso 1: Apertura\nSe presenta\ny pide un minuto\n\nPaso 2: Cierre")
    assert steps[0] == {"label": "Apertura", "criterion": "Se presenta y pide un minuto"}
    assert steps[1] == {"label": "Cierre", "criterion": "Cierre"}


def test_parser_without_markers_takes_one_step_per_paragraph():
    steps = parse_playbook_text("Nos presentamos y pedimos permiso. Luego el motivo.\n\nPreguntamos por el dolor")
    assert [s["label"] for s in steps] == ["Nos presentamos y pedimos permiso", "Preguntamos por el dolor"]
    assert steps[0]["criterion"] == "Nos presentamos y pedimos permiso. Luego el motivo."


def test_parser_never_returns_more_than_fifteen_steps():
    text = "\n".join(f"{i}. Paso {i}" for i in range(1, 31))
    assert len(parse_playbook_text(text)) == 15


def test_parser_handles_windows_newlines_and_empty_input():
    assert [s["label"] for s in parse_playbook_text("- Uno\r\n- Dos")] == ["Uno", "Dos"]
    assert parse_playbook_text("") == []
    assert parse_playbook_text("  \n\n ") == []



_OUTLINE = """# Playbook SDR

## Objetivo del rol

Abrir conversaciones y detectar **un problema específico**.

### 1. Elegir y preparar la cuenta

- Priorizar startups B2B con SDRs
- Revisar en el CRM la relación previa y elegir **un motivo concreto**

### 2. Apertura

Abrir con nombre y una pregunta.

### 3. Cualificar

1. **Equipo y volumen:** quién llama y cuántos son
2. **Flujo actual:** CRM y telefonía
"""


def test_parser_an_outline_gives_one_step_per_numbered_heading():
    steps = parse_playbook_text(_OUTLINE)
    assert [s["label"] for s in steps] == ["Elegir y preparar la cuenta", "Apertura", "Cualificar"]
    assert steps[0]["criterion"] == (
        "Priorizar startups B2B con SDRs. Revisar en el CRM la relación previa y elegir un motivo concreto"
    )
    assert steps[1]["criterion"] == "Abrir con nombre y una pregunta."
    assert steps[2]["criterion"] == "Equipo y volumen: quién llama y cuántos son. Flujo actual: CRM y telefonía"


def test_parser_drops_markdown_and_never_cuts_a_label_mid_word():
    steps = parse_playbook_text(
        "Priorizar startups B2B con SDRs o equipo comercial activo y alta frecuencia de llamadas.\n\n**Cerrar**"
    )
    assert steps[0]["label"] == "Priorizar startups B2B con SDRs o equipo comercial activo"
    assert steps[1]["label"] == "Cerrar"
    assert all("*" not in s["label"] + s["criterion"] for s in steps)


def test_parser_numbered_lines_with_lines_under_them_are_an_outline():
    steps = parse_playbook_text("1. Apertura\n- Se presenta\n- Pide un minuto\n2. Cierre\n- Agenda")
    assert steps == [
        {"label": "Apertura", "criterion": "Se presenta. Pide un minuto"},
        {"label": "Cierre", "criterion": "Agenda"},
    ]

# --- HTTP ---


@pytest.fixture
def client_for():
    store = InMemoryPlaybookRepository()
    set_playbook_repository(store)

    def make(role="owner"):
        app = FastAPI()
        app.include_router(playbooks_router)
        app.include_router(playbook_intake_router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id="u", role=role, status="active", sales_role=None,
        )
        return TestClient(app)

    make.store = store
    yield make
    set_playbook_repository(None)
    set_playbook_structure_llm(None)
    set_playbook_transcriber(None)


URL = "/api/v1/playbooks/discovery/structure"


def test_structuring_text_returns_steps_objections_and_the_saved_source(client_for):
    llm = FakeLLM(GOOD)
    set_playbook_structure_llm(llm)
    client = client_for()
    response = client.post(URL, json={"kind": "text", "payload": SCRIPT, "name": "guion-sdr.txt"})
    assert response.status_code == 200
    body = response.json()
    assert body["sales_motion_key"] == "discovery"
    assert set(body) == {"sales_motion_key", "steps", "objections", "qualification", "reason", "fallback", "source"}
    assert body["fallback"] is False and body["reason"] is None
    assert [s["label"] for s in body["steps"]][:2] == ["Apertura con permiso", "Motivo de la llamada"]
    assert body["steps"][0]["step_id"] == "apertura_con_permiso"
    assert body["source"]["kind"] == "text" and body["source"]["name"] == "guion-sdr.txt"
    saved = client_for.store.get_import("co-1", body["source"]["id"])
    assert saved["draft"]["text"] == SCRIPT and saved["draft"]["name"] == "guion-sdr.txt"
    assert body["source"]["id"].startswith("source:")
    # It only structures: no version, no draft, nothing published.
    assert client.get("/api/v1/playbooks/discovery/editor").json()["source"] == "empty"
    assert client.get("/api/v1/playbooks").json()["motions"] == {"discovery": "missing"}  # listed, nothing more


def test_a_model_failure_is_a_200_with_fallback_true(client_for):
    set_playbook_structure_llm(FakeLLM(RuntimeError("down")))
    body = client_for().post(URL, json={"kind": "text", "payload": NUMBERED}).json()
    assert body["fallback"] is True
    assert [s["label"] for s in body["steps"]] == ["Apertura", "Descubrir el dolor", "Cerrar reunión"]
    assert body["source"]["name"]  # a default name


def test_a_pdf_is_read_and_structured(client_for):
    set_playbook_structure_llm(FakeLLM(GOOD))
    payload = base64.b64encode(_pdf_bytes("Confirmar el problema antes del precio")).decode("ascii")
    response = client_for().post(URL, json={"kind": "pdf", "payload": payload, "name": "guion.pdf"})
    assert response.status_code == 200
    saved = client_for.store.get_import("co-1", response.json()["source"]["id"])
    assert saved["kind"] == "pdf" and saved["draft"]["text"] == "Confirmar el problema antes del precio"


def test_audio_goes_through_the_transcriber(client_for):
    seen = {}

    def transcribe(payload):
        seen["payload"] = payload
        return SCRIPT

    set_playbook_transcriber(transcribe)
    set_playbook_structure_llm(FakeLLM(GOOD))
    response = client_for().post(URL, json={"kind": "audio", "payload": "audio-bytes"})
    assert response.status_code == 200
    assert seen["payload"] == "audio-bytes"
    assert response.json()["source"]["kind"] == "audio"


def _code(response):
    assert response.status_code == 422, response.text
    return response.json()["detail"]["code"]


def test_encrypted_pdf_is_422_pdf_encrypted(client_for):
    payload = base64.b64encode(_pdf_bytes("Secreto", password="secret")).decode("ascii")
    assert _code(client_for().post(URL, json={"kind": "pdf", "payload": payload})) == "pdf_encrypted"


def test_pdf_without_text_is_422_pdf_has_no_text(client_for):
    assert _code(client_for().post(URL, json={"kind": "pdf", "payload": "not a pdf"})) == "pdf_has_no_text"


def test_audio_without_speech_is_422_audio_has_no_speech(client_for):
    set_playbook_transcriber(lambda _payload: "   ")
    assert _code(client_for().post(URL, json={"kind": "audio", "payload": "x"})) == "audio_has_no_speech"


def test_audio_when_stt_is_down_is_422_stt_unavailable(client_for):
    def down(_payload):
        raise RuntimeError("stt down")

    set_playbook_transcriber(down)
    assert _code(client_for().post(URL, json={"kind": "audio", "payload": "x"})) == "stt_unavailable"


def test_an_unknown_kind_is_422_unsupported_source(client_for):
    assert _code(client_for().post(URL, json={"kind": "video", "payload": "x"})) == "unsupported_source"


def test_blank_text_is_422_empty_source(client_for):
    assert _code(client_for().post(URL, json={"kind": "text", "payload": "   \n "})) == "empty_source"


def test_a_failed_read_saves_no_source(client_for, monkeypatch):
    saved = []
    monkeypatch.setattr(client_for.store, "save_source", lambda *args, **kwargs: saved.append(args))
    client_for().post(URL, json={"kind": "text", "payload": ""})
    assert saved == []


def test_a_member_cannot_structure(client_for, monkeypatch):
    saved = []
    monkeypatch.setattr(client_for.store, "save_source", lambda *args, **kwargs: saved.append(args))
    set_playbook_structure_llm(FakeLLM(GOOD))
    response = client_for(role="member").post(URL, json={"kind": "text", "payload": SCRIPT})
    assert response.status_code == 403
    assert saved == []
