"""Filler guard: known AI filler never reaches a rep's email or an Ask answer, and normal
content is never touched."""

import asyncio
import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-text-guard-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-text-guard-32b")

from app.services.text_guard import email_filler, strip_chat_filler, strip_email_filler

BODY = (
    "Hola Marina,\n\n"
    "Te envío el caso de logística que me pediste. Veo una gran oportunidad para vuestro equipo.\n"
    "Quedo a tu disposición para cualquier cosa.\n\n"
    "Un saludo,\nLucía"
)


def test_finds_email_filler_in_spanish_and_english():
    assert set(email_filler(BODY)) == {"Quedo a tu disposición", "una gran oportunidad"}
    assert set(email_filler("I hope this email finds you well. Let's touch base Friday.")) == {
        "I hope this email finds you", "touch base",
    }


def test_normal_content_is_not_flagged():
    clean = (
        "Hola Pedro,\n\nComo me pediste, te mando la propuesta con los 3 puntos que acordamos: "
        "integración con HubSpot, formación y precio por comercial. El jueves 1 de octubre a las 11 "
        "lo revisamos juntos, al nivel de detalle que necesites.\n\nUn saludo,\nLucía"
    )
    assert email_filler(clean) == []
    assert strip_email_filler(clean) == clean


def test_strip_removes_only_the_filler_sentences():
    stripped = strip_email_filler(BODY)
    assert "gran oportunidad" not in stripped and "disposición" not in stripped
    assert "Te envío el caso de logística que me pediste." in stripped
    assert stripped.startswith("Hola Marina,") and stripped.endswith("Un saludo,\nLucía")


def test_chat_filler_openers_and_closers_go_content_stays():
    answer = "¡Claro! Marina Ruiz tiene 2 notas y un deal abierto.\nSi necesitas algo más, dímelo."
    assert strip_chat_filler(answer) == "Marina Ruiz tiene 2 notas y un deal abierto."
    assert strip_chat_filler("¡Claro!") == "¡Claro!"  # never empties an answer
    assert strip_chat_filler("Llama a Marina: te pidió hablar hoy.") == "Llama a Marina: te pidió hablar hoy."


def test_chat_guard_never_deletes_a_content_sentence():
    # Self-review fix: an opener followed by a comma used to drop the whole sentence.
    assert strip_chat_filler("Claro, S.L. tiene 2 deals abiertos.") == "Claro, S.L. tiene 2 deals abiertos."
    assert strip_chat_filler("Por supuesto, Marina tiene 3 deals.") == "Por supuesto, Marina tiene 3 deals."
    # A closer's words in the middle of an answer are content, not a closing offer.
    mid = "Si quieres más información del deal, está en la nota del 12 sep. Marina decide el viernes."
    assert strip_chat_filler(mid) == mid
    # Closing offer in the same line as content: only that sentence goes.
    assert strip_chat_filler("Marina decide el viernes. Si necesitas algo más, dímelo.") == "Marina decide el viernes."


class _LLM:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def chat_json(self, messages, **_kwargs):
        self.calls.append(messages)
        return self.payloads.pop(0)


def _payload(body):
    return {"subject": "Caso de logística", "body": body, "language": "es"}


def test_followup_is_asked_again_naming_the_filler():
    from app.services.followup import compose

    clean = "Hola Marina,\n\nTe envío el caso de logística que me pediste y la propuesta con los precios por comercial que vimos hoy en la llamada, para que lo reviséis con calma.\n\nUn saludo,\nLucía"
    llm = _LLM(_payload(BODY), _payload(clean))
    draft = asyncio.run(compose(llm, [{"role": "user", "content": "x"}]))
    assert draft["body"] == clean
    assert len(llm.calls) == 2
    assert "gran oportunidad" in llm.calls[1][-1]["content"]


def test_filler_that_survives_the_retry_is_stripped_when_an_email_remains():
    from app.services.followup import compose

    long_body = (
        "Hola Marina,\n\nTe envío el caso de logística que me pediste, con los resultados del equipo de "
        "Barcelona y el detalle de cómo se registran las llamadas en HubSpot al colgar. Veo una gran "
        "oportunidad.\n\nEl jueves a las once lo revisamos con tu director comercial.\n\nUn saludo,\nLucía"
    )
    llm = _LLM(_payload(long_body), _payload(long_body))
    draft = asyncio.run(compose(llm, [{"role": "user", "content": "x"}]))
    assert "gran oportunidad" not in draft["body"]
    assert "El jueves a las once lo revisamos" in draft["body"]


def test_a_clean_followup_is_one_call():
    from app.services.followup import compose

    llm = _LLM(_payload("Hola Marina,\n\nTe envío el caso.\n\nUn saludo,\nLucía"))
    asyncio.run(compose(llm, [{"role": "user", "content": "x"}]))
    assert len(llm.calls) == 1


def test_ask_answers_lose_filler_openers():
    from app.services.crm_copilot.web_sessions import public_answer

    assert public_answer("¡Por supuesto! Tienes 3 llamadas pendientes.") == "Tienes 3 llamadas pendientes."
