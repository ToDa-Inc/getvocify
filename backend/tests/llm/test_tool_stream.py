"""Streaming tool-call turns: deltas surface as they arrive, tool calls assemble from fragments."""

import json

import httpx
import pytest
import respx

from app.services.llm.providers.openrouter import OPENROUTER_URL, OpenRouterProvider
from app.services.llm.stream import ToolStreamAccumulator


def _chunk(delta: dict, finish: str | None = None) -> dict:
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


def test_text_deltas_are_returned_and_joined():
    acc = ToolStreamAccumulator()
    assert acc.feed(_chunk({"content": "Hola"})) == "Hola"
    assert acc.feed(_chunk({"content": " Marina"})) == " Marina"
    assert acc.feed(_chunk({}, "stop")) is None
    message = acc.message()
    assert message["content"] == "Hola Marina"
    assert message["tool_calls"] is None


def test_tool_call_fragments_assemble_by_index():
    acc = ToolStreamAccumulator()
    acc.feed(_chunk({"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "get_contact", "arguments": ""}}]}))
    acc.feed(_chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"contact_'}}]}))
    acc.feed(_chunk({"tool_calls": [{"index": 0, "function": {"arguments": 'id": "c1"}'}}]}))
    acc.feed(_chunk({"tool_calls": [{"index": 1, "id": "call-2", "function": {"name": "list_notes", "arguments": "{}"}}]}))
    message = acc.message()
    calls = message["tool_calls"]
    assert [c["id"] for c in calls] == ["call-1", "call-2"]
    assert calls[0]["function"] == {"name": "get_contact", "arguments": '{"contact_id": "c1"}'}
    assert calls[1]["function"]["name"] == "list_notes"


def test_a_chunk_without_choices_is_ignored():
    acc = ToolStreamAccumulator()
    assert acc.feed({"usage": {"total_tokens": 3}}) is None
    assert acc.usage == {"total_tokens": 3}
    assert acc.message()["content"] is None


def _sse(*events: dict | str) -> str:
    lines = []
    for event in events:
        payload = event if isinstance(event, str) else json.dumps(event)
        lines.append(f"data: {payload}\n\n")
    return "".join(lines)


@pytest.mark.asyncio
@respx.mock
async def test_provider_yields_deltas_then_the_final_result():
    body = _sse(
        _chunk({"content": "Hola"}),
        _chunk({"content": " Marina"}),
        _chunk({}, "stop"),
        "[DONE]",
    )
    route = respx.post(OPENROUTER_URL).mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    provider = OpenRouterProvider(api_key="test-key", model="m")
    seen = []
    async for kind, payload in provider.chat_tools_stream([{"role": "user", "content": "hi"}], tools=[]):
        seen.append((kind, payload))
    assert [p for k, p in seen if k == "delta"] == ["Hola", " Marina"]
    kind, final = seen[-1]
    assert kind == "final"
    assert final.content == "Hola Marina"
    assert final.tool_calls == []
    sent = json.loads(route.calls.last.request.content)
    assert sent["stream"] is True


@pytest.mark.asyncio
@respx.mock
async def test_provider_final_carries_parsed_tool_calls():
    body = _sse(
        _chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_contact", "arguments": '{"contact_id":"x"}'}}]}),
        _chunk({}, "tool_calls"),
        "[DONE]",
    )
    respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(200, content=body))
    provider = OpenRouterProvider(api_key="test-key", model="m")
    final = None
    async for kind, payload in provider.chat_tools_stream([], tools=[{"type": "function"}]):
        if kind == "final":
            final = payload
    assert final.tool_calls == [{"id": "c1", "name": "get_contact", "arguments": {"contact_id": "x"}}]


@pytest.mark.asyncio
@respx.mock
async def test_an_http_error_before_the_stream_raises():
    respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(401, json={"error": {"message": "bad key"}}))
    provider = OpenRouterProvider(api_key="test-key", model="m")
    with pytest.raises(Exception, match="401"):
        async for _ in provider.chat_tools_stream([], tools=[]):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_a_429_before_any_bytes_is_retried_then_streams(monkeypatch):
    monkeypatch.setattr("app.services.llm.providers.openrouter.STREAM_RETRY_DELAYS", (0, 0))
    ok = _sse(_chunk({"content": "Hola"}), _chunk({}, "stop"), "[DONE]")
    route = respx.post(OPENROUTER_URL).mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "retry shortly"}}),
            httpx.Response(503, json={"error": {"message": "upstream"}}),
            httpx.Response(200, content=ok),
        ]
    )
    provider = OpenRouterProvider(api_key="test-key", model="m")
    final = None
    async for kind, payload in provider.chat_tools_stream([], tools=[]):
        if kind == "final":
            final = payload
    assert final.content == "Hola" and route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_retries_are_bounded_and_a_client_error_is_not_retried(monkeypatch):
    monkeypatch.setattr("app.services.llm.providers.openrouter.STREAM_RETRY_DELAYS", (0, 0))
    always = respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(429, json={"error": {"message": "slow down"}}))
    provider = OpenRouterProvider(api_key="test-key", model="m")
    with pytest.raises(Exception, match="429"):
        async for _ in provider.chat_tools_stream([], tools=[]):
            pass
    assert always.call_count == 3  # one try plus two retries
    respx.reset()
    bad = respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(400, json={"error": {"message": "bad request"}}))
    with pytest.raises(Exception, match="400"):
        async for _ in provider.chat_tools_stream([], tools=[]):
            pass
    assert bad.call_count == 1


def test_reasoning_fragments_join_per_index_and_ride_on_the_message():
    acc = ToolStreamAccumulator()
    for piece in ("We need", " a tool."):
        acc.feed(_chunk({"reasoning_details": [{"type": "reasoning.text", "text": piece, "format": "unknown", "index": 0}]}))
    acc.feed(_chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "crm_call_stats", "arguments": "{}"}}]}))
    message = acc.message()
    assert message["reasoning_details"] == [{"type": "reasoning.text", "text": "We need a tool.", "format": "unknown", "index": 0}]
    assert message["tool_calls"][0]["id"] == "c1"


def test_a_message_without_reasoning_has_no_reasoning_key():
    acc = ToolStreamAccumulator()
    acc.feed(_chunk({"content": "Hola"}))
    assert "reasoning_details" not in acc.message()
