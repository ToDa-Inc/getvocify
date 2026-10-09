"""Live help's line comes from a direct provider (Together), with OpenRouter as the backup: the backup
starts when the direct one has not written a word in time or fails, and whichever writes first is shown.

Measured 2026-10-05: Together direct wrote the line in 0.39 s (median) and never over 1 s in 50 requests,
but any provider can stall before its first word (Lithos once waited 23 s); a line that late is useless."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

import asyncio
import json

import httpx
import pytest

from app.config import settings
from app.services.copilot import suggest


def _source(pieces, delay=0.0, fail=None, log=None, name="source"):
    def start():
        async def gen():
            if log is not None:
                log.append(f"{name} started")
            try:
                await asyncio.sleep(delay)
                if fail:
                    raise fail
                for piece in pieces:
                    yield piece
            finally:
                if log is not None:
                    log.append(f"{name} closed")
        return gen()
    return start


def _collect(primary, backup, hedge_s=0.05):
    async def run():
        return [item async for item in suggest.first_writer([("direct", primary), ("openrouter", backup)], hedge_s)]
    return asyncio.run(run())


def test_the_direct_provider_in_time_is_the_only_one_asked():
    log = []
    out = _collect(_source(["a", "b"], log=log, name="direct"), _source(["x"], log=log, name="openrouter"))
    assert out == [("direct", "a"), ("direct", "b")]
    assert "openrouter started" not in log


def test_a_stalled_direct_provider_hands_the_line_to_the_backup():
    log = []
    out = _collect(_source(["late"], delay=1.0, log=log, name="direct"), _source(["x", "y"], log=log, name="openrouter"))
    assert out == [("openrouter", "x"), ("openrouter", "y")]
    assert "direct closed" in log  # the stalled request is cancelled, not left running


def test_a_failing_direct_provider_starts_the_backup_at_once():
    async def run():
        t0 = asyncio.get_running_loop().time()
        out = [item async for item in suggest.first_writer(
            [("direct", _source([], fail=RuntimeError("503"))), ("openrouter", _source(["x"]))], 5.0)]
        return out, asyncio.get_running_loop().time() - t0
    out, took = asyncio.run(run())
    assert out == [("openrouter", "x")]
    assert took < 1.0, "a failure must not wait for the hedge delay"


def test_when_every_provider_fails_the_caller_is_told():
    with pytest.raises(RuntimeError):
        _collect(_source([], fail=RuntimeError("down")), _source([], fail=RuntimeError("down too")))


def test_unpinned_live_help_still_asks_for_the_fastest_provider(monkeypatch):
    monkeypatch.setattr(settings, "COPILOT_PROVIDER", None, raising=False)
    assert suggest.live_provider() == {"provider": {"sort": "latency"}}


# --- Through the real request code ------------------------------------------------------------------


LINE = json.dumps({"is_objection": True, "objection_type": "price", "source_id": None, "say_this": "En la demo te digo el precio."})


def _sse(text):
    chunk = json.dumps({"choices": [{"delta": {"content": text}}]})
    return httpx.Response(200, text=f"data: {chunk}\n\ndata: [DONE]\n\n", headers={"content-type": "text/event-stream"})


def _suggest(monkeypatch, direct_reply):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-key", raising=False)
    monkeypatch.setattr(settings, "COPILOT_DIRECT_URL", "https://direct.example/v1/chat/completions", raising=False)
    monkeypatch.setattr(settings, "COPILOT_DIRECT_API_KEY", "direct-key", raising=False)
    monkeypatch.setattr(settings, "COPILOT_DIRECT_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash", raising=False)
    monkeypatch.setattr(settings, "COPILOT_REASONING_EFFORT", "none", raising=False)
    sent = []

    def reply(request):
        body = json.loads(request.content)
        sent.append((request.url.host, body))
        return direct_reply(body) if request.url.host == "direct.example" else _sse(LINE)

    real = httpx.AsyncClient
    monkeypatch.setattr(suggest.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(reply), **kw))

    async def run():
        return [e async for e in suggest.stream_objection_suggestion(
            transcript_window="Them: caro", latest_turn="me parece caro", call_mode="meeting", model="deepseek/deepseek-v4.1-flash",
        )]

    events = asyncio.run(run())
    return next(e for e in events if e["type"] == "result"), sent


def test_live_help_writes_the_line_with_the_direct_provider(monkeypatch):
    result, sent = _suggest(monkeypatch, lambda body: _sse(LINE))
    assert result["suggestion"]["say_this"] == "En la demo te digo el precio."
    assert [host for host, _ in sent] == ["direct.example"]
    direct = sent[0][1]
    assert direct["model"] == "deepseek-ai/DeepSeek-V4.1-Flash"
    assert direct["reasoning_effort"] == "none"  # the direct API's way to switch thinking off
    assert result["model"] == "direct:deepseek-ai/DeepSeek-V4.1-Flash"


def test_a_failing_direct_provider_still_gives_the_rep_the_line(monkeypatch):
    result, sent = _suggest(monkeypatch, lambda body: httpx.Response(503, text="busy"))
    assert result["suggestion"]["say_this"] == "En la demo te digo el precio."
    assert [host for host, _ in sent] == ["direct.example", "openrouter.ai"]
    assert result["model"] == "openrouter:deepseek/deepseek-v4.1-flash"
