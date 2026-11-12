"""C04 findings: the prospect's questions, the doors let pass, what worked off the playbook and what was conceded,
each standing on the right speaker's own words."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-call-findings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-call-findings-32")

from app.services.intelligence import findings

TRANSCRIPT = "\n".join([
    "You: Hola, soy Daniel de Movertis, del Grupo Movilia.",
    "Them: Dime, que estoy liado con la huelga.",
    "You: Te llamo por la gestión de la flota, ¿cómo lo lleváis hoy?",
    "Them: Lo llevamos con otro proveedor, pero el tema de los CAE a ver hasta dónde los gestionáis vosotros y qué coste.",
    "You: Sí, sí, no hay problema, te mando un correo con todo.",
    "Them: Me parece bastante caro en comparación con lo que pago ahora.",
    "You: Te lo puedo dejar a 11 euros por tractora como mucho.",
    "Them: Antes de comprometerme a doce meses tendría que probarlo.",
    "You: Lo que podemos hacer es una prueba de un mes sin permanencia con un vehículo.",
    "Them: Vale, pues pásamelo por WhatsApp y lo reviso esta tarde.",
])
CALL = {"call_type": "cold_first_contact", "phase_reached": "closing", "reached_conversation": True}
CAE = "el tema de los CAE a ver hasta dónde los gestionáis vosotros y qué coste"


def _shape(raw, **kwargs):
    return findings.shape_findings("m-1", raw, TRANSCRIPT, **kwargs)


def test_a_question_is_the_prospects_words_and_an_answer_the_reps():
    shaped = _shape({"questions": [
        {"quote": CAE, "topic": "gestión de CAE", "answered": "yes", "answer": "te mando un correo con todo", "covered_by": "material"},
        # The rep's own words are not the prospect's question.
        {"quote": "¿cómo lo lleváis hoy?", "topic": "Situación actual", "answered": "yes", "answer": None},
    ]})
    assert [q["topic"] for q in shaped["questions"]] == ["Gestión de CAE"]
    question = shaped["questions"][0]
    assert (question["quote"], question["answer"], question["covered_by"]) == (CAE, "te mando un correo con todo", "material")
    assert question["answered"] == "yes" and len(question["evidence_refs"]) == 2


def test_an_answer_the_transcript_does_not_show_is_no_answer_and_an_unknown_answer_id_is_dropped():
    shaped = _shape({"questions": [
        {"quote": CAE, "topic": "Gestión de CAE", "answered": "yes", "answer": "Los CAE van incluidos", "covered_by": "cae_incluido"},
    ]}, answer_ids={"es_caro"})
    question = shaped["questions"][0]
    assert (question["answered"], question["answer"], question["covered_by"]) == ("no", None, None)


def test_the_same_moment_never_counts_twice_and_topics_keep_their_earlier_name():
    shaped = _shape({
        "questions": [{"quote": CAE, "topic": "gestión  de cae.", "answered": "no"}],
        "signals": [{"quote": CAE, "kind": "interest", "topic": "Gestión de CAE", "why": "Abrió la puerta a los CAE.", "line": "¿Cuántos CAE lleváis al mes?"}],
    }, known_topics=["Gestión de CAE"])
    assert [q["topic"] for q in shaped["questions"]] == ["Gestión de CAE"]
    assert shaped["signals"] == []  # the same words, already a question


def test_worked_needs_the_prospects_words_right_after_and_a_concession_is_the_reps():
    move = "Lo que podemos hacer es una prueba de un mes sin permanencia con un vehículo"
    shaped = _shape({
        "worked": [
            {"quote": move, "after_quote": "pásamelo por WhatsApp y lo reviso esta tarde", "topic": "prueba de un mes sin permanencia", "why": "Quitó el miedo a los doce meses."},
            {"quote": "Te lo puedo dejar a 11 euros por tractora como mucho", "after_quote": None, "topic": "Bajar precio", "why": "Cerró."},
        ],
        "concessions": [
            {"quote": "Te lo puedo dejar a 11 euros por tractora como mucho", "kind": "price", "what": "Precio de 11 € por tractora", "normal": "17 € al mes por tractora"},
            {"quote": "Me parece bastante caro en comparación con lo que pago ahora", "kind": "price", "what": "Caro"},
        ],
    })
    assert [(w["topic"], w["after_quote"]) for w in shaped["worked"]] == [
        ("Prueba de un mes sin permanencia", "pásamelo por WhatsApp y lo reviso esta tarde"),
    ]
    assert [(c["kind"], c["what"], c["normal"]) for c in shaped["concessions"]] == [
        ("price", "Precio de 11 € por tractora", "17 € al mes por tractora"),
    ]  # the prospect saying it is expensive is not a concession; the 11 € (dropped from worked) still is


def test_one_move_of_the_rep_can_be_what_worked_and_what_it_conceded():
    move = "Lo que podemos hacer es una prueba de un mes sin permanencia con un vehículo"
    shaped = _shape({
        "worked": [{"quote": move, "after_quote": "pásamelo por WhatsApp y lo reviso esta tarde", "topic": "Prueba de un mes", "why": "Quitó el miedo."}],
        "concessions": [{"quote": move, "kind": "trial", "what": "Prueba de un mes sin permanencia"}],
    })
    assert len(shaped["worked"]) == 1 and len(shaped["concessions"]) == 1


def test_each_list_has_a_limit_and_bad_entries_are_dropped():
    lines = [line[len("Them: "):] for line in TRANSCRIPT.splitlines() if line.startswith("Them:")]
    raw = {"signals": [
        {"quote": text, "kind": "made_up", "topic": f"Tema {i}", "why": "Una puerta."} for i, text in enumerate(lines)
    ] + [{"quote": lines[0], "topic": "", "why": "x"}, "basura"]}
    shaped = _shape(raw)
    assert len(shaped["signals"]) == 3 and {s["kind"] for s in shaped["signals"]} == {"other"}


def test_only_a_sales_conversation_is_read_and_a_failed_read_gives_nothing():
    class Broken:
        async def chat_json(self, *_a, **_k):
            raise RuntimeError("down")

    assert findings.wants_findings(CALL) is True
    assert findings.wants_findings({**CALL, "call_type": "not_a_sales_call"}) is False
    assert findings.wants_findings({**CALL, "reached_conversation": False}) is False
    assert asyncio.run(findings.read_findings("m-1", TRANSCRIPT, Broken(), call=CALL)) is None


def test_the_prompt_gets_the_material_and_the_earlier_topics():
    messages = findings.build_messages(
        TRANSCRIPT, call=CALL, answers=[{"id": "es_caro", "label": "Es caro", "trigger": "caro", "answer": "Compara con el coste."}],
        material=findings.compact_material({"pricing": "17 € al mes por tractora", "proofs": [{"text": "Caso Logística"}], "bad_fit": ""}),
        known_topics=["Gestión de CAE"],
    )
    body = messages[1]["content"]
    assert "17 € al mes por tractora" in body and "Caso Logística" in body and "Gestión de CAE" in body and "bad_fit" not in body
    assert "known_topics" in messages[0]["content"]


def test_known_topics_are_the_most_used_first():
    rows = [
        {"findings": {"questions": [{"topic": "Gestión de CAE"}, {"topic": "Precio por vehículo"}]}},
        {"findings": {"signals": [{"topic": "gestión de cae"}]}},
        {"findings": None},
    ]
    assert findings.known_topics_of(rows) == ["Gestión de CAE", "Precio por vehículo"]


def test_the_analysis_reads_the_findings_after_judging_and_only_when_asked():
    from app.services.intelligence.extract import COACHING_ANSWERS_PROMPT_VERSION, extract_intelligence

    spoken = (
        "SPEAKER: S1\nHola, soy Daniel de Movertis, del Grupo Movilia.\n\n"
        "SPEAKER: S2\nDime, ¿y la instalación de los equipos la hacéis vosotros o la tengo que hacer yo?\n\n"
        "SPEAKER: S1\nLa instalación la hacemos nosotros con un técnico, va incluida.\n\n"
        "SPEAKER: S2\nVale, pues mándame el contrato y lo firmo esta tarde."
    )
    reading = {"call_type": "cold_first_contact", "phase_reached": "closing", "rep_turns": [1, 3]}
    found = {"questions": [{"quote": "¿y la instalación de los equipos la hacéis vosotros o la tengo que hacer yo?",
                            "topic": "Instalación de los equipos", "answered": "yes",
                            "answer": "La instalación la hacemos nosotros con un técnico, va incluida", "covered_by": None}]}

    class FakeLLM:
        def __init__(self, *responses):
            self.responses, self.calls, self.last_call_meta = list(responses), [], {"model": "fake"}

        async def chat_json(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return self.responses.pop(0)

    memo = {"id": "m-f", "transcript": spoken, "created_at": "2026-11-12T10:00:00+01:00", "extraction": {"summary": "s"}}
    llm = FakeLLM(reading, {"objections": []}, found)
    shaped, _ = asyncio.run(extract_intelligence(
        memo, llm, prompt_version=COACHING_ANSWERS_PROMPT_VERSION,
        findings_inputs={"material": {"pricing": "Alquiler con equipo incluido"}, "known_topics": []},
    ))
    assert len(llm.calls) == 3 and "head of sales" in llm.calls[2][0][0]["content"]
    assert llm.calls[2][1]["reasoning_effort"] == "medium"
    question = shaped["findings"]["questions"][0]
    assert (question["topic"], question["answered"]) == ("Instalación de los equipos", "yes")

    llm = FakeLLM(reading, {"objections": []})
    shaped, _ = asyncio.run(extract_intelligence(memo, llm, prompt_version=COACHING_ANSWERS_PROMPT_VERSION))
    assert len(llm.calls) == 2 and "findings" not in shaped


def test_the_reps_coaching_gets_what_to_do_next_time_and_never_the_concessions():
    shaped = {
        "questions": [
            {"topic": "Gestión de CAE", "quote": CAE, "answered": "no", "answer": None, "covered_by": None, "better": None},
            {"topic": "Instalación", "quote": "x", "answered": "yes", "answer": "y", "covered_by": None, "better": None},
            {"topic": "Permanencia", "quote": "z", "answered": "partly", "answer": "w", "covered_by": "material", "better": "Son 12 meses."},
        ],
        "signals": [], "worked": [], "concessions": [{"kind": "price", "what": "11 €", "quote": "q"}],
    }
    coach = findings.coach_findings(shaped)
    assert [(q["topic"], q["no_answer"]) for q in coach["questions"]] == [("Gestión de CAE", True), ("Permanencia", False)]
    assert "concessions" not in coach
    assert findings.coach_findings({"questions": [shaped["questions"][1]], "signals": [], "worked": []}) is None


def test_a_quote_that_lands_on_other_words_of_the_call_drops_the_item():
    shaped = _shape({"signals": [
        # The prospect never said this; a few of its words appear elsewhere, which is not the same moment.
        {"quote": "Lo llevamos con Atlantis y nos falta el tema de los CAE que nadie revisa", "kind": "unhappy",
         "topic": "Proveedor actual", "why": "Mencionó a Atlantis."},
    ]})
    assert shaped["signals"] == []


def test_a_door_that_is_the_calls_turning_point_is_not_shown_twice():
    shaped = {"questions": [], "worked": [], "signals": [
        {"topic": "Contacto en Quadis", "quote": "tendrías que dirigirte directamente a Cuadis", "kind": "referral", "why": "x", "line": "y"},
        {"topic": "Otra", "quote": "Natalia lleva la flota", "kind": "referral", "why": "x", "line": "y"},
    ]}
    reading = {"decisive_moment": {"quote": "es Cuadis, con lo cual tendrías que dirigirte  directamente a Cuadis."}}
    assert [s["topic"] for s in findings.coach_findings(shaped, reading)["signals"]] == ["Otra"]
