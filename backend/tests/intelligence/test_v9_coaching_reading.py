"""C04 v9: v8 plus a reading of the whole call that coaching shows first, and each objection's nature
with what would have served."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-v9-reading-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-v9-reading-32b")

from app.services.coaching import rep_coaching
from app.services.coaching.rep_coaching_reads import as_extraction
from app.services.intelligence import extract
from app.services.intelligence.extract import (
    CALL_READING_PROMPT_VERSION,
    COACHING_READING_PROMPT_VERSION,
    QUALIFICATION_PROMPT_VERSION,
    _needs_upgrade,
    build_messages,
    extract_intelligence,
)

TRANSCRIPT = (
    "SPEAKER: S1\nHola, soy Toni de Vocify, hemos conectado por LinkedIn.\n\n"
    "SPEAKER: S2\nDime.\n\n"
    "SPEAKER: S1\nHacemos que tu equipo siga el proceso y responda las objeciones como tú.\n\n"
    "SPEAKER: S2\nMis comerciales ya saben lo que tienen que decir, ya venden y llegan a sus números.\n\n"
    "SPEAKER: S1\nSí, exactamente. Y además actualizamos el CRM y hacemos reporting.\n\n"
    "SPEAKER: S2\nEso ya lo tenemos con Pipedrive, y los reportes ni los leo."
)
STEPS = [
    {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y da un motivo"},
    {"step_id": "problema", "label": "Problema", "criterion": "Pregunta cómo trabajan hoy"},
]
READING_CALL = {"call_type": "cold_first_contact", "phase_reached": "pitch", "rep_turns": [1, 3, 5]}


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.last_call_meta = {"model": "fake"}

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def _run(judged, version=COACHING_READING_PROMPT_VERSION):
    memo = {"id": "m-9", "transcript": TRANSCRIPT, "created_at": "2026-10-21T10:00:00+02:00", "extraction": {"summary": "s"}}
    llm = FakeLLM(READING_CALL, judged)
    shaped, _ = asyncio.run(extract_intelligence(memo, llm, prompt_version=version, playbook_steps=STEPS))
    return shaped, llm


JUDGED = {
    "reading": {
        "verdict": "Te dijo que no tenía el problema y seguiste vendiendo.",
        "pain": "absent",
        "decisive_moment": {"quote": "mis comerciales ya saben lo que tienen que decir", "meaning": "Descarta el problema."},
        "root_cause": "Vendiste control a quien no quiere controlar.",
        "main_error": "Seguiste explicando funcionalidades cuando ya te había dicho que no lo necesita.",
        "steer": {"line": "Entiendo. ¿Hay alguna reunión difícil en la que aún te consulten?",
                  "branches": [{"if": "Dice que no", "then": "Perfecto, ¿te escribo cuando crezca el equipo?"},
                               {"if": "Dice que sí", "then": "¿Qué tipo de reuniones son?"},
                               {"if": "Cuelga", "then": "Nada"}, {"if": "Cuarta", "then": "Sobra"},
                               {"if": "", "then": "Sin condición"}]},
        "best_outcome": {"what": "Descartar limpio y dejar la puerta abierta.", "got": False},
    },
    "objections": [
        {"kind": "objection", "category": "status_quo", "nature": "sin_dolor", "resolution": "open",
         "quote": "Mis comerciales ya saben lo que tienen que decir, ya venden y llegan a sus números.",
         "response": "Sí, exactamente. Y además actualizamos el CRM y hacemos reporting.",
         "advice": "No había nada que rebatir: comprueba una última hipótesis.", "line": "¿Hay alguna reunión en la que aún te consulten?"},
        {"kind": "objection", "category": "competitor", "nature": "inventada", "resolution": "open",
         "quote": "Eso ya lo tenemos con Pipedrive, y los reportes ni los leo.", "response": None, "advice": None, "line": None},
    ],
    "playbook_observations": [
        {"step_id": "apertura", "status": "met", "quality": "solid", "reason": "Te presentaste.", "quote": "Hola, soy Toni de Vocify, hemos conectado por LinkedIn."},
        {"step_id": "problema", "status": "missed", "reason": "No preguntaste.", "quote": "Mis comerciales ya saben lo que tienen que decir, ya venden y llegan a sus números.",
         "advice": "Pregunta antes de explicar."},
    ],
}


def test_v9_keeps_the_reading_with_the_decisive_moment_found_in_the_transcript():
    shaped, _ = _run(JUDGED)
    reading = shaped["reading"]
    assert shaped["prompt_version"] == COACHING_READING_PROMPT_VERSION
    assert reading["pain"] == "absent"
    assert reading["main_error"].startswith("Seguiste explicando")
    # The prospect's words come back as the transcript has them.
    assert reading["decisive_moment"]["quote"] == "Mis comerciales ya saben lo que tienen que decir"
    assert reading["decisive_moment"]["evidence_refs"]
    # At most three branches, each with both halves.
    assert [b["if"] for b in reading["steer"]["branches"]] == ["Dice que no", "Dice que sí", "Cuelga"]
    assert reading["best_outcome"] == {"what": "Descartar limpio y dejar la puerta abierta.", "got": False}


def test_v9_a_decisive_moment_nobody_said_is_dropped_and_the_rest_stays():
    judged = {**JUDGED, "reading": {**JUDGED["reading"], "decisive_moment": {"quote": "esto no lo dijo nadie en la llamada", "meaning": "x"}}}
    shaped, _ = _run(judged)
    assert shaped["reading"]["decisive_moment"] is None
    assert shaped["reading"]["main_error"]


def test_v9_an_empty_reading_is_none():
    shaped, _ = _run({**JUDGED, "reading": {"verdict": "", "steer": {"line": ""}}})
    assert shaped["reading"] is None


def test_v9_objections_carry_their_nature_advice_and_line():
    shaped, _ = _run(JUDGED)
    first, second = shaped["objections"]
    assert first["nature"] == "sin_dolor"
    assert first["advice"].startswith("No había nada que rebatir")
    assert first["line"] == "¿Hay alguna reunión en la que aún te consulten?"
    assert second["nature"] is None  # a nature the prompt does not have is dropped
    assert second["advice"] is None and second["line"] is None


def test_v8_shapes_neither_the_reading_nor_the_new_objection_fields():
    shaped, _ = _run(JUDGED, version=CALL_READING_PROMPT_VERSION)
    assert "reading" not in shaped
    assert "nature" not in shaped["objections"][0]


def test_v9_steps_are_judged_as_in_v8():
    shaped, _ = _run(JUDGED)
    steps = {o["step_id"]: o for o in shaped["playbook_observations"]}
    assert steps["apertura"]["status"] == "met"
    assert steps["problema"]["status"] == "missed" and steps["problema"]["advice"] == "Pregunta antes de explicar."


def test_v9_payload_is_the_v8_one_with_the_v9_prompt():
    memo = {"id": "m", "transcript": "You: hola", "extraction": {}}
    system = build_messages(memo, prompt_version=COACHING_READING_PROMPT_VERSION, playbook_steps=STEPS, call=READING_CALL, transcript="You: hola")[0]["content"]
    assert "FIRST, READ THE CALL AS A WHOLE" in system and "main_error" in system and "best_outcome" in system


def test_v9_does_not_re_read_v8_blocks_but_upgrades_older_ones():
    def memo(version):
        return {"extraction": {"intelligence": {"prompt_version": version}}}
    assert not _needs_upgrade(memo(CALL_READING_PROMPT_VERSION), COACHING_READING_PROMPT_VERSION)
    assert _needs_upgrade(memo(QUALIFICATION_PROMPT_VERSION), COACHING_READING_PROMPT_VERSION)


def test_v9_needs_both_flags(monkeypatch):
    on: set[str] = set()
    monkeypatch.setattr("app.services.feature_flags.is_enabled", lambda _sb, _cid, flag: flag in on)
    monkeypatch.setattr(extract, "pinned_playbook_steps", lambda _sb, _memo: STEPS)
    memo = {"company_id": "c"}
    on.add(extract.COACHING_READING_FLAG)
    assert extract.extraction_plan(None, memo)[0] != COACHING_READING_PROMPT_VERSION
    on.add(extract.CALL_READING_FLAG)
    assert extract.extraction_plan(None, memo)[0] == COACHING_READING_PROMPT_VERSION
    on.discard(extract.COACHING_READING_FLAG)
    assert extract.extraction_plan(None, memo)[0] == CALL_READING_PROMPT_VERSION


def test_coaching_reads_the_reading_and_the_objection_fields():
    shaped, _ = _run(JUDGED)
    trimmed = {
        "id": "m-9", "user_id": "u", "company_id": "c", "sales_motion_key": "discovery", "audio_duration": 600,
        "created_at": "2026-10-21T08:00:00+00:00", "observations": shaped["playbook_observations"],
        "call_type": "cold_first_contact", "reached_conversation": True, "outcome": None,
        "objections": shaped["objections"], "reading": shaped["reading"], "summary": "s",
    }
    row = rep_coaching.interaction_row(as_extraction(trimmed))
    assert row["reading"]["main_error"].startswith("Seguiste explicando")
    objection = rep_coaching.call_objections(row, [])[0]
    assert objection["nature"] == "sin_dolor" and objection["line"]
