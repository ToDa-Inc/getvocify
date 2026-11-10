"""C04 v10/v11: objections read against every answer of the company's playbook, only real pushback counted, and
what happened right after the rep's reply (Dani, 2026-11-10)."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-v10-answers-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-v10-answers-32b")

from app.services.intelligence import extract
from app.services.intelligence.extract import build_messages, extract_intelligence, playbook_answers, playbook_qualification_inputs

TRANSCRIPT = (
    "SPEAKER: S1\nHola, soy Toni de Vocify.\n\n"
    "SPEAKER: S2\nMira, ahora no estamos buscando este tipo de soluciones.\n\n"
    "SPEAKER: S1\n¿Por qué, qué cambiaría para el año que viene?\n\n"
    "SPEAKER: S2\nDéjame mirarlo y si me interesa podríamos agendar.\n\n"
    "SPEAKER: S1\nVale.\n\n"
    "SPEAKER: S2\nY lo de grabar las llamadas no lo tengo claro por el tema legal."
)
ENTRIES = [
    {"entry_id": "objection:timing", "category": "timing", "guidance": "Pregunta qué cambiaría y deja fecha."},
    {"entry_id": "objection:custom:es_caro", "category": "custom", "label": "Es caro", "trigger": "Es caro",
     "guidance": "¿Respecto a qué te parece caro?"},
    {"entry_id": "objection:price", "category": "price", "guidance": ""},
]
READING_CALL = {"call_type": "cold_first_contact", "phase_reached": "pitch", "rep_turns": [1, 3, 5]}


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.seen = []
        self.last_call_meta = {}

    async def chat_json(self, messages, **_kw):
        self.seen.append(messages)
        return self.responses.pop(0)


def test_every_answer_of_the_playbook_is_given_by_the_id_the_reading_names_it():
    answers = playbook_answers(ENTRIES)
    assert answers == [
        {"id": "timing", "label": "", "trigger": "", "answer": "Pregunta qué cambiaría y deja fecha."},
        {"id": "es_caro", "label": "Es caro", "trigger": "Es caro", "answer": "¿Respecto a qué te parece caro?"},
    ]
    # v7 to v9 still get only the company's own objections.
    assert playbook_qualification_inputs([{"entries": ENTRIES}])[1] == [{"id": "es_caro", "label": "Es caro", "trigger": "Es caro"}]
    assert playbook_qualification_inputs([{"entries": ENTRIES}], every_answer=True)[1] == answers
    messages = build_messages({"id": "m"}, prompt_version=extract.ANSWERS_PROMPT_VERSION, playbook_objections=answers,
                              transcript="You: hola", call=READING_CALL)
    assert '"answer": "Pregunta qué cambiaría y deja fecha."' in messages[-1]["content"]
    assert "pushed back" in messages[0]["content"] and "after_quote" in messages[0]["content"]


def test_what_happened_after_the_reply_is_kept_only_when_the_prospect_said_it():
    judged = {"objections": [
        {"kind": "objection", "category": "timing", "objection_id": "timing", "resolution": "open",
         "quote": "ahora no estamos buscando este tipo de soluciones", "response": "¿Por qué, qué cambiaría para el año que viene?",
         "after": "advanced", "after_quote": "Déjame mirarlo y si me interesa podríamos agendar"},
        # An answer the playbook does not have: the objection stays, with no answer to group it under.
        {"kind": "objection", "category": "trust", "objection_id": "legal", "resolution": "open",
         "quote": "lo de grabar las llamadas no lo tengo claro por el tema legal", "response": None,
         "after": "ended", "after_quote": "esto nunca se dijo"},
    ]}
    memo = {"id": "m-10", "transcript": TRANSCRIPT, "created_at": "2026-11-10T10:00:00+01:00", "extraction": {"summary": "s"}}
    shaped, _ = asyncio.run(extract_intelligence(memo, FakeLLM(READING_CALL, judged), prompt_version=extract.ANSWERS_PROMPT_VERSION,
                                                 playbook_objections=playbook_answers(ENTRIES)))
    first, second = shaped["objections"]
    assert first["objection_id"] == "timing" and first["after"] == "advanced"
    assert first["after_quote"] == "Déjame mirarlo y si me interesa podríamos agendar"
    # A quote that is not in the call: the fact goes with it.
    assert second["objection_id"] is None and second["after"] == "unknown" and second["after_quote"] is None
    assert "nature" not in first  # v10 is v8's shape: no coaching reading
    assert shaped["prompt_version"] == extract.ANSWERS_PROMPT_VERSION


def test_v8_and_v9_blocks_stay_current_and_are_not_re_read():
    for stored in ("intelligence_v8", "intelligence_v9"):
        memo = {"extraction": {"intelligence": {"prompt_version": stored}}}
        assert not extract._needs_upgrade(memo, extract.ANSWERS_PROMPT_VERSION)
        assert stored in extract.CURRENT_PROMPT_VERSIONS
