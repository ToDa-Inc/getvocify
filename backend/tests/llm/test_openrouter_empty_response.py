import httpx
import pytest
import respx

from app.services.llm.providers.openrouter import OPENROUTER_URL, OpenRouterProvider


def _reply(content):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "model": "google/gemini-3.8-flash",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


@respx.mock
@pytest.mark.asyncio
async def test_an_empty_reply_is_retried():
    route = respx.post(OPENROUTER_URL).mock(side_effect=[_reply(None), _reply('{"ok": true}')])
    provider = OpenRouterProvider(api_key="test-key", model="google/gemini-3.8-flash")
    assert await provider.chat_json([{"role": "user", "content": "hola"}]) == {"ok": True}
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_empty_replies_on_every_attempt_still_raise_empty_model_response():
    respx.post(OPENROUTER_URL).mock(return_value=_reply(None))
    provider = OpenRouterProvider(api_key="test-key", model="google/gemini-3.8-flash")
    with pytest.raises(ValueError, match="Empty model response"):
        await provider.chat([{"role": "user", "content": "hola"}], max_retries=1)
