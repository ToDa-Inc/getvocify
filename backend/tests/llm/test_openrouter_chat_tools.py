import httpx
import pytest
import respx

from app.services.llm.providers.openrouter import OPENROUTER_URL, OpenRouterProvider


@respx.mock
@pytest.mark.asyncio
async def test_chat_tools_sends_tools_and_parses_calls():
    respx.post(OPENROUTER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_contacts",
                                        "arguments": '{"query":"Marc"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "model": "google/gemini-3.8-flash",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    provider = OpenRouterProvider(api_key="test-key", model="google/gemini-3.8-flash")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_contacts",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        }
    ]
    result = await provider.chat_tools(
        [{"role": "user", "content": "where is Marc?"}],
        tools=tools,
        extra={"reasoning": {"effort": "low"}},
    )
    request = respx.calls[0].request
    body = request.content
    assert b'"tools"' in body
    assert b"search_contacts" in body
    assert b'"reasoning"' in body
    assert result.content is None
    assert result.tool_calls[0]["name"] == "search_contacts"
    assert result.tool_calls[0]["arguments"]["query"] == "Marc"
    assert result.tool_calls[0]["id"] == "c1"
