"""C04 v8: the call is read (roles, type, phase) before the steps are judged."""

import asyncio
import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-v8-reading-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-v8-reading-32b")

from app.services.intelligence.call_reading import relabel, shape_reading, split_turns
from app.services.intelligence.extract import (
    CALL_READING_PROMPT_VERSION,
    QUALIFICATION_PROMPT_VERSION,
    _locate,
    _needs_upgrade,
    build_messages,
    extract_intelligence,
    is_current,
)

# Diarization gave the rep S2 at the start and S1 at the end.
TRANSCRIPT = (
    "SPEAKER: S1\n¿Sí?\n\n"
    "SPEAKER: S2\nHola, soy Ana, te llamo de Acme, que he visto que estáis abriendo oficina en Valencia.\n\n"
    "SPEAKER: S1\nAh, vale, dime.\n\n"
    "SPEAKER: S1\n¿Cómo conseguís clientes hoy?\n\n"
    "SPEAKER: S2\nPues con ferias, y se nos escapan los leads."
)
STEPS = [
    {"step_id": "apertura", "label": "Apertura con motivo", "criterion": "Se presenta y da un motivo", "example": "soy X de Y, te llamo porque..."},
    {"step_id": "pain", "label": "Descubrir el pain", "criterion": "Pregunta cómo consiguen clientes"},
    {"step_id": "cierre", "label": "Cerrar la meeting", "criterion": "Acuerda día y hora"},
]


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.last_call_meta = {"model": "fake"}

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        # A deterministic model answers a repeated question the same way.
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def test_split_turns_numbers_speaker_blocks_and_label_lines():
    turns = split_turns(TRANSCRIPT)
    assert [t["speaker"] for t in turns] == ["S1", "S2", "S1", "S1", "S2"]
    named = split_turns("Ana García: hola\nPedro: dime\nAna García: te llamo de Acme")
    assert [t["speaker"] for t in named] == ["Ana García", "Pedro", "Ana García"]
    assert split_turns("un dictado sin etiquetas") == [{"speaker": None, "text": "un dictado sin etiquetas"}]


