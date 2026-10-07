"""A "together/<id>" model is served by Together AI without reasoning, priced from settings, and
answered by the same model through OpenRouter when Together fails."""

import json

import httpx
import pytest
import respx

from app.config import settings
from app.services.llm.providers.openrouter import OPENROUTER_URL, TOGETHER_URL, OpenRouterProvider

MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"


def _reply(content, model=MODEL):
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": model,
        "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000},
    })


@pytest.fixture(autouse=True)
def _together(monkeypatch):
    monkeypatch.setattr(settings, "TOGETHER_API_KEY", "tg-key")
    monkeypatch.setattr(settings, "TOGETHER_PRICES", {MODEL: (0.30, 1.20)})
    monkeypatch.setattr(settings, "TOGETHER_FALLBACKS", {MODEL: "deepseek/deepseek-v4.1-flash"})


@respx.mock
@pytest.mark.asyncio
async def test_a_together_model_goes_to_together_without_reasoning_and_is_priced():
    route = respx.post(TOGETHER_URL).mock(return_value=_reply('{"ok": true}'))
    provider = OpenRouterProvider(api_key="or-key")
    assert await provider.chat_json([{"role": "user", "content": "hola"}], model=f"together/{MODEL}") == {"ok": True}
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == MODEL
    assert sent["reasoning"] == {"enabled": False}
    assert route.calls[0].request.headers["Authorization"] == "Bearer tg-key"
    assert provider.last_call_meta["cost_usd"] == pytest.approx(1.50)  # 1M in x 0.30 + 1M out x 1.20


@respx.mock
@pytest.mark.asyncio
async def test_effort_none_turns_reasoning_off_on_openrouter_too():
    route = respx.post(OPENROUTER_URL).mock(return_value=_reply('{"ok": true}', "deepseek/deepseek-v4.1-flash"))
    provider = OpenRouterProvider(api_key="or-key")
    await provider.chat_json([{"role": "user", "content": "hola"}], model="deepseek/deepseek-v4.1-flash", reasoning_effort="none")
    assert json.loads(route.calls[0].request.content)["reasoning"] == {"enabled": False}


@respx.mock
@pytest.mark.asyncio
async def test_when_together_fails_the_same_model_answers_through_openrouter():
    respx.post(TOGETHER_URL).mock(return_value=httpx.Response(503, json={"error": {"message": "busy"}}))
    fallback = respx.post(OPENROUTER_URL).mock(return_value=_reply('{"ok": true}', "deepseek/deepseek-v4.1-flash"))
    provider = OpenRouterProvider(api_key="or-key")
    assert await provider.chat_json([{"role": "user", "content": "hola"}], model=f"together/{MODEL}", max_retries=0) == {"ok": True}
    sent = json.loads(fallback.calls[0].request.content)
    assert sent["model"] == "deepseek/deepseek-v4.1-flash"
    assert sent["reasoning"] == {"enabled": False}
    assert fallback.calls[0].request.headers["Authorization"] == "Bearer or-key"


@respx.mock
@pytest.mark.asyncio
async def test_without_a_together_key_the_fallback_answers(monkeypatch):
    monkeypatch.setattr(settings, "TOGETHER_API_KEY", None)
    together = respx.post(TOGETHER_URL).mock(return_value=_reply('{"ok": true}'))
    respx.post(OPENROUTER_URL).mock(return_value=_reply('{"ok": true}', "deepseek/deepseek-v4.1-flash"))
    provider = OpenRouterProvider(api_key="or-key")
    assert await provider.chat_json([{"role": "user", "content": "hola"}], model=f"together/{MODEL}") == {"ok": True}
    assert together.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_other_models_still_go_to_openrouter_untouched():
    route = respx.post(OPENROUTER_URL).mock(return_value=_reply('{"ok": true}', "google/gemini-3.8-flash"))
    provider = OpenRouterProvider(api_key="or-key")
    await provider.chat_json([{"role": "user", "content": "hola"}], model="google/gemini-3.8-flash")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "google/gemini-3.8-flash"
    assert "reasoning" not in sent


@respx.mock
@pytest.mark.asyncio
async def test_by_default_a_failed_together_call_does_not_go_to_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "TOGETHER_FALLBACKS", {})
    respx.post(TOGETHER_URL).mock(return_value=httpx.Response(503, json={"error": {"message": "busy"}}))
    other = respx.post(OPENROUTER_URL).mock(return_value=_reply('{"ok": true}', "deepseek/deepseek-v4.1-flash"))
    provider = OpenRouterProvider(api_key="or-key")
    with pytest.raises(Exception):
        await provider.chat_json([{"role": "user", "content": "hola"}], model=f"together/{MODEL}", max_retries=0)
    assert other.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_max_tokens_caps_the_answer_and_keeps_reasoning_off():
    route = respx.post(TOGETHER_URL).mock(return_value=_reply('{"ok": true}'))
    provider = OpenRouterProvider(api_key="or-key")
    await provider.chat_json([{"role": "user", "content": "hola"}], model=f"together/{MODEL}", max_tokens=1500)
    sent = json.loads(route.calls[0].request.content)
    assert sent["max_tokens"] == 1500 and sent["reasoning"] == {"enabled": False}


@respx.mock
@pytest.mark.asyncio
async def test_without_max_tokens_the_default_cap_applies():
    route = respx.post(TOGETHER_URL).mock(return_value=_reply('{"ok": true}'))
    provider = OpenRouterProvider(api_key="or-key")
    await provider.chat_json([{"role": "user", "content": "hola"}], model=f"together/{MODEL}")
    assert json.loads(route.calls[0].request.content)["max_tokens"] == settings.LLM_MAX_OUTPUT_TOKENS
