import pytest

from app.services.conversation.intent import ADD_PATTERNS, IntentService, resolve_intent_by_rules


def test_keep_and_skip_and_change_deal():
    assert resolve_intent_by_rules("no actualizar", "waiting_approval", "m1").intent == "keep"
    assert resolve_intent_by_rules("quita el deal", "waiting_approval", "m1").intent == "skip_deal"
    assert resolve_intent_by_rules("sin deal", "waiting_approval", "m1").intent == "skip_deal"
    assert resolve_intent_by_rules("otro deal", "waiting_approval", "m1").intent == "change_deal"
    r = resolve_intent_by_rules("el deal de acme", "waiting_approval", "m1")
    assert r.intent == "search_deal"
    assert "acme" in (r.params or {}).get("q", "").lower()


def test_digit_2_is_not_add_fields():
    assert "2" not in ADD_PATTERNS
    assert resolve_intent_by_rules("2", "waiting_approval", "m1") is None
    assert resolve_intent_by_rules("add", "waiting_approval", "m1").intent == "add_fields"
    assert resolve_intent_by_rules("editar", "waiting_approval", "m1").intent == "add_fields"


@pytest.mark.asyncio
async def test_llm_fallback_prompt_includes_crm_update():
    captured = {}

    class FakeLLM:
        async def chat_json(self, messages, temperature=0):
            captured["system"] = messages[0]["content"]
            return {"intent": "unclear", "confidence": 0.1}

    result = await IntentService(llm_client=FakeLLM()).resolve(
        "pon el amount a 50k", "waiting_approval", "m1"
    )
    system = captured["system"]
    assert '"crm_update"' in system
    assert '"keep"' in system
    assert '"reject"' not in system
    assert "property" in system and "value" in system
    assert result.intent == "unclear"