def test_shape_reading_keeps_allowed_values_and_expands_ranges():
    turns = split_turns(TRANSCRIPT)
    reading = shape_reading(
        {"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, "4-4", 99, True]},
        turns,
    )
    assert reading["call_type"] == "cold_first_contact"
    assert reading["rep_turns"] == [2, 4]
    assert reading["reached_conversation"] is True

    unknown = shape_reading({"call_type": "sales_call", "phase_reached": "end"}, turns)
    assert unknown["call_type"] == "other" and unknown["phase_reached"] == "none"

    voicemail = shape_reading({"call_type": "no_conversation", "phase_reached": "opening", "reached_conversation": True}, turns)
    assert voicemail["reached_conversation"] is False and voicemail["phase_reached"] == "none"


def test_relabel_follows_the_reading_not_the_diarization():
    turns = split_turns(TRANSCRIPT)
    text = relabel(turns, {"rep_turns": [2, 4]})
    assert text.splitlines()[0] == "Them: ¿Sí?"
    assert text.split("\n\n")[1].startswith("You: Hola, soy Ana")
    assert text.split("\n\n")[3] == "You: ¿Cómo conseguís clientes hoy?"


def test_locate_ignores_case_accents_and_punctuation_but_returns_the_transcripts_words():
    transcript = "SPEAKER: S2\n¿Qué tal? Soy Álvaro, te llamo de Acme, ¿vale?"
    assert _locate("soy alvaro te llamo de acme", transcript) == "Soy Álvaro, te llamo de Acme"
    assert _locate("Soy Álvaro, te llamo de Acme", transcript) == "Soy Álvaro, te llamo de Acme"
    assert _locate("vale", transcript) == "vale"  # exact is always fine
    assert _locate("que tal", transcript) is None  # folded, a short quote could land anywhere
    assert _locate("te llamo de otra empresa", transcript) is None


def test_v8_payload_carries_the_call_the_relabeled_transcript_and_step_examples():
    memo = {"id": "m-1", "transcript": TRANSCRIPT, "created_at": "2026-09-28T10:00:00+02:00", "extraction": {"summary": "s"}}
    messages = build_messages(
        memo, prompt_version=CALL_READING_PROMPT_VERSION, playbook_steps=STEPS,
        transcript="You: hola", call={"call_type": "follow_up", "phase_reached": "opening", "reached_conversation": True, "rep_turns": [1]},
    )
    payload = json.loads(messages[1]["content"])
    assert payload["transcript"] == "You: hola"
    assert payload["call"] == {"call_type": "follow_up", "phase_reached": "opening", "reached_conversation": True, "roles_marked": True}
    assert payload["playbook_steps"][0]["example"] == "soy X de Y, te llamo porque..."
    v7 = json.loads(build_messages(memo, prompt_version=QUALIFICATION_PROMPT_VERSION, playbook_steps=STEPS)[1]["content"])
    assert "example" not in v7["playbook_steps"][0] and "call" not in v7


def _run(reading, judged):
    memo = {"id": "m-1", "transcript": TRANSCRIPT, "created_at": "2026-09-28T10:00:00+02:00", "extraction": {"summary": "s"}}
    llm = FakeLLM(reading, judged)
    shaped, meta = asyncio.run(extract_intelligence(
        memo, llm, prompt_version=CALL_READING_PROMPT_VERSION, playbook_steps=STEPS,
        rep_name="Ana", company_name="Acme",
    ))
    return shaped, meta, llm


def test_v8_reads_the_call_then_judges_the_rep_on_their_own_words():
    shaped, meta, llm = _run(
        {"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]},
        {"interest": "medium", "playbook_observations": [
            {"step_id": "apertura", "reason": "Se presenta y da un motivo", "status": "met",
             "quote": "soy ana te llamo de acme que he visto que estais abriendo oficina en valencia"},
            {"step_id": "pain", "reason": "Pregunta cómo consiguen clientes", "status": "met", "quote": "¿Cómo conseguís clientes hoy?"},
            {"step_id": "cierre", "reason": "No propone reunión", "status": "missed",
             "quote": "Pues con ferias, y se nos escapan los leads.", "advice": "Propón un día para enseñarle cómo."},
        ]},
    )
    reading_payload = json.loads(llm.calls[0][1]["content"])
    assert reading_payload["rep_name"] == "Ana" and "[2] S2: Hola, soy Ana" in reading_payload["turns"]
    judged_payload = json.loads(llm.calls[1][1]["content"])
    assert judged_payload["transcript"].startswith("Them: ¿Sí?\n\nYou: Hola, soy Ana")
    steps = {o["step_id"]: o for o in shaped["playbook_observations"]}
    # A paraphrased (accent/punctuation-free) quote still counts, with the transcript's own words.
    assert steps["apertura"]["status"] == "met"
    assert steps["apertura"]["quote"] == "soy Ana, te llamo de Acme, que he visto que estáis abriendo oficina en Valencia"
    assert steps["pain"]["status"] == "met"  # S1 in the diarization, the rep by the reading
    # Booking the meeting is the rep's to declare: never sent to the model, never judged by it.
    assert [s["step_id"] for s in judged_payload["playbook_steps"]] == ["apertura", "pain"]
    assert steps["cierre"]["status"] == "unknown" and steps["cierre"]["judged_by"] == "rep_outcome"
    assert "advice" not in steps["cierre"]
    assert steps["apertura"]["reason"] == "Se presenta y da un motivo"
    assert shaped["call"]["call_type"] == "cold_first_contact"
    assert shaped["prompt_version"] == CALL_READING_PROMPT_VERSION
    assert meta["call_reading"] == {"model": "fake"}


def test_v8_a_prospects_line_never_counts_as_the_rep_doing_a_step():
    shaped, _, _ = _run(
        {"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]},
        {"playbook_observations": [
            {"step_id": "pain", "status": "met", "quote": "Pues con ferias, y se nos escapan los leads."},
        ]},
    )
    steps = {o["step_id"]: o for o in shaped["playbook_observations"]}
    assert steps["pain"]["status"] == "unknown"


def test_v8_a_call_stopped_at_the_door_only_judges_the_opening():
    shaped, _, _ = _run(
        {"call_type": "bad_moment", "phase_reached": "opening", "rep_turns": [2]},
        {"playbook_observations": [
            {"step_id": "apertura", "status": "met", "quote": "Hola, soy Ana, te llamo de Acme"},
            {"step_id": "pain", "status": "missed", "quote": "Ah, vale, dime.", "advice": "x"},
            {"step_id": "cierre", "status": "missed", "quote": "Ah, vale, dime."},
        ]},
    )
    statuses = {o["step_id"]: o["status"] for o in shaped["playbook_observations"]}
    assert statuses == {"apertura": "met", "pain": "not_applicable", "cierre": "not_applicable"}
    assert all("advice" not in o for o in shaped["playbook_observations"])


def test_v8_no_conversation_judges_nothing():
    shaped, _, _ = _run(
        {"call_type": "no_conversation", "phase_reached": "none", "rep_turns": []},
        {"playbook_observations": [{"step_id": "apertura", "status": "missed", "quote": "¿Sí?"}]},
    )
    assert {o["status"] for o in shaped["playbook_observations"]} == {"not_applicable"}


def test_v8_is_current_and_upgrades_older_blocks():
    assert _needs_upgrade({"extraction": {"intelligence": {"prompt_version": QUALIFICATION_PROMPT_VERSION}}}, CALL_READING_PROMPT_VERSION)
    assert not _needs_upgrade({"extraction": {"intelligence": {"prompt_version": CALL_READING_PROMPT_VERSION}}}, CALL_READING_PROMPT_VERSION)
    assert not is_current({"extraction": {"intelligence": {"prompt_version": CALL_READING_PROMPT_VERSION, "input_revision": "x"}}})


def test_v8_next_actions_are_shaped_for_the_brief_and_the_email():
    shaped, _, _ = _run(
        {"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]},
        {"playbook_observations": [], "next": {
            "outcome": {"text": "Contó que se le escapan los leads de ferias", "quote": "se nos escapan los leads"},
            "callback": {"needed": True, "who_asked": "prospect", "when": "2026-09-29T12:30:00+02:00",
                         "when_text": "el lunes a las 12:30", "reason": "quiere verlo con su socio", "quote": None},
            "followup_email": {"needed": True, "kind": "brochure", "content": "casos de éxito", "to": None, "quote": "inventada"},
            "referral": {"name": "", "role": ""},
            "hook": "Pregúntale por las ferias",
        }},
    )
    nxt = shaped["next"]
    assert nxt["outcome"]["text"].startswith("Contó que") and len(nxt["outcome"]["evidence_refs"]) == 1
    assert nxt["callback"]["needed"] and nxt["callback"]["who_asked"] == "prospect"
    assert nxt["callback"]["when"].startswith("2026-10-05T12:30") and nxt["callback"]["temporal_precision"] == "time"  # "el lunes" said on a Monday
    assert nxt["followup_email"] == {"needed": True, "kind": "other", "content": "casos de éxito", "to": None, "evidence_refs": []}
    assert nxt["referral"] is None and nxt["hook"] == "Pregúntale por las ferias"


def test_v8_nothing_said_means_nothing_next():
    shaped, _, _ = _run({"call_type": "no_conversation", "phase_reached": "none"}, {"playbook_observations": []})
    assert shaped["next"] == {"outcome": None, "callback": {"needed": False}, "followup_email": {"needed": False},
                              "referral": None, "hook": None}


def test_v8_callback_day_comes_from_the_words_said_not_the_models_arithmetic():
    shaped, _, _ = _run(
        {"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]},
        {"playbook_observations": [], "next": {"callback": {
            "needed": True, "who_asked": "prospect", "when": "2026-11-28", "when_text": "en un año", "reason": "presupuesto"}}},
    )
    assert shaped["next"]["callback"]["when"].startswith("2027-09-28")
    timed, _, _ = _run(
        {"call_type": "bad_moment", "phase_reached": "opening", "rep_turns": [2]},
        {"playbook_observations": [], "next": {"callback": {
            "needed": True, "who_asked": "prospect", "when": "2026-09-28T12:30:00+02:00", "when_text": "mañana a las 12:30"}}},
    )
    assert timed["next"]["callback"]["when"].startswith("2026-09-29T12:30") and timed["next"]["callback"]["temporal_precision"] == "time"


def test_v8_a_quote_of_the_whole_exchange_counts_on_the_reps_part_and_carries_quality():
    shaped, _, _ = _run(
        {"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]},
        {"playbook_observations": [
            {"step_id": "pain", "status": "met", "quality": "improvable", "reason": "Preguntaste pero no profundizaste",
             "advice": "Repregunta qué le cuesta más.",
             "quote": "¿Cómo conseguís clientes hoy? Pues con ferias, y se nos escapan los leads."},
        ]},
    )
    pain = {o["step_id"]: o for o in shaped["playbook_observations"]}["pain"]
    assert pain["status"] == "met" and pain["quote"] == "Cómo conseguís clientes hoy"
    assert pain["quality"] == "improvable" and pain["advice"] == "Repregunta qué le cuesta más."


def test_v8_a_step_the_model_left_out_is_read_once_more():
    memo = {"id": "m-1", "transcript": TRANSCRIPT, "created_at": "2026-09-28T10:00:00+02:00", "extraction": {"summary": "s"}}
    partial = {"playbook_observations": [{"step_id": "apertura", "status": "met", "quote": "soy Ana, te llamo de Acme"}]}
    full = {"playbook_observations": [
        {"step_id": "apertura", "status": "met", "quote": "soy Ana, te llamo de Acme"},
        {"step_id": "pain", "status": "met", "quote": "¿Cómo conseguís clientes hoy?"},
    ]}
    llm = FakeLLM({"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]}, partial, full)
    shaped, _ = asyncio.run(extract_intelligence(memo, llm, prompt_version=CALL_READING_PROMPT_VERSION, playbook_steps=STEPS))
    assert len(llm.calls) == 3
    assert {o["step_id"]: o["status"] for o in shaped["playbook_observations"]}["pain"] == "met"


def test_v8_a_step_done_in_a_call_stopped_at_the_door_still_counts():
    shaped, _, _ = _run(
        {"call_type": "wrong_person", "phase_reached": "discovery", "rep_turns": [2, 4]},
        {"playbook_observations": [
            {"step_id": "apertura", "status": "met", "quote": "soy Ana, te llamo de Acme"},
            {"step_id": "pain", "status": "met", "quote": "¿Cómo conseguís clientes hoy?"},
        ]},
    )
    assert {o["step_id"]: o["status"] for o in shaped["playbook_observations"]}["pain"] == "met"


def test_v8_no_conversation_skips_the_second_pass():
    memo = {"id": "m-1", "transcript": TRANSCRIPT, "created_at": "2026-09-28T10:00:00+02:00", "extraction": {"summary": "s"}}
    llm = FakeLLM({"call_type": "no_conversation", "phase_reached": "none", "rep_turns": []})
    shaped, _ = asyncio.run(extract_intelligence(memo, llm, prompt_version=CALL_READING_PROMPT_VERSION, playbook_steps=STEPS))
    assert len(llm.calls) == 1  # the reading only
    assert {o["status"] for o in shaped["playbook_observations"]} == {"not_applicable"}
    assert shaped["next"]["callback"] == {"needed": False}


def test_v8_reuses_the_reading_the_crm_pass_stored_for_the_same_transcript():
    from app.services.intelligence.call_reading import PROMPT_VERSION as READING_VERSION
    reading = {"version": READING_VERSION, "call_type": "cold_first_contact", "phase_reached": "discovery",
               "reached_conversation": True, "rep_turns": [2, 4], "other_turns": [], "turn_count": 5, "roles_marked": True}
    memo = {"id": "m-1", "transcript": TRANSCRIPT, "created_at": "2026-09-28T10:00:00+02:00",
            "extraction": {"summary": "s", "call_reading": reading}}
    llm = FakeLLM({"playbook_observations": [{"step_id": "apertura", "status": "met", "quote": "soy Ana, te llamo de Acme"},
                                             {"step_id": "pain", "status": "met", "quote": "¿Cómo conseguís clientes hoy?"}]})
    shaped, _ = asyncio.run(extract_intelligence(memo, llm, prompt_version=CALL_READING_PROMPT_VERSION, playbook_steps=STEPS))
    assert len(llm.calls) == 1  # no second reading
    assert json.loads(llm.calls[0][1]["content"])["transcript"].startswith("Them: ¿Sí?\n\nYou: Hola, soy Ana")
    stale = {**memo, "extraction": {"summary": "s", "call_reading": {**reading, "turn_count": 9}}}
    llm2 = FakeLLM({"call_type": "cold_first_contact", "phase_reached": "discovery", "rep_turns": [2, 4]}, {"playbook_observations": []})
    asyncio.run(extract_intelligence(stale, llm2, prompt_version=CALL_READING_PROMPT_VERSION, playbook_steps=STEPS))
    assert len(llm2.calls) >= 2  # a reading that does not fit is made again
