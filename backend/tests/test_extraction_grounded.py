"""Step-1 CRM extraction in the C04 v8 pipeline: the call was read first."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from app.services.extraction import ExtractionService

SPECS = [
    {"name": "pains", "object_type": "companies", "type": "enumeration", "label": "Pains",
     "options": [{"value": "leads", "label": "Pocos leads"}]},
]
READING = {"call_type": "cold_first_contact", "phase_reached": "discovery", "roles_marked": True}


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        return dict(self.reply)


class FakeJev:
    is_available = True

    def __init__(self):
        self.calls = 0

    async def classify_enums(self, *args, **kwargs):
        self.calls += 1
        return {"pains": "leads"}


def _service(reply):
    service = ExtractionService.__new__(ExtractionService)
    service.llm = FakeLLM(reply)
    service.jev = FakeJev()
    return service


def test_no_conversation_writes_one_line_and_calls_no_model():
    service = _service({"summary": "x"})
    out = asyncio.run(service.extract(
        "You: hola\n\nThem: ...", SPECS,
        call_reading={"call_type": "no_conversation", "call_type_reason": "Saltó el buzón."},
    ))
    assert out.summary.startswith("**Resultado:** Sin conversación.")
    assert service.llm.calls == [] and service.jev.calls == 0


def test_grounded_prompt_judges_on_the_prospects_words_and_skips_the_enum_second_passes():
    service = _service({"summary": "**Resultado:** Aceptó una demo.", "nextSteps": []})
    asyncio.run(service.extract(
        "You: soy Ana de Acme\n\nThem: se nos escapan los leads", SPECS, call_reading=READING,
    ))
    system, user = service.llm.calls[0][0]["content"], service.llm.calls[0][1]["content"]
    assert "never facts about the prospect" in system
    assert "Only what the prospect said" in user and "primera conversación" in user
    assert "partner_channel" not in user and "MUST set it" not in user
    assert service.jev.calls == 0 and len(service.llm.calls) == 1  # no Jev, no leftover-enum pass


def test_without_a_reading_the_legacy_prompt_is_unchanged():
    service = _service({"summary": "x"})
    service.jev.is_available = False
    asyncio.run(service.extract("S1: hola\n\nS2: dime", SPECS))
    assert "prefer the best-matching option over null" in service.llm.calls[0][1]["content"]
